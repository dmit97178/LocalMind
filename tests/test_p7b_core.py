from __future__ import annotations

from pathlib import Path

import pytest

from src.core.interfaces import ToolBackend
from src.core.response_builder import ResponseBuilder
from src.core.schemas import (
    ExecutionPlan,
    ExecutionStep,
    LocalMindError,
    ParamInstanceCheck,
    Result,
    ToolDef,
)
from src.core.tool_validation import render_tool_catalog
from src.tools.builtin_backend import BuiltinToolBackend
from src.tools.capabilities import validate_capabilities


def _echo_check(value: str) -> bool:
    return bool(value.strip())


def test_egress_tool_requires_echo_checks_and_audit_redaction() -> None:
    tool = ToolDef(
        name="demo.outbound",
        description="Outbound demo",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        egress=True,
    )
    with pytest.raises(LocalMindError) as exc_info:
        validate_capabilities((), (tool,), enabled=False)
    assert exc_info.value.details == {"reason": "egress_contract_invalid"}

    valid = ToolDef(
        name="demo.outbound",
        description="Outbound demo",
        parameters=tool.parameters,
        egress=True,
        supply_by_echo=("text",),
        audit_redact_all_params=True,
        param_instance_checks={"text": ParamInstanceCheck(_echo_check)},
    )
    assert validate_capabilities((), (valid,), enabled=False) == ()
    rendered = render_tool_catalog((valid,))
    assert "egress" not in rendered
    assert "audit_redact_all_params" not in rendered


def test_tool_backend_close_is_a_backward_compatible_noop() -> None:
    class Backend(ToolBackend):
        def list_tools(self) -> list[ToolDef]:
            return []

        def execute(self, tool_name: str, params: dict) -> Result[dict]:
            return Result.ok({})

    assert Backend().close() is None


def test_response_builder_sanitizes_controls_and_marks_truncation() -> None:
    plan = ExecutionPlan([ExecutionStep("system.echo", "echo", {"message": "x"})])
    result = ResponseBuilder().build(
        plan,
        {0: {"message": "ok\x1b[2J\u200b" + "x" * 5000}},
    )
    assert "\x1b" not in result.display
    assert "\u200b" not in result.display
    assert "…（已截断显示，原文" in result.display


def test_file_stat_reports_metadata_without_content(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    backend = BuiltinToolBackend({
        "whitelist": ["file.stat"],
        "workspace_root": str(tmp_path),
    })

    result = backend.execute("file.stat", {"path": "notes.txt"})

    assert result.is_ok
    assert result.value is not None
    assert result.value["path"] == "notes.txt"
    assert result.value["exists"] is True
    assert result.value["is_dir"] is False
    assert result.value["size_bytes"] == 5
    assert isinstance(result.value["modified_at"], str)
    assert "content" not in result.value


def test_composite_backend_has_no_transport_or_platform_dependency() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "tools" / "composite_backend.py"
    ).read_text(encoding="utf-8").lower()
    assert all(token not in source for token in ("mcp", "qwenpaw", "jsonrpc", "subprocess"))
