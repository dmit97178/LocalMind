"""Tests for the small main-loop components."""

from __future__ import annotations

from datetime import datetime

from src.core.interfaces import EvolutionBackend
from src.core.schemas import (
    CloudRequestPackage,
    IntentCandidate,
    LocalMindError,
    MinimalContext,
    Skill,
)


class RecordingEvolutionBackend(EvolutionBackend):
    def __init__(self) -> None:
        self.collect_calls: list[tuple[dict, str]] = []

    def reflect(self, task_context: dict) -> list:
        return []

    def get_skills(self, intent: str) -> list[Skill]:
        return []

    def collect_experience(self, task: dict, outcome: str) -> None:
        self.collect_calls.append((task, outcome))


def test_input_normalizer_strips_text_and_creates_cli_event() -> None:
    from src.core.input_normalizer import InputNormalizer

    event = InputNormalizer().normalize("  check port  ", "session-1", "project-1")

    assert event.text == "check port"
    assert event.session_id == "session-1"
    assert event.project_id == "project-1"
    assert event.source == "cli"
    assert datetime.fromisoformat(event.timestamp).tzinfo is not None


def test_input_normalizer_rejects_blank_input() -> None:
    from src.core.input_normalizer import InputNormalizer

    try:
        InputNormalizer().normalize(" \t\n", "session-1")
    except LocalMindError as exc:
        assert exc.code == "INVALID_INPUT"
        assert exc.recoverable is True
    else:
        raise AssertionError("InputNormalizer should reject blank input")


def test_task_planner_uses_structured_tool_call() -> None:
    from src.core.schemas import ToolCallDraft, ToolDef
    from src.core.task_planner import TaskPlanner

    tool = ToolDef(
        "system.echo",
        "Echo a message.",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )

    plan = TaskPlanner().plan(
        IntentCandidate(
            suggested_tools=["system.get_time"],
            entities={"message": "hello"},
            risk_draft="normal",
            tool_intent="local_action",
            tool_call=ToolCallDraft("system.echo", {"message": "hello"}),
            tool_call_resolution="resolved",
        ),
        MinimalContext(
            system_prompt="test", current_input="echo hello", tool_defs=(tool,)
        ),
    )

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "system.echo"
    assert step.action == "echo"
    assert step.params == {"message": "hello"}
    assert step.entities == step.params
    assert step.user_input == "echo hello"
    assert step.risk_level == "normal"


def test_response_builder_separates_display_from_memory_narrative() -> None:
    from src.core.response_builder import ResponseBuilder
    from src.core.schemas import ExecutionPlan, ExecutionStep

    output = ResponseBuilder().build(
        ExecutionPlan(steps=[ExecutionStep(tool_name="system.echo", action="echo")]),
        {0: {"message": "hello"}},
    )

    assert "system.echo" in output.display
    assert "hello" in output.display
    assert "执行结果 1 条" in output.narrative_reply
    assert "hello" not in output.narrative_reply


def test_reflection_recorder_is_noop_in_p0a() -> None:
    from src.core.reflection_recorder import ReflectionRecorder

    evolution = RecordingEvolutionBackend()
    ReflectionRecorder(evolution=evolution).record({"task": "echo"}, "ok")

    assert evolution.collect_calls == []


def test_noop_backends_return_contract_safe_empty_responses() -> None:
    from src.evolution.noop_backend import NoopEvolutionBackend
    from src.tools.cloud_advisory import NoopCloudAdvisoryBackend

    cloud = NoopCloudAdvisoryBackend()
    evolution = NoopEvolutionBackend()

    assert cloud.advise(
        CloudRequestPackage("task", "session", "noop", "advisory", "grant", [], "advice only", 1)
    ).analysis
    assert evolution.reflect({"task": "echo"}) == []
    assert evolution.get_skills("echo") == []
    assert evolution.collect_experience({"task": "echo"}, "ok") is None
