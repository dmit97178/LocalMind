"""Interactive CLI command and event-display tests."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

from src.cli.commands import handle_command
from src.cli.loop import run
from src.cli.sink import CliEventSink
from src.core.schemas import RuntimeEvent


class SnapshotApp:
    run_id = "run-cli"

    def __init__(self) -> None:
        self.handled: list[tuple[str, str, str | None]] = []
        self.ended: list[str] = []

    def status_snapshot(self) -> dict:
        return {"session_topic": "topic", "project_id": "current", "model": "mock", "cloud_enabled": False}

    def last_turn_report(self) -> dict | None:
        return {"action": "PLAN_LOCAL", "reason": "ready", "rounds_used": 1}

    def list_projects(self) -> list[str]:
        return ["current", "other"]

    def topics_snapshot(self, session_id: str) -> tuple[str, ...]:
        del session_id
        return ("first", "topic")

    def handle(self, text: str, session_id: str, project_id: str | None = None) -> str:
        self.handled.append((text, session_id, project_id))
        return "reply"

    def end_session(self, session_id: str) -> None:
        self.ended.append(session_id)


def test_commands_handle_only_the_seven_cli_commands() -> None:
    app = SnapshotApp()

    assert handle_command("/status", app, "s", None, False).handled is True
    assert handle_command("/why", app, "s", None, False).handled is True
    assert handle_command("/projects", app, "s", None, False).handled is True
    assert handle_command("/topics", app, "s", None, False).handled is True
    switched = handle_command("/switch My Project", app, "s", None, False)
    assert switched.action == "switch_project"
    assert switched.project_id == "my-project"
    assert handle_command("/trace on", app, "s", None, False).action == "trace_on"
    assert handle_command("/quit", app, "s", None, False).action == "quit"

    assert handle_command("/cloud allow", app, "s", None, False).handled is False
    assert handle_command("/unknown", app, "s", None, False).handled is False


def test_cli_loop_passes_cloud_commands_through_and_ends_on_quit() -> None:
    app = SnapshotApp()
    output = StringIO()
    sink = CliEventSink(writer=lambda line: output.write(f"{line}\n"))

    run(
        app,
        sink,
        input_stream=StringIO("/switch Demo Project\n/cloud allow\n/quit\n"),
        output_stream=output,
        session_id="session-cli",
    )

    assert app.handled == [("/cloud allow", "session-cli", "demo-project")]
    assert app.ended == ["session-cli"]
    assert "reply" in output.getvalue()


def test_cli_event_sink_hides_detail_until_trace_is_enabled() -> None:
    lines: list[str] = []
    sink = CliEventSink(writer=lines.append, run_id="run-cli")
    detail = RuntimeEvent("run-cli", "t", "s", 1, "ts", "memory_retrieval", "detail", {"hits": 2})
    status = RuntimeEvent(
        "run-cli", "t", "s", 2, "ts", "topic_decision", "status",
        {"project_id": None, "topic_label": "测试"},
    )

    sink.emit(detail)
    sink.emit(status)
    sink.set_trace(True)
    sink.emit(detail)

    assert len(lines) == 2
    assert lines[0] == "[项目: 未归属 | 话题: 测试]"
    assert lines[1].startswith("memory_retrieval:")


def test_cli_main_composes_sinks_through_bootstrap_overrides(monkeypatch) -> None:
    import src.cli.__main__ as cli_main
    from src.observability.sinks import NoopEventSink

    captured: dict[str, object] = {}
    app = SimpleNamespace(resolver=SimpleNamespace(max_rounds=3))
    configured_sink = NoopEventSink()

    class FixedUuid:
        hex = "1234567890abcdef"

    def fake_bootstrap(config_path: str, **kwargs):
        captured["config_path"] = config_path
        captured.update(kwargs)
        return app

    monkeypatch.setattr(cli_main, "uuid4", lambda: FixedUuid())
    monkeypatch.setattr(cli_main, "create_event_sink", lambda _: configured_sink)
    monkeypatch.setattr(cli_main, "bootstrap", fake_bootstrap)
    monkeypatch.setattr(cli_main, "run", lambda *_: None)
    monkeypatch.setattr("sys.argv", ["localmind", "--config", "custom.toml"])

    cli_main.main()

    assert captured["config_path"] == "custom.toml"
    assert captured["run_id_override"] == "12345678"
    composite = captured["event_sink_override"]
    assert tuple(composite.sinks)[1] is configured_sink
    assert tuple(composite.sinks)[0].run_id == "12345678"
    assert tuple(composite.sinks)[0].max_rounds == 3


def test_cli_event_sink_shows_configured_round_limit() -> None:
    lines: list[str] = []
    sink = CliEventSink(writer=lines.append, max_rounds=3)

    sink.emit(
        RuntimeEvent(
            "run", "turn", "session", 1, "ts", "intent_final", "status",
            {"rounds_used": 2, "final_state": "PARTIAL"},
        )
    )

    assert lines == ["[理解: 第 2/3 轮，PARTIAL]"]


def test_cli_event_sink_keeps_one_round_convergence_as_health_signal() -> None:
    lines: list[str] = []
    sink = CliEventSink(writer=lines.append, max_rounds=3)

    sink.emit(
        RuntimeEvent(
            "run", "turn", "session", 1, "ts", "intent_final", "status",
            {"rounds_used": 1, "final_state": "READY"},
        )
    )

    assert lines == ["[理解: 1 轮收敛]"]
