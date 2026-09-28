"""Launch LocalMind's interactive CLI with ``python -m src.cli``."""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from src.cli.loop import run
from src.cli.sink import CliEventSink
from src.cli.transcript import TranscriptStore
from src.main import bootstrap, create_event_sink
from src.observability.sinks import CompositeEventSink


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="LocalMind interactive CLI")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parents[2] / "config" / "default.toml"),
    )
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--transcript", default=None)
    parser.add_argument("--history-turns", type=int, default=0)
    args = parser.parse_args(argv)
    if args.history_turns < 0:
        parser.error("--history-turns must be non-negative")
    run_id = uuid4().hex[:8]
    configured_sink = create_event_sink(args.config)
    cli_sink = CliEventSink(run_id=run_id)
    app = bootstrap(
        args.config,
        event_sink_override=CompositeEventSink((cli_sink, configured_sink)),
        run_id_override=run_id,
    )
    try:
        cli_sink.max_rounds = app.resolver.max_rounds
        if any(
            value is not None
            for value in (args.session_id, args.project_id, args.transcript)
        ) or args.history_turns:
            run(
                app,
                cli_sink,
                session_id=args.session_id,
                project_id=args.project_id,
                transcript=TranscriptStore(args.transcript) if args.transcript else None,
                history_turns=args.history_turns,
            )
        else:
            run(app, cli_sink)
    finally:
        shutdown = getattr(app, "shutdown", None)
        if callable(shutdown):
            shutdown()


if __name__ == "__main__":
    main()
