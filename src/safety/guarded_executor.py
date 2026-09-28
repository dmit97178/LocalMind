"""Guarded execution boundary for all tool side effects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.core.interfaces import ToolBackend
from src.core.risk_vocabulary import read_approval_profile
from src.core.schemas import (
    AuditEvent,
    ExecutionPlan,
    ExecutionStep,
    PreflightReport,
    SafetyDenied,
    ToolCallDraft,
    ToolDef,
    ToolError,
)
from src.core.tool_validation import validate_tool_call, validate_tool_catalog
from src.safety.policy import SafetyPolicy
from src.safety.secret_scan import contains_credential, scan_credentials

_RISK_ORDER = {"normal": 0, "sensitive": 1, "dangerous": 2}
_APPROVAL_ORDER = {"standard": 0, "high_impact": 1}
_SENSITIVE_PARAM_KEYS = {
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "passphrase",
    "key",
    "content",
}
@dataclass
class GuardedToolExecutor:
    """Execute tool plans only after registration and safety checks."""

    tool_backend: ToolBackend
    safety_policy: SafetyPolicy
    audit_log: list[AuditEvent] | None = None

    def __post_init__(self) -> None:
        if self.audit_log is None:
            self.audit_log = []

    def execute(
        self,
        plan: ExecutionPlan,
        task_id: str = "",
        intent_id: str = "",
    ) -> dict[int, dict[str, object]]:
        """Execute plan steps and return results keyed by step index."""

        results: dict[int, dict[str, object]] = {}
        registered_tools = {
            tool.name: tool
            for tool in validate_tool_catalog(self.tool_backend.list_tools())
        }

        for step_index, step in enumerate(plan.steps):
            tool_def = registered_tools.get(step.tool_name)
            if tool_def is None:
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=step.risk_level,
                    verdict="error",
                    reason=f"Tool is not registered: {step.tool_name}",
                )
                raise ToolError(
                    code="TOOL_NOT_FOUND",
                    message=f"Tool is not registered: {step.tool_name}",
                    user_message="所需工具不可用。",
                    recoverable=True,
                    details={"tool_name": step.tool_name, "step_index": step_index},
                )

            validation = validate_tool_call(
                ToolCallDraft(step.tool_name, dict(step.params)),
                tuple(registered_tools.values()),
            )
            if not validation.ok:
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=step.risk_level,
                    verdict="error",
                    reason=validation.reason,
                )
                raise ToolError(
                    code="TOOL_PARAM_ERROR",
                    message=f"Tool parameters rejected at execution boundary: {validation.reason}",
                    user_message="操作参数不正确。",
                    recoverable=True,
                    details={
                        "tool_name": step.tool_name,
                        "step_index": step_index,
                        "reason": validation.reason,
                        "missing": validation.missing,
                        "offending": validation.offending,
                    },
                )

            dynamic = self.tool_backend.preflight(step.tool_name, dict(step.params))
            effective_risk = _max_risk(
                step.risk_level, tool_def.risk_level, dynamic.effective_risk
            )
            effective_profile = _max_approval_profile(
                step.approval_profile,
                tool_def.approval_profile,
                dynamic.approval_profile,
            )
            step = replace(
                step,
                risk_level=effective_risk,
                approval_profile=effective_profile,
            )
            if effective_risk == "dangerous":
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=effective_risk,
                    verdict="denied",
                    reason="Dangerous operations are denied by the execution boundary.",
                    redact_all_values=True,
                )
                raise SafetyDenied(
                    code="SAFETY_DENIED",
                    message=f"Dangerous step denied: {step.tool_name}",
                    user_message="此操作已被安全策略拒绝。",
                    recoverable=False,
                    details={
                        "tool_name": step.tool_name,
                        "risk_level": effective_risk,
                        "step_index": step_index,
                    },
                )

            if effective_profile == "high_impact":
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=effective_risk,
                    verdict="denied",
                    reason="high_impact_closed",
                    redact_all_values=True,
                )
                raise SafetyDenied(
                    code="SAFETY_IMPACT_CLOSED",
                    message=f"High-impact step withheld: {step.tool_name}",
                    user_message="此操作属于高影响操作，当前阶段不执行。我可以先给出分析与所需条件。",
                    recoverable=False,
                    details={
                        "tool_name": step.tool_name,
                        "risk_level": effective_risk,
                        "step_index": step_index,
                    },
                )

            if effective_risk == "sensitive" and not step.gate23_passed:
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=effective_risk,
                    verdict="denied",
                    reason="Sensitive operations require confirmation and identity verification.",
                    redact_all_values=True,
                )
                raise SafetyDenied(
                    code="SAFETY_NECESSITY",
                    message=f"Sensitive step lacks confirmation: {step.tool_name}",
                    user_message="此操作需要确认与身份验证后才能执行。",
                    recoverable=False,
                    details={
                        "tool_name": step.tool_name,
                        "risk_level": effective_risk,
                        "step_index": step_index,
                    },
                )

            try:
                verdict = self.safety_policy.check(step)
            except SafetyDenied as exc:
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=effective_risk,
                    verdict="denied",
                    reason=exc.message,
                    redact_all_values=True,
                )
                raise
            if not verdict.allowed:
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=effective_risk,
                    verdict="denied",
                    reason=verdict.reason,
                    redact_all_values=verdict.risk_level in {"sensitive", "dangerous"},
                )
                raise SafetyDenied(
                    code="SAFETY_DENIED",
                    message=f"Safety policy denied step {step_index}: {verdict.reason}",
                    user_message="此操作被安全策略阻止。",
                    recoverable=False,
                    details={
                        "step_index": step_index,
                        "tool_name": step.tool_name,
                        "risk_level": verdict.risk_level,
                        "reason": verdict.reason,
                    },
                )

            tool_result = self.tool_backend.execute(step.tool_name, dict(step.params))
            if tool_result.is_err:
                error = tool_result.error
                if error is None:
                    error = ToolError(
                        code="TOOL_EXEC_ERROR",
                        message=f"Tool returned an invalid error result: {step.tool_name}",
                        user_message="操作执行失败。",
                        recoverable=True,
                        details={"tool_name": step.tool_name, "step_index": step_index},
                    )
                self._record(
                    step_index,
                    step,
                    task_id,
                    intent_id,
                    risk_level=effective_risk,
                    verdict="error",
                    reason=error.message,
                )
                raise error

            results[step_index] = tool_result.value or {}
            self._record(
                step_index,
                step,
                task_id,
                intent_id,
                risk_level=effective_risk,
                verdict="allowed",
                reason=dynamic.reason or "ok",
            )

        return results

    def preflight(
        self,
        plan: ExecutionPlan,
        task_id: str = "",
        intent_id: str = "",
    ) -> PreflightReport:
        """Assess a plan without executing tools or writing audit records."""

        del task_id, intent_id
        registered = {
            tool.name: tool
            for tool in validate_tool_catalog(self.tool_backend.list_tools())
        }
        reports: list[PreflightReport] = []
        for step in plan.steps:
            tool_def = registered.get(step.tool_name)
            if tool_def is None:
                raise ToolError(
                    code="TOOL_NOT_FOUND",
                    message=f"Tool is not registered: {step.tool_name}",
                    user_message="所需工具不可用。",
                    recoverable=True,
                    details={"tool_name": step.tool_name},
                )
            dynamic = self.tool_backend.preflight(step.tool_name, dict(step.params))
            effective = _max_risk(
                step.risk_level, tool_def.risk_level, dynamic.effective_risk
            )
            effective_profile = _max_approval_profile(
                step.approval_profile,
                tool_def.approval_profile,
                dynamic.approval_profile,
            )
            reports.append(
                replace(
                    dynamic,
                    effective_risk=effective,
                    requires_confirmation=dynamic.requires_confirmation
                    or effective in {"sensitive", "dangerous"},
                    approval_profile=effective_profile,
                )
            )
        if not reports:
            return PreflightReport("normal", False)
        highest = max(reports, key=lambda report: _risk_value(report.effective_risk))
        effective_profile = _max_approval_profile(
            *(report.approval_profile for report in reports)
        )
        targeted = next((report for report in reports if report.target_key is not None), highest)
        return PreflightReport(
            effective_risk=highest.effective_risk,
            requires_confirmation=any(report.requires_confirmation for report in reports),
            target_exists=targeted.target_exists,
            target_key=targeted.target_key,
            reason=highest.reason or targeted.reason,
            approval_profile=effective_profile,
        )

    def record_denial(
        self,
        plan: ExecutionPlan,
        task_id: str,
        intent_id: str,
        reason: str,
    ) -> None:
        """Record a pre-execution security denial for a pending plan."""

        for step_index, step in enumerate(plan.steps):
            self._record(
                step_index,
                step,
                task_id,
                intent_id,
                risk_level=effective_risk_for(step, None),
                verdict="denied",
                reason=reason,
                redact_all_values=True,
            )

    def _record(
        self,
        step_index: int,
        step: ExecutionStep,
        task_id: str,
        intent_id: str,
        *,
        risk_level: str,
        verdict: str,
        reason: str,
        redact_all_values: bool = False,
    ) -> None:
        if self.audit_log is None:
            raise RuntimeError("GuardedToolExecutor audit log was not initialized")
        redact_all_values = redact_all_values or any(
            tool.name == step.tool_name and tool.audit_redact_all_params
            for tool in self.tool_backend.list_tools()
        )
        self.audit_log.append(
            AuditEvent(
                audit_id=uuid4().hex[:12],
                task_id=task_id,
                intent_id=intent_id,
                tool_name=step.tool_name,
                params_redacted=redact_params(step.params, redact_all_values=redact_all_values),
                risk_level=risk_level,
                verdict=verdict,
                reason=reason,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )


def effective_risk_for(step: ExecutionStep, tool_def: ToolDef | None) -> str:
    """Keep the registered tool risk as a minimum safety level."""

    model_level = _risk_value(step.risk_level)
    tool_level = _risk_value(tool_def.risk_level) if tool_def else 0
    effective_level = max(model_level, tool_level)
    return next(level for level, value in _RISK_ORDER.items() if value == effective_level)


def _risk_value(risk_level: str) -> int:
    """Fail closed when an adapter or model provides an unknown risk level."""

    return _RISK_ORDER.get(risk_level, _RISK_ORDER["sensitive"])


def _max_risk(*levels: str) -> str:
    value = max(_risk_value(level) for level in levels)
    return next(level for level, rank in _RISK_ORDER.items() if rank == value)


def _max_approval_profile(*profiles: str) -> str:
    value = max(
        _APPROVAL_ORDER[read_approval_profile(profile)]
        for profile in profiles
    )
    return next(profile for profile, rank in _APPROVAL_ORDER.items() if rank == value)


def redact_params(value: Any, *, redact_all_values: bool = False) -> Any:
    """Recursively remove sensitive values before persisting an audit event."""

    if isinstance(value, Mapping):
        return {
            key: "***"
            if redact_all_values or _is_sensitive_key(key)
            else redact_params(item, redact_all_values=False)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [redact_params(item, redact_all_values=redact_all_values) for item in value]
    if redact_all_values or contains_sensitive_value(value):
        return "***"
    return value


def _effective_risk(step: ExecutionStep, tool_def: ToolDef) -> str:
    """Backward-compatible alias for the original internal helper."""

    return effective_risk_for(step, tool_def)


def _redact(value: Any, *, redact_all_values: bool = False) -> Any:
    """Backward-compatible alias for the original internal helper."""

    return redact_params(value, redact_all_values=redact_all_values)


def contains_sensitive_value(value: object) -> bool:
    """Return whether text still matches the shared sensitive-value pattern."""

    return contains_credential(value)


def contains_bare_secret(value: object) -> bool:
    """Return whether text is a recognizable bare credential value."""

    return isinstance(value, str) and any(
        hit.normalized_label is None for hit in scan_credentials(value)
    )


def _is_sensitive_key(key: object) -> bool:
    return str(key).lower() in _SENSITIVE_PARAM_KEYS
