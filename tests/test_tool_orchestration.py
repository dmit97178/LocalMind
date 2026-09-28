"""Contract tests for structured local-tool orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.core.schemas import (
    IntentCandidate,
    LocalMindError,
    MinimalContext,
    ToolCallDraft,
    ToolContext,
    ToolDef,
)


def _tool(name: str = "system.echo") -> ToolDef:
    return ToolDef(
        name=name,
        description="Echo text.",
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )


def _reject_today(value: str) -> bool:
    return value != "today"


@pytest.mark.parametrize(
    ("payload", "intent", "resolution", "conflict", "has_call", "failure_reason"),
    [
        ({}, "none", "absent", False, False, None),
        ({"tool_intent": "none", "tool_call": None}, "none", "absent", False, False, None),
        ({"tool_intent": "local_action"}, "local_action", "absent", False, False, "tool_call_missing"),
        ({"tool_intent": "bogus"}, "local_action", "absent", False, False, "tool_call_missing"),
        ({"tool_intent": "none", "tool_call": []}, "local_action", "invalid_shape", True, False, "tool_call_invalid_shape"),
        ({"tool_call": {"tool_name": "system.echo", "arguments": {"message": "hi"}}}, "local_action", "resolved", False, True, None),
        ({"tool_intent": "none", "tool_call": {"tool_name": "system.echo", "arguments": {"message": "hi"}}}, "local_action", "resolved", True, True, None),
        ({"tool_call": {"tool_name": "missing", "arguments": {}}}, "local_action", "unknown_tool", False, False, "unknown_tool"),
        ({"tool_call": [{"tool_name": "system.echo", "arguments": {}}]}, "local_action", "multiple_proposed", False, False, "multiple_proposed"),
        ({"tool_call": {"tool_name": "system.echo", "arguments": []}}, "local_action", "invalid_shape", False, False, "tool_call_invalid_shape"),
    ],
)
def test_tool_call_normalization_truth_table(
    payload: dict,
    intent: str,
    resolution: str,
    conflict: bool,
    has_call: bool,
    failure_reason: str | None,
) -> None:
    from src.core.control_policy import ControlPolicy
    from src.core.intent_resolver import _candidate_from_model_output

    raw = {
        "state": "READY",
        "intent_type": "test",
        "entities": {},
        "missing_info": [],
        "risk_draft": "normal",
        "model_confidence": 0.9,
        **payload,
    }
    candidate = _candidate_from_model_output(raw, (_tool(),))

    assert candidate.tool_intent == intent
    assert candidate.tool_call_resolution == resolution
    assert candidate.tool_intent_conflict is conflict
    assert (candidate.tool_call is not None) is has_call
    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        tool_defs=(_tool(),),
    )
    if failure_reason is not None:
        assert action.reason == failure_reason
    else:
        assert action.reason not in {
            "tool_call_missing",
            "unknown_tool",
            "multiple_proposed",
            "tool_call_invalid_shape",
        }


def test_tool_validator_rejects_bool_for_integer_and_unknown_arguments() -> None:
    from src.core.tool_validation import validate_tool_call

    tool = ToolDef(
        "math.repeat",
        "Repeat text.",
        {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["count", "text"],
        },
    )

    wrong_type = validate_tool_call(
        ToolCallDraft("math.repeat", {"count": True, "text": "x"}), (tool,)
    )
    unknown = validate_tool_call(
        ToolCallDraft("math.repeat", {"count": 2, "text": "x", "extra": 1}),
        (tool,),
    )

    assert wrong_type.ok is False and wrong_type.reason == "param_type"
    assert wrong_type.offending == ("count",)
    assert unknown.ok is False and unknown.reason == "param_unknown_key"
    assert unknown.offending == ("extra",)


def test_tool_validator_treats_rejected_instance_as_missing() -> None:
    from src.core.schemas import ParamInstanceCheck
    from src.core.tool_validation import validate_tool_call

    tool = ToolDef(
        "demo.lookup",
        "Lookup a place.",
        {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
        param_instance_checks={
            "location": ParamInstanceCheck(_reject_today),
        },
    )

    result = validate_tool_call(
        ToolCallDraft("demo.lookup", {"location": "today"}), (tool,),
    )

    assert result.ok is False
    assert result.reason == "param_missing"
    assert result.missing == ("location",)
    assert result.instance_rejected == ("location",)


def test_tool_catalog_rejects_invalid_instance_check_declaration() -> None:
    from src.core.schemas import ParamInstanceCheck
    from src.core.tool_validation import validate_tool_catalog

    tool = replace(
        _tool(),
        param_instance_checks={"missing": ParamInstanceCheck(str.isalpha)},
    )

    with pytest.raises(LocalMindError) as caught:
        validate_tool_catalog((tool,))

    assert caught.value.code == "CONFIG_ERROR"
    assert caught.value.details["reason"] == "param_instance_declaration_invalid"


def test_tool_catalog_rejects_non_check_instance_declaration() -> None:
    from src.core.tool_validation import validate_tool_catalog

    tool = replace(_tool(), param_instance_checks={"message": object()})  # type: ignore[dict-item]

    with pytest.raises(LocalMindError) as caught:
        validate_tool_catalog((tool,))

    assert caught.value.details["reason"] == "param_instance_declaration_invalid"


def test_control_policy_exposes_missing_tool_catalog_without_crashing() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="READY",
        intent_type="write",
        risk_draft="normal",
        model_confidence=0.9,
        tool_intent="local_action",
        tool_call=ToolCallDraft("system.echo", {"message": "hi"}),
        tool_call_resolution="resolved",
    )

    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        tool_defs=None,
    )

    assert action.action == "PLAN_LOCAL"
    assert action.reason == "tool_catalog_absent"

    empty_catalog = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        tool_defs=(),
    )
    assert empty_catalog.reason == "unknown_tool"


def test_task_planner_uses_only_structured_tool_call_arguments() -> None:
    from src.core.task_planner import TaskPlanner

    tool = _tool()
    candidate = IntentCandidate(
        state="READY",
        intent_type="echo",
        entities={"message": "entity-value", "unexpected": "ignored"},
        suggested_tools=["missing.tool"],
        risk_draft="normal",
        model_confidence=0.9,
        tool_intent="local_action",
        tool_call=ToolCallDraft("system.echo", {"message": "draft-value"}),
        tool_call_resolution="resolved",
    )
    context = MinimalContext("system", tool_defs=(tool,))

    plan = TaskPlanner().plan(candidate, context)

    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "system.echo"
    assert plan.steps[0].params == {"message": "draft-value"}


def test_catalog_validation_rejects_unsupported_schema_keyword() -> None:
    from src.core.schemas import LocalMindError
    from src.core.tool_validation import validate_tool_catalog

    invalid = replace(
        _tool(),
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string", "maxLength": 5}},
            "required": ["message"],
        },
    )

    with pytest.raises(LocalMindError) as caught:
        validate_tool_catalog((invalid,))

    assert caught.value.code == "CONFIG_ERROR"
    assert caught.value.details == {"reason": "tool_schema_invalid", "tool_name": "system.echo"}


@pytest.mark.parametrize(
    ("tools", "reason"),
    [
        (tuple(_tool(f"demo.{index}") for index in range(33)), "tool_catalog_too_large"),
        ((_tool(), _tool()), "tool_catalog_duplicate"),
        ((replace(_tool(), description="x" * 9000),), "tool_catalog_too_large"),
    ],
)
def test_catalog_validation_rejects_unbounded_or_duplicate_catalogs(
    tools: tuple[ToolDef, ...], reason: str
) -> None:
    from src.core.tool_validation import validate_tool_catalog

    with pytest.raises(LocalMindError) as caught:
        validate_tool_catalog(tools)

    assert caught.value.code == "CONFIG_ERROR"
    assert caught.value.details["reason"] == reason


def test_catalog_limit_errors_include_the_measured_limit() -> None:
    from src.core.tool_validation import validate_tool_catalog

    with pytest.raises(LocalMindError) as count_error:
        validate_tool_catalog(tuple(_tool(f"demo.{index}") for index in range(33)))
    with pytest.raises(LocalMindError) as byte_error:
        validate_tool_catalog((replace(_tool(), description="x" * 9000),))

    assert count_error.value.details["tool_count"] == 33
    assert "catalog_bytes" not in count_error.value.details
    assert byte_error.value.details["catalog_bytes"] > 8192
    assert "tool_count" not in byte_error.value.details


def test_tool_call_validation_fails_closed_for_unvalidated_schema() -> None:
    from src.core.tool_validation import validate_tool_call

    malformed = replace(_tool(), parameters={"type": "object"})

    result = validate_tool_call(
        ToolCallDraft("system.echo", {"message": "hello"}),
        (malformed,),
    )

    assert result.ok is False
    assert result.reason == "param_type"


def test_response_schema_and_prompt_use_the_same_complete_catalog() -> None:
    from src.core.intent_resolver import _build_prompt, _intent_response_schema

    tool = _tool()
    context = MinimalContext("system", current_input="echo hi", tool_defs=(tool,))

    schema = _intent_response_schema(context.tool_defs)
    prompt = _build_prompt(context, [], None, 1, None)

    assert schema["properties"]["tool_call"]["properties"]["tool_name"]["enum"] == [
        "system.echo"
    ]
    assert {"tool_intent", "tool_call"} <= set(schema["required"])
    assert '"required":["message"]' in prompt
    assert '"risk_level":"normal"' in prompt
    assert '"tool_intent": "local_action"' in prompt
    assert '"tool_call": {"tool_name": "system.echo"' in prompt


def test_tool_call_arguments_may_be_omitted_as_empty_object() -> None:
    from src.core.intent_resolver import _candidate_from_model_output

    tool = ToolDef(
        "system.get_time",
        "Get time.",
        {"type": "object", "properties": {}, "required": []},
    )
    candidate = _candidate_from_model_output(
        {
            "state": "READY",
            "intent_type": "get_time",
            "entities": {},
            "missing_info": [],
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "tool_call": {"tool_name": "system.get_time"},
        },
        (tool,),
    )

    assert candidate.tool_call == ToolCallDraft("system.get_time", {})
    assert candidate.tool_call_resolution == "resolved"


@pytest.mark.parametrize(
    "raw_path",
    [
        "../outside.md",
        str(Path.cwd().anchor + "outside.md"),
        "~/outside.md",
        r"\\server\share\outside.md",
        r"C:\outside.md",
    ],
)
@pytest.mark.parametrize("tool_name", ["file.read", "file.list_dir", "file.write"])
def test_all_file_tools_share_workspace_escape_boundary(
    tmp_path: Path,
    raw_path: str,
    tool_name: str,
) -> None:
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})
    params = {"path": raw_path}
    if tool_name == "file.write":
        params["content"] = "blocked"

    report = backend.preflight(tool_name, params)
    result = backend.execute(tool_name, params)

    assert report.effective_risk == "dangerous"
    assert report.reason == "workspace_escape"
    assert result.is_err and result.error is not None
    assert result.error.code == "FILE_ERROR"
    assert result.error.details == {"reason": "workspace_escape"}


def test_preflight_rejects_malformed_path_as_file_error(tmp_path: Path) -> None:
    from src.core.schemas import ToolError
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend({"workspace_root": str(tmp_path)})

    with pytest.raises(ToolError) as caught:
        backend.preflight("file.read", {"path": "a\0b"})

    assert caught.value.code == "FILE_ERROR"
    assert caught.value.details == {"reason": "path_type"}


def test_registered_dummy_tool_needs_no_orchestrator_branch(monkeypatch, tmp_path: Path) -> None:
    from src.core.intent_resolver import _build_prompt, _intent_response_schema
    from src.core.task_planner import TaskPlanner
    from src.tools.builtin_backend import BuiltinToolBackend
    from src.tools.registry import BUILTIN_TOOLS, RegisteredTool

    definition = ToolDef(
        "demo.upper",
        "Uppercase text.",
        {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )

    def upper(params: dict, context: ToolContext) -> dict:
        assert context.tool_def is definition
        return {"text": str(params["text"]).upper()}

    monkeypatch.setitem(BUILTIN_TOOLS, "demo.upper", RegisteredTool(definition, upper))
    backend = BuiltinToolBackend(
        {"whitelist": ["demo.upper"], "workspace_root": str(tmp_path)}
    )
    context = MinimalContext("system", current_input="uppercase hi", tool_defs=(definition,))
    candidate = IntentCandidate(
        state="READY",
        intent_type="uppercase",
        risk_draft="normal",
        model_confidence=0.9,
        tool_intent="local_action",
        tool_call=ToolCallDraft("demo.upper", {"text": "hi"}),
        tool_call_resolution="resolved",
    )

    plan = TaskPlanner().plan(candidate, context)
    result = backend.execute(plan.steps[0].tool_name, plan.steps[0].params)
    prompt = _build_prompt(context, [], None, 1, None)
    schema = _intent_response_schema(context.tool_defs)

    assert [tool.name for tool in backend.list_tools()] == ["demo.upper"]
    assert "demo.upper" in prompt
    assert schema["properties"]["tool_call"]["properties"]["tool_name"]["enum"] == [
        "demo.upper"
    ]
    assert result.value == {"text": "HI"}
    from src.tools.capabilities import BUILTIN_CAPABILITIES
    from src.tools.registry import BUILTIN_TOOLS

    declared_names = (*BUILTIN_TOOLS, *(item.capability_id for item in BUILTIN_CAPABILITIES))
    for path in (
        Path("src/main.py"),
        Path("src/core/task_planner.py"),
        Path("src/core/control_policy.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert all(f'"{name}"' not in source and f"'{name}'" not in source for name in declared_names)
    assert '== "file.write"' not in Path("src/tools/builtin_backend.py").read_text(
        encoding="utf-8"
    )


def test_guarded_executor_revalidates_step_parameters_before_preflight() -> None:
    from src.core.schemas import ExecutionPlan, ExecutionStep, ToolError
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy
    from src.safety.rule_only_backend import RuleOnlySafetyBackend
    from src.tools.builtin_backend import BuiltinToolBackend

    backend = BuiltinToolBackend()
    executor = GuardedToolExecutor(
        backend,
        SafetyPolicy(RuleOnlySafetyBackend()),
    )

    with pytest.raises(ToolError) as caught:
        executor.execute(
            ExecutionPlan(
                [ExecutionStep("system.echo", "echo", {"message": 42})]
            )
        )

    assert caught.value.code == "TOOL_PARAM_ERROR"
    assert caught.value.details["reason"] == "param_type"
