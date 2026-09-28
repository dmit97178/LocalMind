"""Focused P3 safety-hardening tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.core.interfaces import SafetyBackend, ToolBackend
from src.core.schemas import (
    ExecutionPlan,
    ExecutionStep,
    Result,
    SafetyDenied,
    SafetyVerdict,
    ToolDef,
)


@dataclass
class AllowingSafetyBackend(SafetyBackend):
    operations: list[dict] = field(default_factory=list)

    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        self.operations.append(operation)
        return SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")


@dataclass
class SensitiveToolBackend(ToolBackend):
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="file.read",
                description="Read a file.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                risk_level="sensitive",
            )
        ]

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        self.calls.append((tool_name, params))
        return Result.ok({"content": "ok"})


def test_sensitive_step_requires_gate23_before_tool_execution() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    tool_backend = SensitiveToolBackend()
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(backend=AllowingSafetyBackend()),
    )

    with pytest.raises(SafetyDenied, match="confirmation") as error:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="file.read",
                        action="read",
                        params={"path": "notes.txt"},
                        risk_level="sensitive",
                        user_input="read notes.txt",
                    )
                ]
            )
        )

    assert error.value.code == "SAFETY_NECESSITY"
    assert tool_backend.calls == []
    assert executor.audit_log[0].verdict == "denied"


def test_sensitive_step_with_gate23_and_related_input_executes() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    tool_backend = SensitiveToolBackend()
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(backend=AllowingSafetyBackend()),
    )

    result = executor.execute(
        ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool_name="file.read",
                    action="read",
                    params={"path": "notes.txt"},
                    risk_level="sensitive",
                    user_input="read notes.txt",
                    gate23_passed=True,
                )
            ]
        )
    )

    assert result == {0: {"content": "ok"}}
    assert tool_backend.calls == [("file.read", {"path": "notes.txt"})]


def test_relevance_gate_blocks_unrelated_sensitive_params() -> None:
    from src.safety.policy import SafetyPolicy

    backend = AllowingSafetyBackend()
    policy = SafetyPolicy(backend=backend)

    with pytest.raises(SafetyDenied) as error:
        policy.check(
            ExecutionStep(
                tool_name="file.read",
                action="read",
                params={"path": "secrets.txt"},
                risk_level="sensitive",
                user_input="tell me the current time",
            )
        )

    assert error.value.code == "SAFETY_RELEVANCE"
    assert backend.operations == []


def test_executor_applies_registered_risk_before_relevance_gate() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    tool_backend = SensitiveToolBackend()
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(backend=AllowingSafetyBackend()),
    )

    with pytest.raises(SafetyDenied) as error:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="file.read",
                        action="read",
                        params={"path": "secrets.txt"},
                        risk_level="normal",
                        user_input="tell me the current time",
                        gate23_passed=True,
                    )
                ]
            )
        )

    assert error.value.code == "SAFETY_RELEVANCE"
    assert tool_backend.calls == []


def test_unknown_risk_level_is_treated_as_sensitive() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    tool_backend = SensitiveToolBackend()
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(backend=AllowingSafetyBackend()),
    )

    with pytest.raises(SafetyDenied) as error:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="file.read",
                        action="read",
                        params={"path": "notes.txt"},
                        risk_level="unrecognized",
                        user_input="read notes.txt",
                    )
                ]
            )
        )

    assert error.value.code == "SAFETY_NECESSITY"
    assert executor.audit_log[0].risk_level == "sensitive"
    assert tool_backend.calls == []
