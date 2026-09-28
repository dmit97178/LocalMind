from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import replace

import pytest

from src.adapters.mcp_adapter import MCPStdioToolProvider
from src.core.interfaces import ToolProvider
from src.core.schemas import ProviderSnapshot, Result, ToolCandidate
from src.tools.builtin_backend import BuiltinToolBackend
from src.tools.composite_backend import CompositeToolBackend
from src.tools.provider_declarations import EXTERNAL_PROVIDERS, resolve_provider_declarations


class FakeProvider(ToolProvider):
    provider_id = "demo"

    def __init__(
        self,
        *,
        schema_type: str = "string",
        candidates: tuple[ToolCandidate, ...] | None = None,
        close_forced: bool = False,
    ) -> None:
        self.closed = False
        self.calls: list[tuple[str, Mapping[str, object]]] = []
        self.schema_type = schema_type
        self.candidates = candidates
        self.close_forced = close_forced

    def handshake(self) -> ProviderSnapshot:
        default = (ToolCandidate("json_format", {
            "type": "object",
            "properties": {"text": {"type": self.schema_type}},
            "required": ["text"],
        }),)
        return ProviderSnapshot(
            "demo",
            True,
            default if self.candidates is None else self.candidates,
        )

    def execute(self, raw_name: str, params: Mapping[str, object]) -> Result[dict]:
        self.calls.append((raw_name, params))
        return Result.ok({"text": str(params["text"])})

    def close(self) -> None:
        self.closed = True

    def diagnostics(self) -> dict[str, object]:
        return {
            "healthy": not self.closed,
            "failure_reason": "closed" if self.closed else None,
            "close_forced": self.close_forced and self.closed,
        }


def _backend(provider: FakeProvider) -> CompositeToolBackend:
    builtin = BuiltinToolBackend(
        {"whitelist": ["system.get_time"], "workspace_root": "."},
        capabilities_enabled=True,
    )
    snapshot = provider.handshake()
    return CompositeToolBackend(builtin, ((provider, snapshot),))


def test_composite_admits_compatible_external_tool_and_merges_capabilities() -> None:
    provider = FakeProvider()
    backend = _backend(provider)
    assert "demo.json_format" in {tool.name for tool in backend.list_tools()}
    assert "text.format" in {item.capability_id for item in backend.list_capabilities()}

    result = backend.execute("demo.json_format", {"text": "{}"})
    assert result.is_ok
    assert provider.calls == [("json_format", {"text": "{}"})]


def test_composite_contract_mismatch_only_makes_tool_unavailable() -> None:
    backend = _backend(FakeProvider(schema_type="integer"))
    assert "demo.json_format" not in {tool.name for tool in backend.list_tools()}
    assert backend.diagnostics()["contract_mismatch_count"] == 1


@pytest.mark.parametrize(
    ("schema", "expected_clause"),
    [
        ({"type": "array"}, "schema_shape"),
        ({"type": "object", "properties": {}, "required": []}, "local_required_missing"),
        ({
            "type": "object",
            "properties": {"text": {"type": "integer"}},
            "required": ["text"],
        }, "local_required_type"),
        ({
            "type": "object",
            "properties": {"text": {"type": "string"}, "extra": {"type": "string"}},
            "required": ["text", "extra"],
        }, "server_required_undeclared"),
    ],
)
def test_composite_records_each_contract_mismatch_clause(
    schema: dict[str, object], expected_clause: str
) -> None:
    backend = _backend(FakeProvider(candidates=(ToolCandidate("json_format", schema),)))

    diagnostics = backend.diagnostics()
    assert diagnostics["contract_mismatch_count"] == 1
    clauses = diagnostics["contract_mismatch_clauses"]
    assert isinstance(clauses, dict)
    assert clauses[expected_clause] == 1
    assert sum(clauses.values()) == 1


def test_composite_records_admitted_tool_not_reported() -> None:
    backend = _backend(FakeProvider(candidates=()))

    diagnostics = backend.diagnostics()
    assert diagnostics["contract_mismatch_count"] == 1
    assert diagnostics["contract_mismatch_clauses"]["not_reported"] == 1


def test_composite_rejects_secret_and_oversize_before_provider_call() -> None:
    provider = FakeProvider()
    backend = _backend(provider)
    secret = backend.execute("demo.json_format", {"text": "sk-" + "a" * 40})
    assert not secret.is_ok and secret.error is not None
    assert secret.error.details["reason"] == "param_secret_rejected"
    oversized = backend.execute("demo.json_format", {"text": "x" * 8193})
    assert not oversized.is_ok and oversized.error is not None
    assert oversized.error.details["reason"] == "param_too_large"
    assert provider.calls == []


def test_composite_close_is_idempotent_and_disables_all_tools() -> None:
    provider = FakeProvider()
    backend = _backend(provider)
    backend.close()
    backend.close()
    assert provider.closed
    assert backend.list_tools() == []
    result = backend.execute("system.get_time", {})
    assert not result.is_ok and result.error is not None
    assert result.error.code == "TOOL_NOT_FOUND"


def test_composite_reports_forced_close_count() -> None:
    backend = _backend(FakeProvider(close_forced=True))

    backend.close()

    assert backend.diagnostics()["close_failures"] == 1


@pytest.mark.parametrize("fault", ["", "hint_readonly_false"])
def test_external_metadata_never_changes_local_admission(fault: str) -> None:
    declaration = resolve_provider_declarations((replace(
        EXTERNAL_PROVIDERS[0],
        argv=(
            sys.executable,
            "scripts/mcp_demo_server.py",
            *(("--fault", fault) if fault else ()),
        ),
    ),))[0]
    provider = MCPStdioToolProvider(
        declaration, handshake_timeout_ms=2000, call_timeout_ms=2000,
    )
    builtin = BuiltinToolBackend(
        {"whitelist": ["system.get_time"], "workspace_root": "."},
        capabilities_enabled=True,
    )
    backend = CompositeToolBackend(builtin, ((provider, provider.handshake()),))
    try:
        definition = next(tool for tool in backend.list_tools() if tool.name == "demo.json_format")
        assert definition.risk_level == "normal"
        assert definition.approval_profile == "standard"
        assert definition.audit_redact_all_params is True
    finally:
        backend.close()


def test_unadmitted_provider_tools_are_counted_but_never_exposed() -> None:
    declaration = resolve_provider_declarations((replace(
        EXTERNAL_PROVIDERS[0],
        argv=(sys.executable, "scripts/mcp_demo_server.py", "--fault", "extra_tools"),
    ),))[0]
    provider = MCPStdioToolProvider(
        declaration, handshake_timeout_ms=2000, call_timeout_ms=2000,
    )
    builtin = BuiltinToolBackend(
        {"whitelist": ["system.get_time"], "workspace_root": "."},
        capabilities_enabled=True,
    )
    backend = CompositeToolBackend(builtin, ((provider, provider.handshake()),))
    try:
        assert {tool.name for tool in backend.list_tools()} == {
            "system.get_time", "demo.json_format",
        }
        diagnostics = backend.diagnostics()
        assert diagnostics["served_count"] == 3
        assert diagnostics["unadmitted_count"] == 2
    finally:
        backend.close()
