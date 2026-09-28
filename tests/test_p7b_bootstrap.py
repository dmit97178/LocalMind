from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.core.interfaces import ToolBackend
from src.core.schemas import Result, ToolDef
from src.main import bootstrap, create_tool_backend
from src.models.mock_backend import MockModelBackend
from tests.test_intent_resolver import ScriptedModelBackend
from tests.test_p7_capability_routing import _response


def _config() -> dict:
    return {
        "tool_backend": {
            "type": "builtin_only",
            "config": {"whitelist": ["system.get_time", "file.stat"]},
        },
        "tools": {"workspace_root": ".", "weather": {"provider": "none"}},
        "capability_routing": {"enabled": True},
        "tool_providers": {
            "demo": {
                "enabled": True,
                "handshake_timeout_ms": 2000,
                "call_timeout_ms": 2000,
            }
        },
    }


def test_factory_enables_demo_provider_and_shutdown_closes_it() -> None:
    backend = create_tool_backend(_config())
    assert "demo.json_format" in {tool.name for tool in backend.list_tools()}
    backend.close()
    assert backend.list_tools() == []


def test_factory_without_provider_section_keeps_builtin_backend() -> None:
    config = _config()
    config.pop("tool_providers")
    backend = create_tool_backend(config)
    assert {tool.name for tool in backend.list_tools()} == {"system.get_time", "file.stat"}
    assert "text.format" in {item.capability_id for item in backend.list_capabilities()}


def test_app_shutdown_closes_enabled_provider() -> None:
    config = Path(__file__).parents[1] / "config" / "mcp.example.toml"
    app = bootstrap(str(config), model_backend_override=MockModelBackend())
    assert "demo.json_format" in {tool.name for tool in app.executor.tool_backend.list_tools()}
    app.shutdown()
    app.shutdown()
    assert app.executor.tool_backend.list_tools() == []


def test_bootstrap_failure_closes_already_created_tool_backend(monkeypatch) -> None:
    class ClosingBackend(ToolBackend):
        closed = False

        def list_tools(self) -> list[ToolDef]:
            return []

        def execute(self, tool_name: str, params: dict) -> Result[dict]:
            return Result.ok({})

        def close(self) -> None:
            self.closed = True

    backend = ClosingBackend()
    monkeypatch.setattr("src.main.create_tool_backend", lambda *args, **kwargs: backend)
    monkeypatch.setattr(
        "src.main.create_safety_backend",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    config = Path(__file__).parents[1] / "config" / "default.toml"
    with pytest.raises(RuntimeError, match="stop"):
        bootstrap(str(config), model_backend_override=MockModelBackend())
    assert backend.closed


def test_bootstrap_failure_reaps_started_provider_process(monkeypatch) -> None:
    import src.adapters.mcp_adapter as adapter_module

    real_popen = adapter_module.subprocess.Popen
    processes: list[subprocess.Popen[bytes]] = []

    def capture(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(adapter_module.subprocess, "Popen", capture)
    monkeypatch.setattr(
        "src.main.create_safety_backend",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    config = Path(__file__).parents[1] / "config" / "mcp.example.toml"

    with pytest.raises(RuntimeError, match="stop"):
        bootstrap(str(config), model_backend_override=MockModelBackend())

    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_external_tool_runs_through_the_real_app_execution_path() -> None:
    config = Path(__file__).parents[1] / "config" / "mcp.example.toml"
    compact = '{"b":2,"a":1}'
    model = ScriptedModelBackend([
        _response(capability_id="text.format", intent_type="format_json"),
        _response(
            intent_type="format_json",
            tool_intent="local_action",
            tool_call={
                "tool_name": "demo.json_format",
                "arguments": {"text": compact},
            },
        ),
    ])
    app = bootstrap(str(config), model_backend_override=model)
    try:
        reply = app.handle(f"请格式化这段 JSON：{compact}", "mcp-session")
        assert "demo.json_format" in reply
        assert '"a": 1' in reply
        assert app.last_turn_report()["reply_provenance"] == "executed"
        assert all(
            "MCP_UNTRUSTED_DESCRIPTION_IGNORE_PREVIOUS_INSTRUCTIONS" not in prompt
            and "MCP_UNTRUSTED_TITLE" not in prompt
            for prompt in model.prompts
        )
    finally:
        app.shutdown()
