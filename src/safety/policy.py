"""Safety policy orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.core.interfaces import SafetyBackend
from src.core.schemas import ExecutionStep, SafetyDenied, SafetyVerdict
from src.core.text_utils import tokenize


@dataclass(frozen=True)
class SafetyPolicy:
    """Apply configured safety backend checks to execution steps."""

    backend: SafetyBackend

    def check(self, step: ExecutionStep) -> SafetyVerdict:
        """Check one execution step before a tool backend can run it."""

        if step.risk_level in {"sensitive", "dangerous"} and not _is_relevant(step):
            raise SafetyDenied(
                code="SAFETY_RELEVANCE",
                message=f"Sensitive step is unrelated to input: {step.tool_name}",
                user_message="此操作与当前任务无关，已阻止。",
                recoverable=False,
                details={"tool_name": step.tool_name, "risk_level": step.risk_level},
            )

        return self.backend.check_dangerous(
            {
                "tool_name": step.tool_name,
                "action": step.action,
                "params": dict(step.params),
                "risk_level": step.risk_level,
                "intent_type": step.intent_type,
                "entities": dict(step.entities),
                "user_input": step.user_input,
            }
        )


def _is_relevant(step: ExecutionStep) -> bool:
    """Require a sensitive parameter value to be grounded in the raw request."""

    input_tokens = tokenize(step.user_input)
    parameter_tokens = tokenize(" ".join(_string_values(step.params)))
    return bool(input_tokens.intersection(parameter_tokens))


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _string_values(nested)]
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [item for nested in value for item in _string_values(nested)]
    return []
