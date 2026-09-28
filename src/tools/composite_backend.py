"""Aggregate built-in tools with locally admitted external providers."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from src.core.capabilities import validate_active_capabilities
from src.core.interfaces import ToolBackend, ToolProvider
from src.core.schemas import (
    ExternalToolAdmission,
    PreflightReport,
    ProviderSnapshot,
    Result,
    ToolCallDraft,
    ToolCapability,
    ToolDef,
    ToolError,
)
from src.core.tool_validation import validate_tool_call, validate_tool_catalog
from src.safety.guarded_executor import contains_bare_secret, contains_sensitive_value
from src.tools.provider_declarations import (
    EXTERNAL_CAPABILITIES,
    EXTERNAL_TOOL_ADMISSIONS,
    external_tool_defs,
)

_MAX_PARAM_CODEPOINTS = 8192
_MAX_REQUEST_BYTES = 32768
_PROVIDER_ENVELOPE_OVERHEAD = 64
_FATAL_PROVIDER_REASONS = frozenset({
    "provider_timeout",
    "provider_unreachable",
    "provider_response_too_large",
    "provider_parse_error",
    "provider_protocol_error",
})


@dataclass
class _ExternalBinding:
    provider: ToolProvider
    raw_name: str
    definition: ToolDef
    healthy: bool = True


class CompositeToolBackend(ToolBackend):
    """Single ToolBackend view over built-ins and compatible external tools."""

    def __init__(
        self,
        builtin: ToolBackend,
        provider_snapshots: tuple[tuple[ToolProvider, ProviderSnapshot], ...],
        *,
        admissions: tuple[ExternalToolAdmission, ...] = EXTERNAL_TOOL_ADMISSIONS,
        external_capabilities: tuple[ToolCapability, ...] = EXTERNAL_CAPABILITIES,
    ) -> None:
        self._builtin = builtin
        self._providers = tuple(provider for provider, _ in provider_snapshots)
        self._snapshots = {snapshot.provider_id: snapshot for _, snapshot in provider_snapshots}
        self._closed = False
        self._bindings: dict[str, _ExternalBinding] = {}
        self._contract_mismatch_count = 0
        self._contract_mismatch_clauses: Counter[str] = Counter()
        self._unadmitted_count = 0
        tool_defs = external_tool_defs(admissions)
        definition_by_key = {
            (admission.provider_id, admission.raw_name): definition
            for admission, definition in zip(admissions, tool_defs, strict=True)
        }
        provider_by_id = {provider.provider_id: provider for provider in self._providers}
        admitted_keys = set(definition_by_key)
        served_count = 0
        for _, snapshot in provider_snapshots:
            served_count += len(snapshot.candidates)
            self._unadmitted_count += sum(
                (snapshot.provider_id, candidate.raw_name) not in admitted_keys
                for candidate in snapshot.candidates
            )
            if not snapshot.healthy:
                continue
            by_name: dict[str, list[object]] = {}
            for candidate in snapshot.candidates:
                by_name.setdefault(candidate.raw_name, []).append(candidate)
            for key, definition in definition_by_key.items():
                provider_id, raw_name = key
                if provider_id != snapshot.provider_id:
                    continue
                candidates = by_name.get(raw_name, [])
                if len(candidates) != 1:
                    self._contract_mismatch_count += 1
                    self._contract_mismatch_clauses["not_reported"] += 1
                    continue
                mismatch = _compatibility_mismatch(definition, candidates[0])
                if mismatch is not None:
                    self._contract_mismatch_count += 1
                    self._contract_mismatch_clauses[mismatch] += 1
                    continue
                self._bindings[definition.name] = _ExternalBinding(
                    provider_by_id[provider_id], raw_name, definition,
                )
        self._admitted_count = len(tool_defs)
        self._served_count = served_count
        validate_tool_catalog([*builtin.list_tools(), *tool_defs])
        self._capabilities = validate_active_capabilities(
            (*builtin.list_capabilities(), *external_capabilities),
            self.list_tools(),
        )

    def list_tools(self) -> list[ToolDef]:
        if self._closed:
            return []
        for binding in self._bindings.values():
            diagnostic: dict[str, object] = getattr(
                binding.provider, "diagnostics", lambda: {}
            )()
            if diagnostic and diagnostic.get("healthy") is False:
                binding.healthy = False
        external = [
            binding.definition
            for binding in self._bindings.values()
            if binding.healthy
        ]
        return [*self._builtin.list_tools(), *external]

    def list_capabilities(self) -> list[ToolCapability]:
        return [] if self._closed else list(self._capabilities)

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        if self._closed:
            return Result.err(_tool_not_found(tool_name))
        binding = self._bindings.get(tool_name)
        if binding is None:
            if tool_name in {tool.name for tool in self._builtin.list_tools()}:
                return self._builtin.execute(tool_name, params)
            return Result.err(_tool_not_found(tool_name))
        if not binding.healthy:
            return Result.err(_tool_not_found(tool_name))
        for value in params.values():
            if isinstance(value, str) and len(value) > _MAX_PARAM_CODEPOINTS:
                return Result.err(_execution_error("param_too_large"))
            if isinstance(value, str) and (
                contains_sensitive_value(value) or contains_bare_secret(value)
            ):
                return Result.err(_execution_error("param_secret_rejected"))
        validation = validate_tool_call(
            ToolCallDraft(tool_name, dict(params)), (binding.definition,),
        )
        if not validation.ok:
            return Result.err(ToolError(
                code="TOOL_PARAM_ERROR",
                message=f"External tool parameters rejected: {validation.reason}",
                user_message="操作参数不正确。",
                recoverable=True,
                details={"reason": validation.reason},
            ))
        outbound = json.dumps(
            {"name": binding.raw_name, "arguments": params},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(outbound) + _PROVIDER_ENVELOPE_OVERHEAD > _MAX_REQUEST_BYTES:
            return Result.err(_execution_error("param_too_large"))
        result = binding.provider.execute(binding.raw_name, dict(params))
        if result.error is not None and isinstance(result.error.details, dict):
            reason = result.error.details.get("reason")
            if reason in _FATAL_PROVIDER_REASONS:
                binding.healthy = False
        return result

    def preflight(self, tool_name: str, params: dict) -> PreflightReport:
        if tool_name in self._bindings and self._bindings[tool_name].healthy:
            return super().preflight(tool_name, params)
        return self._builtin.preflight(tool_name, params)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for binding in self._bindings.values():
            binding.healthy = False
        for provider in self._providers:
            try:
                provider.close()
            except Exception:
                continue
        try:
            self._builtin.close()
        except Exception:
            pass

    def diagnostics(self) -> dict[str, object]:
        provider_health: dict[str, object] = {}
        close_failures = 0
        unhandled = pagination = malformed = unsupported = timeouts = 0
        for provider in self._providers:
            diagnostic: dict[str, object] = getattr(provider, "diagnostics", lambda: {})()
            snapshot = self._snapshots.get(provider.provider_id)
            binding_health = all(
                binding.healthy
                for binding in self._bindings.values()
                if binding.provider is provider
            )
            provider_health[provider.provider_id] = {
                "healthy": diagnostic.get(
                    "healthy",
                    (snapshot.healthy if snapshot else False) and binding_health,
                ),
                "failure_reason": diagnostic.get(
                    "failure_reason", snapshot.failure_reason if snapshot else "unreachable"
                ),
                "protocol_version": diagnostic.get("protocol_version"),
            }
            unhandled += _integer_metric(diagnostic, "unhandled_notifications")
            pagination += _integer_metric(diagnostic, "pagination_ignored")
            malformed += _integer_metric(diagnostic, "malformed_tool_entries")
            unsupported += _integer_metric(diagnostic, "unsupported_content_count")
            timeouts += _integer_metric(diagnostic, "timeout_count")
            close_failures += int(bool(diagnostic.get("close_forced", False)))
        return {
            "enabled_providers": tuple(provider.provider_id for provider in self._providers),
            "provider_health": provider_health,
            "admitted_count": self._admitted_count,
            "served_count": self._served_count,
            "unadmitted_count": self._unadmitted_count,
            "contract_mismatch_count": self._contract_mismatch_count,
            "contract_mismatch_clauses": {
                clause: self._contract_mismatch_clauses[clause]
                for clause in (
                    "schema_shape",
                    "local_required_missing",
                    "local_required_type",
                    "server_required_undeclared",
                    "not_reported",
                )
            },
            "unhandled_notifications": unhandled,
            "pagination_ignored": pagination,
            "malformed_tool_entries": malformed,
            "unsupported_content_count": unsupported,
            "timeout_count": timeouts,
            "closed": self._closed,
            "close_failures": close_failures,
        }


def _compatibility_mismatch(definition: ToolDef, candidate: object) -> str | None:
    schema = getattr(candidate, "input_schema", None)
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        return "schema_shape"
    properties = schema.get("properties")
    external_required = schema.get("required", [])
    if not isinstance(properties, Mapping) or not isinstance(external_required, list):
        return "schema_shape"
    if (
        any(not isinstance(name, str) for name in external_required)
        or len(set(external_required)) != len(external_required)
    ):
        return "schema_shape"
    local_properties = definition.parameters["properties"]
    local_required = definition.parameters["required"]
    if any(name not in properties for name in local_required):
        return "local_required_missing"
    if any(
        not isinstance(properties[name], Mapping) or properties[name].get("type") != "string"
        for name in local_required
    ):
        return "local_required_type"
    if any(name not in local_properties for name in external_required):
        return "server_required_undeclared"
    return None


def _tool_not_found(tool_name: str) -> ToolError:
    return ToolError(
        code="TOOL_NOT_FOUND",
        message=f"Tool is not available: {tool_name}",
        user_message="所需工具不可用。",
        recoverable=True,
        details={"tool_name": tool_name},
    )


def _execution_error(reason: str) -> ToolError:
    return ToolError(
        code="TOOL_EXEC_ERROR",
        message=f"External tool execution rejected: {reason}",
        user_message="外部工具执行失败。",
        recoverable=True,
        details={"reason": reason},
    )


def _integer_metric(diagnostic: dict[str, object], key: str) -> int:
    value = diagnostic.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
