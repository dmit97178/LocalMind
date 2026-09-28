"""Thin read-eval loop for the LocalMind CLI."""

from __future__ import annotations

import sys
from typing import Protocol, TextIO

from src.cli.commands import CommandApp, handle_command
from src.cli.sink import CliEventSink
from src.cli.transcript import TranscriptStore


class LoopApp(CommandApp, Protocol):
    run_id: str | None

    def handle(self, text: str, session_id: str, project_id: str | None = None) -> str: ...
    def end_session(self, session_id: str) -> None: ...


def run(
    app: LoopApp,
    sink: CliEventSink,
    *,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    session_id: str | None = None,
    project_id: str | None = None,
    transcript: TranscriptStore | None = None,
    history_turns: int = 0,
) -> None:
    """Run until /quit or EOF, finalizing the session exactly once."""

    _configure_utf8(input_stream)
    _configure_utf8(output_stream)
    active_session = session_id or f"sess_cli_{app.run_id or 'local'}"
    bound_project = project_id
    output_stream.write("LocalMind 已启动。命令：/status /why /trace on|off /quit\n")
    if transcript is not None:
        history = transcript.read_recent(turns=history_turns)
        if history:
            for role, content in history:
                speaker = "你" if role == "user" else "LocalMind"
                output_stream.write(f"{speaker}：{content}\n")
    while True:
        line = input_stream.readline()
        if line == "":
            app.end_session(active_session)
            break
        text = line.rstrip("\r\n")
        if not text.strip():
            continue
        result = handle_command(text, app, active_session, bound_project, sink.trace_on)
        if result.handled:
            if result.action == "switch_project":
                bound_project = result.project_id
            elif result.action == "trace_on":
                sink.set_trace(True)
            elif result.action == "trace_off":
                sink.set_trace(False)
            elif result.action == "quit":
                app.end_session(active_session)
                if result.output:
                    output_stream.write(f"{result.output}\n")
                break
            if result.output:
                output_stream.write(f"{result.output}\n")
            continue
        reply = app.handle(text, active_session, bound_project)
        if transcript is not None:
            transcript.append("user", text)
            transcript.append("assistant", reply)
        output_stream.write(f"{reply}\n")


def _configure_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
