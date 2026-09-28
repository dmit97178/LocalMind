"""Run the P5 project-memory path without requiring a live local model."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from src.main import bootstrap
    from src.models.mock_backend import MockModelBackend

    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "echo_message",
            "entities": {"message": "P5 ready"},
            "missing_info": [],
            "suggested_tools": ["system.echo"],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "system.echo", "arguments": {"message": "P5 memory connected"}},
            "risk_draft": "normal",
            "model_confidence": 0.9,
        }
    )
    app = bootstrap("config/p6_legacy.example.toml", model_backend_override=model)
    try:
        reply = app.handle("记录 P5 项目进度", session_id="p5-demo", project_id="Demo Project")
        app.end_session("p5-demo")
        state = app.projects.load("demo-project")
        summary = app.memory.get_summary("conversation", "p5-demo") or {}

        print(reply)
        print(f"project={state.project_id if state is not None else ''}")
        print(f"summary={summary.get('summary', '')}")
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
