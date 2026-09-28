"""Regression tests for local narrative prompt priority."""

from __future__ import annotations

from types import SimpleNamespace

from src.main import App


class CapturingModel:
    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        del response_schema
        self.prompt = prompt
        return {"text": "ok"}


def test_local_reply_places_current_input_after_reference_context() -> None:
    model = CapturingModel()
    app = object.__new__(App)
    app.resolver = SimpleNamespace(model=model)
    context = SimpleNamespace(
        current_input="CURRENT_SOURCE_SENTINEL",
        relevant_history=("OLD_SUMMARY_SENTINEL",),
        project_state={"summary": "OLD_PROJECT_SENTINEL"},
    )

    assert app._build_local_reply(context) == "ok"

    assert model.prompt.index("OLD_SUMMARY_SENTINEL") < model.prompt.index(
        "CURRENT_SOURCE_SENTINEL"
    )
    assert model.prompt.index("OLD_PROJECT_SENTINEL") < model.prompt.index(
        "CURRENT_SOURCE_SENTINEL"
    )
    assert model.prompt.rstrip().endswith("CURRENT_SOURCE_SENTINEL")
