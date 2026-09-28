"""Run the deterministic P0a mock demonstration."""

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
            "entities": {"message": "Hello LocalMind!"},
            "missing_info": [],
            "suggested_tools": ["system.echo"],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "system.echo", "arguments": {"message": "Hello LocalMind!"}},
            "risk_draft": "normal",
            "model_confidence": 0.85,
            "reasoning": "P0a demonstration.",
        }
    )
    app = bootstrap("config/p6_legacy.example.toml", model_backend_override=model)
    try:
        print(app.handle("echo hello", session_id="demo"))
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
