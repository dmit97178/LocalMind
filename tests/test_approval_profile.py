"""Approval-profile boundary tests for high-impact tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.core.interfaces import SafetyBackend, ToolBackend
from src.core.schemas import (
    ExecutionPlan,
    ExecutionStep,
    PreflightReport,
    Result,
    SafetyDenied,
    SafetyVerdict,
    ToolDef,
)
from src.safety.guarded_executor import GuardedToolExecutor
from src.safety.policy import SafetyPolicy


@dataclass
class ProfileToolBackend(ToolBackend):
    static_profile: str = "standard"
    dynamic_profile: str = "standard"
    dynamic_risk: str = "normal"
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                "system.echo",
                "Echo a message.",
                {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
                "normal",
                self.static_profile,
            )
        ]

    def preflight(self, tool_name: str, params: dict) -> PreflightReport:
        del tool_name, params
        return PreflightReport(
            effective_risk=self.dynamic_risk,
            requires_confirmation=self.dynamic_risk in {"sensitive", "dangerous"},
            approval_profile=self.dynamic_profile,
        )

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        self.calls.append((tool_name, params))
        return Result.ok({"message": params.get("message", "")})


@dataclass
class AllowSafetyBackend(SafetyBackend):
    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        del operation
        return SafetyVerdict(True, "normal", "allowed")


def _executor(backend: ProfileToolBackend) -> GuardedToolExecutor:
    return GuardedToolExecutor(backend, SafetyPolicy(AllowSafetyBackend()), [])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("standard", "standard"),
        (" high_impact ", "high_impact"),
        ("HIGH_IMPACT", "high_impact"),
        (None, "high_impact"),
        (42, "high_impact"),
        ("", "high_impact"),
        ("critical", "high_impact"),
        ("low", "high_impact"),
    ],
)
def test_read_approval_profile_is_closed_and_fail_closed(raw: object, expected: str) -> None:
    from src.core.risk_vocabulary import APPROVAL_PROFILES, read_approval_profile

    result = read_approval_profile(raw)

    assert result == expected
    assert result in APPROVAL_PROFILES


@pytest.mark.parametrize(
    ("step_profile", "static_profile", "dynamic_profile"),
    [
        ("standard", "high_impact", "standard"),
        ("high_impact", "standard", "standard"),
        ("standard", "standard", "high_impact"),
    ],
)
def test_preflight_profile_sources_only_raise_the_plan_profile(
    step_profile: str,
    static_profile: str,
    dynamic_profile: str,
) -> None:
    backend = ProfileToolBackend(static_profile, dynamic_profile)
    report = _executor(backend).preflight(
        ExecutionPlan(
            [
                ExecutionStep(
                    "system.echo",
                    "echo",
                    {"message": "hello"},
                    approval_profile=step_profile,
                )
            ]
        )
    )

    assert report.approval_profile == "high_impact"
    assert report.requires_confirmation is False
    assert backend.calls == []


@pytest.mark.parametrize("risk_level", ["normal", "sensitive"])
def test_execute_rejects_high_impact_before_tool_execution(risk_level: str) -> None:
    backend = ProfileToolBackend(dynamic_risk=risk_level)
    executor = _executor(backend)
    plan = ExecutionPlan(
        [
            ExecutionStep(
                "system.echo",
                "echo",
                {"message": "hello"},
                risk_level=risk_level,
                gate23_passed=True,
                approval_profile="high_impact",
            )
        ]
    )

    with pytest.raises(SafetyDenied) as captured:
        executor.execute(plan, "task-1", "intent-1")

    assert captured.value.code == "SAFETY_IMPACT_CLOSED"
    assert backend.calls == []
    assert executor.audit_log is not None
    assert executor.audit_log[-1].verdict == "denied"
    assert executor.audit_log[-1].reason == "high_impact_closed"


def test_dangerous_risk_takes_priority_over_high_impact_profile() -> None:
    backend = ProfileToolBackend(dynamic_profile="high_impact", dynamic_risk="dangerous")
    executor = _executor(backend)

    with pytest.raises(SafetyDenied) as captured:
        executor.execute(
            ExecutionPlan(
                [
                    ExecutionStep(
                        "system.echo",
                        "echo",
                        {"message": "hello"},
                        approval_profile="high_impact",
                    )
                ]
            )
        )

    assert captured.value.code == "SAFETY_DENIED"
    assert backend.calls == []
