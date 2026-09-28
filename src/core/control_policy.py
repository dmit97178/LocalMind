"""Deterministic control policy for intent candidates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.core.reference_guard import ReferenceGuardResult
from src.core.risk_vocabulary import RISK_LEVELS
from src.core.schemas import IntentCandidate, NextAction, ToolCapability, ToolDef
from src.core.tool_validation import validate_tool_call

_READY_STATE = "READY"
_HIGH_CONFIDENCE = 0.7
_MEDIUM_CONFIDENCE = 0.6
_ASK_USER_CONFIDENCE = 0.4
_DANGEROUS_RISK = "dangerous"
_NORMAL_RISK = "normal"
_CLOUD_BENEFIT_THRESHOLD = 0.5


@dataclass(frozen=True)
class CloudControlState:
    """Per-turn deterministic facts used to decide whether cloud consultation is allowed."""

    cloud_enabled: bool
    force_cloud: bool = False
    deny_cloud: bool = False
    provider_available: bool = False
    remaining_turns: int = 0
    cooldown_active: bool = False
    task_has_sensitive_execution_chain: bool = False
    has_task_text: bool = False


@dataclass(frozen=True)
class CloudAdmissionDecision:
    """Structured result of the deterministic cloud-admission gate."""

    admitted: bool
    gate_result: str
    denied_reason: str = "none"


@dataclass(frozen=True)
class ControlPolicy:
    """Apply hard-coded scheduling rules to model-produced candidates."""

    def decide(
        self,
        candidate: IntentCandidate,
        cloud_state: CloudControlState | None = None,
        *,
        resolution_exhausted: bool,
        no_progress: bool = False,
        reference_guard: ReferenceGuardResult | None = None,
        tool_defs: Sequence[ToolDef] | None = None,
        capabilities: Sequence[ToolCapability] | None = None,
    ) -> NextAction:
        """Choose the next action without calling a model."""

        admission = evaluate_cloud_admission(
            candidate,
            cloud_state,
        )

        if admission.gate_result == "not_evaluated":
            if _is_dangerous(candidate):
                return NextAction(
                    action="REFUSE",
                    reason="Intent draft is marked dangerous.",
                    requires_user_confirmation=False,
                )

        force_cloud = cloud_state is not None and cloud_state.force_cloud
        if reference_guard is not None and reference_guard.triggered and not force_cloud:
            return NextAction(
                action="ASK_USER",
                reason="dangling_reference",
                requires_user_confirmation=False,
            )

        if admission.admitted:
            reason = (
                "Cloud consultation was explicitly forced by the user."
                if admission.gate_result == "admitted_forced"
                else "Cloud consultation passed deterministic per-turn controls."
            )
            return NextAction(
                action="REQUEST_CLOUD",
                reason=reason,
                requires_user_confirmation=False,
            )

        if is_effectively_ready(candidate):
            return _decide_ready(candidate, tool_defs, capabilities)

        if no_progress:
            if _is_conditionally_answerable(candidate):
                return NextAction(
                    action="PLAN_LOCAL",
                    reason="local_conditional_answer",
                    requires_user_confirmation=False,
                )
            return NextAction(
                action="ASK_USER",
                reason="no_progress",
                requires_user_confirmation=False,
            )

        if resolution_exhausted:
            return NextAction(
                action="ASK_USER",
                reason="resolution_exhausted",
                requires_user_confirmation=False,
            )

        if candidate.missing_info:
            return NextAction(
                action="RETRIEVE_MORE",
                reason="Intent is not ready and still has missing information.",
                requires_user_confirmation=False,
            )

        return NextAction(
            action="ASK_USER",
            reason="Intent is not ready but has no explicit missing information.",
            requires_user_confirmation=False,
        )


def _decide_ready(
    candidate: IntentCandidate,
    tool_defs: Sequence[ToolDef] | None,
    capabilities: Sequence[ToolCapability] | None = None,
) -> NextAction:
    if capabilities is not None:
        if candidate.capability_resolution in {"unavailable", "unrecognized"}:
            return NextAction("PLAN_LOCAL", "capability_unavailable", False)
        if candidate.capability_resolution == "routed" and candidate.tool_call is None and candidate.tool_call_resolution == "absent":
            return NextAction("PLAN_LOCAL", "tool_call_missing", False)
    if candidate.tool_intent == "local_action":
        if tool_defs is None:
            return NextAction("PLAN_LOCAL", "tool_catalog_absent", False)
        resolution_reasons = {
            "absent": "tool_call_missing",
            "unknown_tool": "unknown_tool",
            "multiple_proposed": "multiple_proposed",
            "invalid_shape": "tool_call_invalid_shape",
            "irrelevant_tool": "capability_irrelevant",
            "unrouted_tool": "capability_unrouted",
            "param_not_from_input": "param_not_from_input",
        }
        if candidate.tool_call_resolution != "resolved" or candidate.tool_call is None:
            return NextAction(
                "PLAN_LOCAL",
                resolution_reasons.get(
                    candidate.tool_call_resolution, "tool_call_invalid_shape"
                ),
                False,
            )
        validation = validate_tool_call(candidate.tool_call, tool_defs)
        if not validation.ok:
            reason = (
                validation.reason
                if validation.reason in {"param_missing", "unknown_tool"}
                else "param_invalid"
            )
            return NextAction(
                "ASK_USER" if validation.reason == "param_missing" else "PLAN_LOCAL",
                reason,
                False,
            )
    if candidate.missing_info:
        return NextAction(
            action="ASK_USER",
            reason="Intent is marked ready but still has missing information.",
            requires_user_confirmation=False,
        )

    confidence = candidate.model_confidence
    risk = _risk_for_policy(candidate.risk_draft)
    if confidence >= _HIGH_CONFIDENCE:
        if risk == _NORMAL_RISK:
            return NextAction(
                action="PLAN_LOCAL",
                reason="Intent is ready with sufficient confidence and normal risk.",
                requires_user_confirmation=False,
            )
        return NextAction(
            action="PLAN_LOCAL",
            reason=f"Intent is ready but risk is {risk}; user confirmation required.",
            requires_user_confirmation=True,
        )

    if confidence >= _MEDIUM_CONFIDENCE:
        return NextAction(
            action="PLAN_LOCAL",
            reason="Intent is ready but confidence requires user confirmation.",
            requires_user_confirmation=True,
        )

    if confidence >= _ASK_USER_CONFIDENCE:
        return NextAction(
            action="ASK_USER",
            reason="Intent confidence is too low for local planning.",
            requires_user_confirmation=False,
        )

    return NextAction(
        action="ASK_USER",
        reason="Intent confidence is too low for local planning.",
        requires_user_confirmation=False,
    )


def is_effectively_ready(candidate: IntentCandidate) -> bool:
    """Return whether objective candidate fields are sufficient for scheduling."""

    if candidate.state.upper() == _READY_STATE:
        return True
    return (
        candidate.model_confidence >= _HIGH_CONFIDENCE
        and not candidate.missing_info
        and candidate.intent_type.strip().lower() != "unknown"
    )


def _is_dangerous(candidate: IntentCandidate) -> bool:
    return _risk_for_policy(candidate.risk_draft) == _DANGEROUS_RISK


def _risk_for_policy(raw: object) -> str:
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized == _DANGEROUS_RISK:
            return _DANGEROUS_RISK
        if normalized in RISK_LEVELS:
            return normalized
    return "sensitive"


def evaluate_cloud_admission(
    candidate: IntentCandidate,
    cloud_state: CloudControlState | None = None,
) -> CloudAdmissionDecision:
    """Evaluate cloud admission without producing actions or side effects."""

    if _is_dangerous(candidate):
        return CloudAdmissionDecision(False, "not_evaluated")

    cloud_state = cloud_state or CloudControlState(cloud_enabled=False)
    if not cloud_state.force_cloud and (
        candidate.capability_resolution in {"unavailable", "unrecognized"}
        or candidate.tool_call_resolution == "param_not_from_input"
    ) and candidate.tool_call is None:
        return CloudAdmissionDecision(False, "not_evaluated")
    if cloud_state.force_cloud:
        request_kind = "forced"
        proposal = None
    else:
        proposal = candidate.consultation_proposal
        if proposal is None:
            return CloudAdmissionDecision(False, "absent")
        if not proposal.should_consult:
            return CloudAdmissionDecision(False, "not_suggested")

        request_kind = "proposal"

    denied_reason = _cloud_denied_reason(cloud_state)
    if denied_reason != "none":
        return CloudAdmissionDecision(False, "vetoed", denied_reason)

    if request_kind == "proposal":
        if proposal is None:
            return CloudAdmissionDecision(False, "absent")
        if proposal.expected_benefit < _CLOUD_BENEFIT_THRESHOLD:
            return CloudAdmissionDecision(False, "benefit_below_threshold")
        if candidate.tool_intent == "local_action":
            return CloudAdmissionDecision(False, "local_action_proposed")
        eligible = is_effectively_ready(candidate) or (
            candidate.state.strip().upper() in {"PARTIAL", "ALMOST"}
            and candidate.intent_type.strip().lower() not in {"", "unknown"}
        )
        if not eligible:
            return CloudAdmissionDecision(False, "not_eligible_local_state")
    return CloudAdmissionDecision(True, f"admitted_{request_kind}")


def _cloud_denied_reason(cloud_state: CloudControlState) -> str:
    if cloud_state.deny_cloud:
        return "deny_cloud"
    if cloud_state.task_has_sensitive_execution_chain:
        return "sensitive_execution_chain"
    if not cloud_state.cloud_enabled:
        return "cloud_disabled"
    if not cloud_state.provider_available:
        return "provider_unavailable"
    if cloud_state.remaining_turns <= 0:
        return "budget_exhausted"
    if cloud_state.cooldown_active:
        return "cooldown_active"
    if cloud_state.force_cloud and not cloud_state.has_task_text:
        return "empty_task"
    return "none"


def _is_conditionally_answerable(candidate: IntentCandidate) -> bool:
    return (
        candidate.state.strip().upper() == "ALMOST"
        and candidate.intent_type.strip().lower() not in {"", "unknown"}
        and _risk_for_policy(candidate.risk_draft) == _NORMAL_RISK
        and candidate.tool_intent != "local_action"
    )
