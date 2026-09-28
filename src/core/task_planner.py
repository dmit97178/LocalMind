"""P0a local task planner."""

from __future__ import annotations

from src.core.schemas import ExecutionPlan, ExecutionStep, IntentCandidate, MinimalContext
from src.core.tool_validation import validate_tool_call


class TaskPlanner:
    """Translate one model-suggested local tool into an execution plan."""

    def plan(self, candidate: IntentCandidate, context: MinimalContext) -> ExecutionPlan:
        if candidate.tool_call is None or candidate.tool_call_resolution != "resolved":
            return ExecutionPlan()
        validation = validate_tool_call(candidate.tool_call, context.tool_defs)
        if not validation.ok:
            return ExecutionPlan()
        tool_name = candidate.tool_call.tool_name
        return ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool_name=tool_name,
                    action=tool_name.rsplit(".", maxsplit=1)[-1],
                    params=dict(candidate.tool_call.arguments),
                    risk_level=candidate.risk_draft,
                    intent_type=candidate.intent_type,
                    entities=dict(candidate.entities),
                    user_input=context.current_input,
                )
            ]
        )
