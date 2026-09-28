"""Tests for guarded execution and P0a safety stubs."""

from dataclasses import dataclass, field

import pytest

from src.core.interfaces import SafetyBackend, ToolBackend
from src.core.schemas import (
    ExecutionPlan,
    ExecutionStep,
    LocalMindError,
    PreflightReport,
    Result,
    SafetyDenied,
    SafetyVerdict,
    ToolDef,
    ToolError,
)


@dataclass
class RecordingToolBackend(ToolBackend):
    result: Result[dict]
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def list_tools(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="system.echo",
                description="Echo a message.",
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "token": {"type": "string"},
                    },
                    "required": ["message"],
                },
            )
        ]

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        self.calls.append((tool_name, params))
        return self.result


@dataclass
class FixedSafetyBackend(SafetyBackend):
    verdict: SafetyVerdict
    operations: list[dict] = field(default_factory=list)

    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        self.operations.append(operation)
        return self.verdict


def test_audit_redact_all_params_applies_to_allowed_and_failed_results() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    class OutboundBackend(RecordingToolBackend):
        def list_tools(self) -> list[ToolDef]:
            return [ToolDef(
                "weather.current", "Weather lookup",
                {"type": "object", "properties": {"location": {"type": "string"}},
                 "required": ["location"]},
                audit_redact_all_params=True,
            )]

    backend = OutboundBackend(Result.ok({"source": "test"}))
    executor = GuardedToolExecutor(
        backend, SafetyPolicy(FixedSafetyBackend(SafetyVerdict(True, "normal", "ok")))
    )
    plan = ExecutionPlan([ExecutionStep(
        tool_name="weather.current", action="current",
        params={"location": "南京"}, risk_level="normal",
    )])

    executor.execute(plan)
    assert "南京" not in repr(executor.audit_log)
    assert executor.audit_log is not None
    assert executor.audit_log[-1].params_redacted == {"location": "***"}

    backend.result = Result.err(ToolError(
        code="TOOL_EXEC_ERROR", message="failed", user_message="failed", recoverable=True
    ))
    with pytest.raises(ToolError):
        executor.execute(plan)
    assert "南京" not in repr(executor.audit_log)
    assert executor.audit_log[-1].params_redacted == {"location": "***"}

    invalid = ExecutionPlan([ExecutionStep(
        tool_name="weather.current", action="current",
        params={"location": 123}, risk_level="normal",
    )])
    with pytest.raises(ToolError):
        executor.execute(invalid)
    assert executor.audit_log[-1].params_redacted == {"location": "***"}


def test_guarded_executor_checks_safety_before_executing_tool() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    safety_backend = FixedSafetyBackend(
        SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")
    )
    tool_backend = RecordingToolBackend(Result.ok({"echo": "hello"}))
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(backend=safety_backend),
    )

    result = executor.execute(
        ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool_name="system.echo",
                    action="echo",
                    params={"message": "hello"},
                )
            ]
        )
    )

    assert result == {0: {"echo": "hello"}}
    assert safety_backend.operations == [
        {
            "tool_name": "system.echo",
            "action": "echo",
            "params": {"message": "hello"},
            "risk_level": "normal",
            "intent_type": "unknown",
            "entities": {},
            "user_input": "",
        }
    ]
    assert tool_backend.calls == [("system.echo", {"message": "hello"})]


def test_guarded_executor_denies_before_tool_execution_when_safety_fails() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    tool_backend = RecordingToolBackend(Result.ok({"should_not": "run"}))
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(
            backend=FixedSafetyBackend(
                SafetyVerdict(
                    allowed=False,
                    risk_level="dangerous",
                    reason="Matched forbidden command pattern.",
                )
            )
        ),
    )

    try:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="system.echo",
                        action="echo",
                        params={"message": "rm -rf /"},
                        risk_level="normal",
                    )
                ]
            )
        )
    except SafetyDenied as exc:
        assert exc.code == "SAFETY_DENIED"
        assert exc.details == {
            "step_index": 0,
            "tool_name": "system.echo",
            "risk_level": "dangerous",
            "reason": "Matched forbidden command pattern.",
        }
    else:
        raise AssertionError("GuardedToolExecutor should raise SafetyDenied")

    assert tool_backend.calls == []


def test_guarded_executor_raises_tool_error_when_tool_backend_returns_error() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    tool_backend = RecordingToolBackend(
        Result.err(
            ToolError(
                code="TOOL_EXEC_ERROR",
                message="tool failed",
                user_message="操作执行失败。",
                recoverable=True,
            )
        )
    )
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(
            backend=FixedSafetyBackend(
                SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")
            )
        ),
    )

    try:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="system.echo",
                        action="echo",
                        params={"message": "hello"},
                    )
                ]
            )
        )
    except ToolError as exc:
        assert exc.code == "TOOL_EXEC_ERROR"
    else:
        raise AssertionError("GuardedToolExecutor should raise ToolError")


def test_guarded_executor_rejects_unregistered_tool_before_safety_check() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    safety_backend = FixedSafetyBackend(
        SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")
    )
    executor = GuardedToolExecutor(
        tool_backend=RecordingToolBackend(Result.ok({"unused": True})),
        safety_policy=SafetyPolicy(backend=safety_backend),
    )

    try:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="system.unknown",
                        action="echo",
                        params={"message": "hello"},
                    )
                ]
            )
        )
    except ToolError as exc:
        assert exc.code == "TOOL_NOT_FOUND"
        assert exc.details == {"tool_name": "system.unknown", "step_index": 0}
    else:
        raise AssertionError("GuardedToolExecutor should reject unregistered tools")

    assert safety_backend.operations == []


def test_identity_verifier_p0a_stub_allows_any_passphrase() -> None:
    from src.safety.identity import IdentityVerifier

    verifier = IdentityVerifier(passphrase_config={"lockout_attempts": 5})

    assert verifier.verify("") is True
    assert verifier.verify("anything") is True


def test_recording_tool_backend_result_error_must_be_localmind_error() -> None:
    error = LocalMindError(
        code="TOOL_EXEC_ERROR",
        message="base failure",
        user_message="操作执行失败。",
        recoverable=True,
    )

    assert RecordingToolBackend(Result.err(error)).result.error is error


def test_guarded_executor_records_redacted_audit_event_for_success() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    audit_log = []
    executor = GuardedToolExecutor(
        tool_backend=RecordingToolBackend(Result.ok({"echo": "hello"})),
        safety_policy=SafetyPolicy(
            backend=FixedSafetyBackend(
                SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")
            )
        ),
        audit_log=audit_log,
    )

    executor.execute(
        ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool_name="system.echo",
                    action="echo",
                    params={"message": "hello", "token": "secret-value"},
                )
            ]
        ),
        task_id="task-1",
        intent_id="intent-1",
    )

    assert len(audit_log) == 1
    assert audit_log[0].task_id == "task-1"
    assert audit_log[0].intent_id == "intent-1"
    assert audit_log[0].verdict == "allowed"
    assert audit_log[0].params_redacted == {"message": "hello", "token": "***"}


def test_guarded_executor_creates_audit_log_when_none_is_supplied() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    executor = GuardedToolExecutor(
        tool_backend=RecordingToolBackend(Result.ok({"echo": "hello"})),
        safety_policy=SafetyPolicy(
            backend=FixedSafetyBackend(
                SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")
            )
        ),
        audit_log=None,
    )

    assert executor.audit_log == []


def test_guarded_executor_rejects_sensitive_registered_tool_in_p0a() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    class SensitiveToolBackend(RecordingToolBackend):
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

    audit_log = []
    tool_backend = SensitiveToolBackend(Result.ok({"content": "unused"}))
    executor = GuardedToolExecutor(
        tool_backend=tool_backend,
        safety_policy=SafetyPolicy(
            backend=FixedSafetyBackend(
                SafetyVerdict(allowed=True, risk_level="normal", reason="allowed")
            )
        ),
        audit_log=audit_log,
    )

    try:
        executor.execute(
            ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool_name="file.read",
                        action="read",
                        params={"path": "notes.txt"},
                        risk_level="normal",
                    )
                ]
            ),
            task_id="task-1",
            intent_id="intent-1",
        )
    except SafetyDenied as exc:
        assert exc.code == "SAFETY_NECESSITY"
        assert exc.user_message == "此操作需要确认与身份验证后才能执行。"
    else:
        raise AssertionError("P0a should reject sensitive tools")

    assert tool_backend.calls == []
    assert audit_log[0].verdict == "denied"
    assert audit_log[0].risk_level == "sensitive"


def test_execute_rechecks_dynamic_risk_and_exposes_it_to_safety_and_audit() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    class DynamicBackend(RecordingToolBackend):
        def preflight(self, tool_name: str, params: dict) -> PreflightReport:
            return PreflightReport("sensitive", True, True, "notes.txt", "target_exists")

    safety_backend = FixedSafetyBackend(
        SafetyVerdict(allowed=True, risk_level="sensitive", reason="allowed")
    )
    audit_log = []
    executor = GuardedToolExecutor(
        DynamicBackend(Result.ok({"bytes_written": 3})),
        SafetyPolicy(safety_backend),
        audit_log,
    )
    plan = ExecutionPlan(
        [
            ExecutionStep(
                "system.echo",
                "echo",
                {"message": "hello"},
                user_input="hello",
                gate23_passed=True,
            )
        ]
    )

    executor.execute(plan, "task-1", "intent-1")

    assert safety_backend.operations[0]["risk_level"] == "sensitive"
    assert audit_log[0].risk_level == "sensitive"


def test_executor_preflight_aggregates_dynamic_plan_risk_without_side_effects() -> None:
    from src.safety.guarded_executor import GuardedToolExecutor
    from src.safety.policy import SafetyPolicy

    class DynamicBackend(RecordingToolBackend):
        def preflight(self, tool_name: str, params: dict) -> PreflightReport:
            return PreflightReport("sensitive", True, True, "notes.txt", "target_exists")

    backend = DynamicBackend(Result.ok({"unused": True}))
    audit_log = []
    executor = GuardedToolExecutor(
        backend,
        SafetyPolicy(FixedSafetyBackend(SafetyVerdict(True, "normal", "allowed"))),
        audit_log,
    )

    report = executor.preflight(
        ExecutionPlan([ExecutionStep("system.echo", "echo", {"message": "hello"})])
    )

    assert report == PreflightReport("sensitive", True, True, "notes.txt", "target_exists")
    assert backend.calls == []
    assert audit_log == []


def test_unknown_model_risk_defaults_to_sensitive_not_dangerous() -> None:
    from src.safety.guarded_executor import effective_risk_for

    step = ExecutionStep("system.echo", "echo", {}, risk_level="unexpected")
    tool = ToolDef("system.echo", "Echo", {}, "normal")

    assert effective_risk_for(step, tool) == "sensitive"
