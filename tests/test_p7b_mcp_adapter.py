from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from src.adapters.mcp_adapter import MCPStdioToolProvider
from src.tools.provider_declarations import EXTERNAL_PROVIDERS, resolve_provider_declarations


def _provider(*extra: str, handshake_timeout_ms: int = 2000, call_timeout_ms: int = 2000):
    declaration = resolve_provider_declarations((replace(
        EXTERNAL_PROVIDERS[0],
        argv=(sys.executable, "scripts/mcp_demo_server.py", *extra),
    ),))[0]
    return MCPStdioToolProvider(
        declaration,
        handshake_timeout_ms=handshake_timeout_ms,
        call_timeout_ms=call_timeout_ms,
    )


def _capture_processes(monkeypatch) -> list[subprocess.Popen[bytes]]:
    import src.adapters.mcp_adapter as adapter_module

    real_popen = adapter_module.subprocess.Popen
    processes: list[subprocess.Popen[bytes]] = []

    def capture(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(adapter_module.subprocess, "Popen", capture)
    return processes


def test_mcp_provider_handshake_and_call(monkeypatch) -> None:
    processes = _capture_processes(monkeypatch)
    provider = _provider()
    try:
        snapshot = provider.handshake()
        assert snapshot.healthy
        assert snapshot.candidates[0].raw_name == "json_format"
        assert provider.handshake() == snapshot
        result = provider.execute("json_format", {"text": '{"b":2,"a":1}'})
        assert result.is_ok
        assert result.value == {"text": '{\n  "a": 1,\n  "b": 2\n}'}
    finally:
        provider.close()
    assert provider.diagnostics()["closed"] is True
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_mcp_provider_does_not_inherit_arbitrary_environment(monkeypatch) -> None:
    monkeypatch.setenv("LOCALMIND_TEST_SECRET_RANDOM", "must-not-cross")
    provider = _provider("--dump-env")
    try:
        assert provider.handshake().healthy
        result = provider.execute("json_format", {"text": "{}"})
        assert result.is_ok and result.value is not None
        keys = json.loads(result.value["text"])
        allowed = {
            "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
            "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
            "PYTHONIOENCODING", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE",
        }
        assert set(keys) <= allowed
        assert "LOCALMIND_TEST_SECRET_RANDOM" not in keys
        assert "PATH" not in keys
    finally:
        provider.close()


def test_mcp_provider_rejects_bad_version_without_breaking_bootstrap() -> None:
    provider = _provider("--fault", "bad_version")
    try:
        snapshot = provider.handshake()
        assert not snapshot.healthy
        assert snapshot.failure_reason == "protocol_version_unsupported"
    finally:
        provider.close()


def test_mcp_provider_timeout_invalidates_stream(monkeypatch) -> None:
    processes = _capture_processes(monkeypatch)
    provider = _provider("--fault", "hang", handshake_timeout_ms=100)
    try:
        snapshot = provider.handshake()
        assert not snapshot.healthy
        assert snapshot.failure_reason == "timeout"
        assert provider.diagnostics()["timeout_count"] == 1
    finally:
        provider.close()
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_call_timeout_discards_late_reply_and_reaps_process(monkeypatch) -> None:
    processes = _capture_processes(monkeypatch)
    provider = _provider("--fault", "late_reply", call_timeout_ms=100)
    try:
        assert provider.handshake().healthy
        first = provider.execute("json_format", {"text": "{}"})
        assert first.is_err and first.error is not None
        assert first.error.details["reason"] == "provider_timeout"
        assert provider.diagnostics()["failure_reason"] == "timeout"
        second = provider.execute("json_format", {"text": "{}"})
        assert second.is_err and second.error is not None
        assert second.error.details["reason"] == "provider_unreachable"
        assert provider.diagnostics()["failure_reason"] == "timeout"
    finally:
        provider.close()
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_mcp_provider_unsupported_content_keeps_provider_healthy() -> None:
    provider = _provider("--fault", "non_text_content")
    try:
        assert provider.handshake().healthy
        result = provider.execute("json_format", {"text": "{}"})
        assert not result.is_ok
        assert result.error is not None
        assert result.error.details["reason"] == "provider_unsupported_content"
        assert provider.diagnostics()["healthy"] is True
        assert provider.diagnostics()["unsupported_content_count"] == 1
    finally:
        provider.close()


def test_mcp_provider_ignores_notification_and_keeps_id_correlation() -> None:
    provider = _provider("--fault", "no_id")
    try:
        assert provider.handshake().healthy
        result = provider.execute("json_format", {"text": "{}"})
        assert result.is_ok
        assert provider.diagnostics()["unhandled_notifications"] >= 2
    finally:
        provider.close()


def test_mcp_provider_maps_parse_oversize_and_tool_errors() -> None:
    cases = (
        ("garbage", "protocol"),
        ("oversize", "oversize"),
    )
    for fault, expected_health in cases:
        provider = _provider("--fault", fault)
        try:
            snapshot = provider.handshake()
            assert not snapshot.healthy
            assert snapshot.failure_reason == expected_health
        finally:
            provider.close()

    provider = _provider("--fault", "iserror")
    try:
        assert provider.handshake().healthy
        result = provider.execute("json_format", {"text": "{}"})
        assert not result.is_ok and result.error is not None
        assert result.error.details["reason"] == "tool_reported_error"
        assert result.error.details["content_items"] == 1
        assert result.error.details["content_length"] == len("private failure")
        assert provider.diagnostics()["healthy"] is True
    finally:
        provider.close()


def test_mcp_provider_stderr_noise_cannot_block_call() -> None:
    provider = _provider("--fault", "noisy_stderr")
    try:
        assert provider.handshake().healthy
        assert provider.execute("json_format", {"text": "{}"}).is_ok
    finally:
        provider.close()


def test_provider_argv_shell_metacharacters_arrive_as_literal_data() -> None:
    provider = _provider("--dump-argv", "literal;a|b&c")
    try:
        assert provider.handshake().healthy
        result = provider.execute("json_format", {"text": "{}"})
        assert result.is_ok and result.value is not None
        argv = json.loads(result.value["text"])["argv"]
        assert "literal;a|b&c" in argv
    finally:
        provider.close()


def test_transport_source_never_inherits_environment_or_uses_a_shell() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "adapters" / "mcp_adapter.py"
    ).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "stderr=subprocess.DEVNULL" in source
    assert "shell=False" in source


def test_boolean_response_id_is_a_protocol_error() -> None:
    provider = _provider("--fault", "bool_id")
    try:
        snapshot = provider.handshake()
        assert not snapshot.healthy
        assert snapshot.failure_reason == "protocol"
    finally:
        provider.close()


def test_tool_list_diagnostics_cover_pagination_and_malformed_entries() -> None:
    cases = (("pagination", "pagination_ignored"), ("malformed_tool", "malformed_tool_entries"))
    for fault, metric in cases:
        provider = _provider("--fault", fault)
        try:
            assert provider.handshake().healthy
            assert provider.diagnostics()[metric] == 1
        finally:
            provider.close()


def test_process_death_and_sigterm_faults_are_reaped(monkeypatch) -> None:
    for fault in ("die", "ignore_sigterm"):
        processes = _capture_processes(monkeypatch)
        provider = _provider("--fault", fault)
        assert provider.handshake().healthy
        if fault == "die":
            result = provider.execute("json_format", {"text": "{}"})
            assert result.is_err
        provider.close()
        assert len(processes) == 1
        assert processes[0].poll() is not None
        assert provider.diagnostics()["close_forced"] is (os.name != "nt" and fault == "ignore_sigterm")
