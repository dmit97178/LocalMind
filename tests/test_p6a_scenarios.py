"""P6a application scenarios spanning events, CLI state, and file writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

from src.core.schemas import RuntimeEvent
from src.models.mock_backend import MockModelBackend
from src.safety.identity import IdentityVerifier

_DEFAULT_CONFIG = Path(__file__).parents[1] / "config" / "p6_legacy.example.toml"


@dataclass
class RecordingSink:
    events: list[RuntimeEvent] = field(default_factory=list)

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


def _write_model(path: str, content: str) -> MockModelBackend:
    return MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "write_file",
            "entities": {"path": path, "content": content},
            "missing_info": [],
            "suggested_tools": ["file.write"],
            "tool_intent": "local_action",
            "tool_call": {
                "tool_name": "file.write",
                "arguments": {"path": path, "content": content},
            },
            "risk_draft": "normal",
            "model_confidence": 0.95,
            "reasoning": "write requested",
        }
    )


def _file_app(tmp_path: Path, *, path: str = "notes.txt", content: str = "你好"):
    from src.main import bootstrap

    sink = RecordingSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=_write_model(path, content),
        event_sink_override=sink,
    )
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.safety.backend.workspace_root = tmp_path  # type: ignore[attr-defined]
    return app, sink


def test_new_file_write_requires_confirmation_and_emits_metadata_only(
    tmp_path: Path,
) -> None:
    app, sink = _file_app(tmp_path, content="private-value")

    reply = app.handle("写入笔记", "session-write")

    assert "确认" in reply
    assert not (tmp_path / "notes.txt").exists()
    assert app._pending_preflight is not None
    assert app._pending_preflight.requires_confirmation is True
    assert app._pending_preflight.target_exists is False
    assert not any(event.stage == "tool_execution" for event in sink.events)
    assert "private-value" not in repr(app.executor.audit_log)


def test_existing_file_is_promoted_to_confirmation(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    app, _ = _file_app(tmp_path, content="new")

    reply = app.handle("覆盖笔记", "session-write")

    assert "覆盖" in reply
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "old"
    assert app._pending_preflight is not None
    assert app._pending_preflight.target_exists is True


def test_confirmation_rejects_when_target_state_changed(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")
    app, sink = _file_app(tmp_path, content="new")
    verifier = IdentityVerifier({"hash_file": str(tmp_path / ".passphrase")})
    verifier.set_passphrase("local-secret")
    app.id_verifier = verifier
    assert "覆盖" in app.handle("覆盖 notes.txt", "session-write")
    target.unlink()

    reply = app.handle("确认 local-secret", "session-write")

    assert "文件状态已变化" in reply
    assert target.exists() is False
    assert app.executor.audit_log[-1].reason == "target_state_changed"
    turn_events = [event for event in sink.events if event.turn_id is not None]
    assert any(
        event.stage == "dispatch_decision" and event.data["reason"] == "confirmation_verified"
        for event in turn_events
    )
    confirmation_dispatch = next(
        event
        for event in turn_events
        if event.stage == "dispatch_decision"
        and event.data["reason"] == "confirmation_verified"
    )
    assert confirmation_dispatch.data["proposal_gate_result"] == "not_evaluated"
    assert confirmation_dispatch.data["proposal_denied_reason"] == "none"
    assert confirmation_dispatch.data["reference_guard_result"] == "not_evaluated"
    assert "local-secret" not in repr([event.data for event in turn_events])


def test_confirmed_overwrite_keeps_sensitive_audit_and_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")
    app, sink = _file_app(tmp_path, content="new-private-value")
    verifier = IdentityVerifier({"hash_file": str(tmp_path / ".passphrase")})
    verifier.set_passphrase("local-secret")
    app.id_verifier = verifier

    assert "覆盖" in app.handle("覆盖 notes.txt", "session-write")
    reply = app.handle("确认 local-secret", "session-write")

    assert "bytes_written" in reply
    assert target.read_text(encoding="utf-8") == "new-private-value"
    audit = app.executor.audit_log[-1]
    assert audit.verdict == "allowed"
    assert audit.risk_level == "sensitive"
    assert audit.reason == "target_exists"
    assert "new-private-value" not in repr(audit.params_redacted)
    assert "local-secret" not in repr([event.data for event in sink.events])


def test_new_file_preflight_rejects_when_external_creation_changes_target(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    app, _ = _file_app(tmp_path)
    verifier = IdentityVerifier({"hash_file": str(tmp_path / ".passphrase")})
    verifier.set_passphrase("local-secret")
    app.id_verifier = verifier
    assert "确认" in app.handle("写入 notes.txt", "session-write")
    target.write_text("external", encoding="utf-8")

    reply = app.handle("确认 local-secret", "session-write")

    assert "文件状态已变化" in reply
    assert target.read_text(encoding="utf-8") == "external"
    assert app.executor.audit_log[-1].reason == "target_state_changed"


def test_dangerous_preflight_is_audited_without_tool_execution(tmp_path: Path) -> None:
    app, _ = _file_app(tmp_path, path="../outside.txt")

    reply = app.handle("写入 ../outside.txt", "session-write")

    assert "安全策略拒绝" in reply
    assert app.executor.audit_log[-1].verdict == "denied"
    assert app.executor.audit_log[-1].reason == "workspace_escape"
    assert not (tmp_path.parent / "outside.txt").exists()


def test_snapshot_methods_do_not_mutate_state() -> None:
    app, _ = _file_app(Path.cwd())
    before = (app._event_seq, app._pending_plan, app.topics.topics_history("session"))

    assert app.last_turn_report() is None
    app.status_snapshot()
    app.list_projects()
    app.topics_snapshot("session")

    assert (app._event_seq, app._pending_plan, app.topics.topics_history("session")) == before


def test_end_session_emits_session_event_without_turn_id() -> None:
    app, sink = _file_app(Path.cwd())

    app.end_session("session-end")

    event = sink.events[-1]
    assert event.stage == "session_ended"
    assert event.turn_id is None
    assert event.data == {"summary_written": False}


def test_cli_switch_drives_real_project_turn_and_state_commands(tmp_path: Path) -> None:
    from src.cli.loop import run
    from src.cli.sink import CliEventSink

    app, _ = _file_app(tmp_path)
    output = StringIO()
    cli_sink = CliEventSink(writer=lambda line: output.write(f"{line}\n"))

    run(
        app,
        cli_sink,
        input_stream=StringIO(
            "/switch Demo Project\n写入 notes.txt\n/why\n/status\n/projects\n/topics\n/quit\n"
        ),
        output_stream=output,
        session_id="session-cli-real",
    )

    memory = app.memory.retrieve("写入", project_id="demo-project")
    assert memory.is_ok and memory.value
    rendered = output.getvalue()
    assert "已绑定项目：demo-project" in rendered
    assert "上轮动作=PLAN_LOCAL" in rendered
    assert "当前项目=demo-project" in rendered
    assert "demo-project（当前绑定）" in rendered
    assert "话题：" in rendered


def test_runtime_events_sanitize_user_and_model_text_slots() -> None:
    from src.main import bootstrap

    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    sink = RecordingSink()
    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": f"api_key={secret}",
            "entities": {"message": "safe"},
            "missing_info": [],
            "suggested_tools": ["system.echo"],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "system.echo", "arguments": {"message": "safe"}},
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "reasoning": secret,
        }
    )
    app = bootstrap(
        str(_DEFAULT_CONFIG), model_backend_override=model, event_sink_override=sink
    )

    app.handle(f"api_key={secret}", "session-private")

    assert secret not in repr([event.data for event in sink.events])
    assert secret not in repr(app.last_turn_report())
    assert not any(event.stage == "degradation" for event in sink.events)
