"""Tests for ControlPolicy."""

from dataclasses import replace

import pytest

from src.core.control_policy import (
    CloudControlState,
    ControlPolicy,
    evaluate_cloud_admission,
)
from src.core.reference_guard import ReferenceGuardResult
from src.core.schemas import ConsultationProposal, IntentCandidate, NextAction


def ready_candidate(
    *,
    confidence: float,
    risk: str = "normal",
    missing_info: list[str] | None = None,
) -> IntentCandidate:
    return IntentCandidate(
        state="READY",
        intent_type="check_system_status",
        entities={"target": "port"},
        missing_info=[] if missing_info is None else missing_info,
        risk_draft=risk,
        model_confidence=confidence,
    )


def test_ready_high_confidence_normal_risk_plans_locally_without_confirmation() -> None:
    from src.core.control_policy import ControlPolicy

    action = ControlPolicy().decide(ready_candidate(confidence=0.7), resolution_exhausted=False)

    assert action == NextAction(
        action="PLAN_LOCAL",
        reason="Intent is ready with sufficient confidence and normal risk.",
        requires_user_confirmation=False,
    )


def test_ready_sensitive_risk_requires_confirmation() -> None:
    from src.core.control_policy import ControlPolicy

    action = ControlPolicy().decide(
        ready_candidate(confidence=0.91, risk="sensitive"),
        resolution_exhausted=False,
    )

    assert action.action == "PLAN_LOCAL"
    assert action.requires_user_confirmation is True
    assert "sensitive" in action.reason


def test_ready_medium_confidence_requires_confirmation() -> None:
    from src.core.control_policy import ControlPolicy

    action = ControlPolicy().decide(ready_candidate(confidence=0.6), resolution_exhausted=False)

    assert action.action == "PLAN_LOCAL"
    assert action.requires_user_confirmation is True
    assert "confidence" in action.reason


def test_ready_low_confidence_asks_user() -> None:
    from src.core.control_policy import ControlPolicy

    action = ControlPolicy().decide(ready_candidate(confidence=0.59), resolution_exhausted=False)

    assert action.action == "ASK_USER"
    assert action.requires_user_confirmation is False


def test_ready_with_missing_info_asks_user_even_when_confidence_is_high() -> None:
    from src.core.control_policy import ControlPolicy

    action = ControlPolicy().decide(
        ready_candidate(confidence=0.9, missing_info=["project"]),
        resolution_exhausted=False,
    )

    assert action.action == "ASK_USER"
    assert "missing" in action.reason


def test_ready_label_with_missing_info_remains_eligible_for_automatic_cloud() -> None:
    from src.core.control_policy import evaluate_cloud_admission, is_effectively_ready

    candidate = replace(
        ready_candidate(confidence=0.9, missing_info=["service name"]),
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.9
        ),
    )
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )

    admission = evaluate_cloud_admission(candidate, cloud_state)


    assert is_effectively_ready(candidate) is True
    assert admission.gate_result == "admitted_proposal"
    assert admission.admitted is True


def test_non_ready_with_missing_info_retrieves_more() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="check_system_status",
        missing_info=["target"],
        model_confidence=0.3,
    )

    action = ControlPolicy().decide(candidate, resolution_exhausted=False)

    assert action == NextAction(
        action="RETRIEVE_MORE",
        reason="Intent is not ready and still has missing information.",
        requires_user_confirmation=False,
    )


def test_resolution_exhausted_asks_user_instead_of_requesting_another_round() -> None:
    """A final non-ready resolver result must not schedule impossible retrieval."""

    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="training_plan",
        missing_info=["topic", "audience"],
        model_confidence=0.3,
    )

    action = ControlPolicy().decide(candidate, resolution_exhausted=True)

    assert action == NextAction(
        action="ASK_USER",
        reason="resolution_exhausted",
        requires_user_confirmation=False,
    )


def test_ready_intent_preempts_resolution_exhaustion() -> None:
    """T4: the exhausted marker cannot downgrade a ready local task."""

    action = ControlPolicy().decide(
        ready_candidate(confidence=0.9),
        resolution_exhausted=True,
    )

    assert action.action == "PLAN_LOCAL"


def test_no_progress_preempts_resolution_exhaustion() -> None:
    """T5: no-progress retains its conditional-answer path before exhaustion."""

    candidate = IntentCandidate(
        state="ALMOST",
        intent_type="architecture_analysis",
        missing_info=["traffic estimate"],
        suggested_tools=[],
        risk_draft="normal",
        model_confidence=0.55,
    )

    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=True,
        no_progress=True,
    )

    assert action == NextAction(
        action="PLAN_LOCAL",
        reason="local_conditional_answer",
        requires_user_confirmation=False,
    )


def test_resolution_exhausted_does_not_preempt_forced_cloud_consultation() -> None:
    """The exhaustion branch must remain below an explicitly requested cloud turn."""

    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="analysis",
        missing_info=["deployment scale"],
        risk_draft="normal",
        model_confidence=0.3,
    )
    cloud_state = CloudControlState(
        cloud_enabled=True,
        force_cloud=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )

    action = ControlPolicy().decide(
        candidate,
        cloud_state,
        resolution_exhausted=True,
    )

    assert action.action == "REQUEST_CLOUD"
    assert evaluate_cloud_admission(candidate, cloud_state).gate_result == "admitted_forced"


def test_resolution_exhausted_does_not_preempt_admitted_cloud_proposal() -> None:
    """A useful automatic escalation remains available after local rounds are consumed."""

    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="architecture_analysis",
        missing_info=["traffic profile"],
        risk_draft="normal",
        model_confidence=0.4,
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.8
        ),
    )
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )

    action = ControlPolicy().decide(
        candidate,
        cloud_state,
        resolution_exhausted=True,
    )

    assert action.action == "REQUEST_CLOUD"
    assert evaluate_cloud_admission(candidate, cloud_state).gate_result == "admitted_proposal"


def test_high_confidence_complete_concrete_vague_candidate_plans_locally() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="VAGUE",
        intent_type="system.echo",
        entities={"message": "hello"},
        missing_info=[],
        suggested_tools=["system.echo"],
        risk_draft="normal",
        model_confidence=0.9,
    )

    action = ControlPolicy().decide(candidate, resolution_exhausted=False)

    assert action.action == "PLAN_LOCAL"
    assert action.requires_user_confirmation is False


def test_high_confidence_unknown_intent_is_not_effectively_ready() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="VAGUE",
        intent_type="unknown",
        missing_info=[],
        model_confidence=0.9,
    )

    assert ControlPolicy().decide(candidate, resolution_exhausted=False).action == "ASK_USER"


def test_dangerous_risk_refuses_regardless_of_state_or_round_count() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="VAGUE",
        risk_draft="dangerous",
        missing_info=["anything"],
        model_confidence=0.1,
    )

    action = ControlPolicy().decide(candidate, resolution_exhausted=False)

    assert action.action == "REFUSE"
    assert action.requires_user_confirmation is False


def test_force_and_proposal_cloud_both_admit_sensitive_for_later_authorization() -> None:
    proposal = ConsultationProposal(True, "reasoning_complexity", 0.9)
    candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        risk_draft="sensitive",
        model_confidence=0.9,
        consultation_proposal=proposal,
    )
    available = {
        "cloud_enabled": True,
        "provider_available": True,
        "remaining_turns": 3,
    }

    forced = evaluate_cloud_admission(
        candidate,
        CloudControlState(**available, force_cloud=True, has_task_text=True),
    )
    automatic = evaluate_cloud_admission(
        candidate,
        CloudControlState(**available),
    )

    assert (forced.admitted, forced.gate_result, forced.denied_reason) == (
        True,
        "admitted_forced",
        "none",
    )
    assert (automatic.admitted, automatic.gate_result, automatic.denied_reason) == (
        True,
        "admitted_proposal",
        "none",
    )


def test_forced_sensitive_admission_is_deterministic() -> None:
    candidate = IntentCandidate(state="READY", risk_draft="sensitive")
    state = CloudControlState(
        cloud_enabled=True,
        force_cloud=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )

    outcomes = {
        (
            ControlPolicy().decide(
                candidate, state, resolution_exhausted=False
            ).action,
            evaluate_cloud_admission(candidate, state).gate_result,
        )
        for _ in range(20)
    }

    assert outcomes == {("REQUEST_CLOUD", "admitted_forced")}


@pytest.mark.parametrize("risk", ["DANGEROUS", " dangerous "])
def test_policy_defensively_refuses_dangerous_spelling_variants(risk: str) -> None:
    action = ControlPolicy().decide(
        ready_candidate(confidence=0.9, risk=risk),
        resolution_exhausted=False,
    )

    assert action.action == "REFUSE"


@pytest.mark.parametrize("risk", ["high", "critical", "normal-ish", None, 42, ""])
def test_policy_treats_other_out_of_domain_risks_as_sensitive(risk: object) -> None:
    candidate = replace(ready_candidate(confidence=0.9), risk_draft=risk)  # type: ignore[arg-type]

    action = ControlPolicy().decide(candidate, resolution_exhausted=False)

    assert action.action == "PLAN_LOCAL"
    assert action.requires_user_confirmation is True


def test_non_ready_without_missing_info_asks_user() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="ALMOST",
        intent_type="unknown",
        missing_info=[],
        model_confidence=0.55,
    )

    action = ControlPolicy().decide(candidate, resolution_exhausted=False)

    assert action.action == "ASK_USER"
    assert "not ready" in action.reason


def test_cloud_request_requires_model_proposal_and_per_turn_available_state() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        missing_info=[],
        suggested_tools=[],
        risk_draft="normal",
        model_confidence=0.9,
        consultation_proposal=ConsultationProposal(
            should_consult=True,
            escalation_reason="architecture_tradeoff",
            expected_benefit=0.8,
        ),
    )

    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            provider_available=True,
            remaining_turns=3,
        ),
    )

    assert action.action == "REQUEST_CLOUD"
    assert action.requires_user_confirmation is False


def test_cloud_request_is_denied_by_per_turn_state_or_local_tool_path() -> None:
    from src.core.control_policy import ControlPolicy

    candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        missing_info=[],
        suggested_tools=[],
        risk_draft="normal",
        model_confidence=0.9,
        consultation_proposal=ConsultationProposal(
            should_consult=True,
            escalation_reason="architecture_tradeoff",
            expected_benefit=0.8,
        ),
    )
    disabled = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=False,
            provider_available=True,
            remaining_turns=3,
        ),
    )
    with_tool = ControlPolicy().decide(
        IntentCandidate(
            state="READY",
            intent_type="analysis",
            missing_info=[],
            tool_intent="local_action",
            risk_draft="normal",
            model_confidence=0.9,
            consultation_proposal=candidate.consultation_proposal,
        ),
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            provider_available=True,
            remaining_turns=3,
        ),
    )

    assert disabled.action == "PLAN_LOCAL"
    assert with_tool.action == "PLAN_LOCAL"


def test_force_cloud_cannot_bypass_deny_or_budget_veto() -> None:
    candidate = ready_candidate(confidence=0.9)

    denied = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            deny_cloud=True,
            provider_available=True,
            remaining_turns=3,
        ),
    )
    exhausted = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            provider_available=True,
            remaining_turns=0,
        ),
    )

    assert denied.action == "PLAN_LOCAL"
    assert exhausted.action == "PLAN_LOCAL"


def test_forced_cloud_respects_provider_and_cooldown_vetoes() -> None:
    candidate = ready_candidate(confidence=0.9)
    states = (
        CloudControlState(
            cloud_enabled=False,
            force_cloud=True,
            provider_available=True,
            remaining_turns=3,
            has_task_text=True,
        ),
        CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            provider_available=False,
            remaining_turns=3,
            has_task_text=True,
        ),
        CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            provider_available=True,
            remaining_turns=3,
            cooldown_active=True,
            has_task_text=True,
        ),
    )

    actions = [
        ControlPolicy().decide(candidate, resolution_exhausted=False, cloud_state=state).action
        for state in states
    ]

    assert actions == ["PLAN_LOCAL", "PLAN_LOCAL", "PLAN_LOCAL"]


def test_forced_cloud_bypasses_partial_missing_info_and_model_tool_suggestion() -> None:
    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="analysis",
        missing_info=["deployment scale"],
        suggested_tools=["local.inspect"],
        risk_draft="normal",
        model_confidence=0.3,
    )

    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            provider_available=True,
            remaining_turns=3,
            has_task_text=True,
        ),
    )

    assert action.action == "REQUEST_CLOUD"
    assert "forced" in action.reason.lower()


def test_forced_cloud_defaults_to_no_task_text_and_does_not_upgrade() -> None:
    candidate = IntentCandidate(
        state="VAGUE",
        intent_type="unknown",
        missing_info=["task"],
        risk_draft="normal",
        model_confidence=0.0,
    )

    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            provider_available=True,
            remaining_turns=3,
        ),
    )

    assert action.action != "REQUEST_CLOUD"


def test_forced_cloud_allows_sensitive_draft_but_not_sensitive_execution_chain() -> None:
    sensitive = ready_candidate(confidence=0.9, risk="sensitive")
    normal = ready_candidate(confidence=0.9)
    forced = {
        "cloud_enabled": True,
        "force_cloud": True,
        "provider_available": True,
        "remaining_turns": 3,
        "has_task_text": True,
    }

    sensitive_action = ControlPolicy().decide(
        sensitive,
        resolution_exhausted=False,
        cloud_state=CloudControlState(**forced),
    )
    active_chain_action = ControlPolicy().decide(
        normal,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            **forced,
            task_has_sensitive_execution_chain=True,
        ),
    )

    assert sensitive_action.action == "REQUEST_CLOUD"
    assert active_chain_action.action != "REQUEST_CLOUD"


def test_partial_intent_with_valid_proposal_can_request_cloud() -> None:
    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="architecture_analysis",
        missing_info=["traffic profile"],
        suggested_tools=[],
        risk_draft="normal",
        model_confidence=0.6,
        consultation_proposal=ConsultationProposal(
            should_consult=True,
            escalation_reason="architecture_tradeoff",
            expected_benefit=0.8,
        ),
    )

    action = ControlPolicy().decide(
        candidate,
        resolution_exhausted=False,
        cloud_state=CloudControlState(
            cloud_enabled=True,
            provider_available=True,
            remaining_turns=3,
        ),
    )

    assert action.action == "REQUEST_CLOUD"


def test_partial_intent_requires_positive_cloud_proposal_and_benefit() -> None:
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
    )
    candidates = (
        IntentCandidate(
            state="PARTIAL",
            intent_type="analysis",
            missing_info=["detail"],
            risk_draft="normal",
            model_confidence=0.6,
        ),
        IntentCandidate(
            state="PARTIAL",
            intent_type="analysis",
            missing_info=["detail"],
            risk_draft="normal",
            model_confidence=0.6,
            consultation_proposal=ConsultationProposal(False, "reasoning_complexity", 0.9),
        ),
        IntentCandidate(
            state="PARTIAL",
            intent_type="analysis",
            missing_info=["detail"],
            risk_draft="normal",
            model_confidence=0.6,
            consultation_proposal=ConsultationProposal(True, "reasoning_complexity", 0.49),
        ),
    )

    actions = [
        ControlPolicy().decide(candidate, resolution_exhausted=False, cloud_state=cloud_state).action
        for candidate in candidates
    ]

    assert actions == ["RETRIEVE_MORE", "RETRIEVE_MORE", "RETRIEVE_MORE"]


def test_automatic_cloud_does_not_upgrade_vague_or_unknown_or_tool_candidate() -> None:
    proposal = ConsultationProposal(
        should_consult=True,
        escalation_reason="reasoning_complexity",
        expected_benefit=0.9,
    )
    base = {
        "missing_info": ["detail"],
        "risk_draft": "normal",
        "model_confidence": 0.6,
        "consultation_proposal": proposal,
    }
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
    )

    vague = ControlPolicy().decide(
        IntentCandidate(state="VAGUE", intent_type="analysis", **base),
        resolution_exhausted=False,
        cloud_state=cloud_state,
    )
    unknown = ControlPolicy().decide(
        IntentCandidate(state="PARTIAL", intent_type="unknown", **base),
        resolution_exhausted=False,
        cloud_state=cloud_state,
    )
    with_tool = ControlPolicy().decide(
        IntentCandidate(
            state="PARTIAL",
            intent_type="analysis",
            tool_intent="local_action",
            **base,
        ),
        resolution_exhausted=False,
        cloud_state=cloud_state,
    )

    assert vague.action != "REQUEST_CLOUD"
    assert unknown.action != "REQUEST_CLOUD"
    assert with_tool.action != "REQUEST_CLOUD"


def test_cloud_admission_reports_admitted_absent_below_threshold_and_vetoed() -> None:
    from src.core.control_policy import evaluate_cloud_admission

    available = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
    )
    proposal = ConsultationProposal(True, "reasoning_complexity", 0.9)
    candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        risk_draft="normal",
        model_confidence=0.95,
        consultation_proposal=proposal,
    )

    admitted = evaluate_cloud_admission(candidate, available)
    absent = evaluate_cloud_admission(
        ready_candidate(confidence=0.95),
        available,
    )
    below = evaluate_cloud_admission(
        IntentCandidate(
            state="READY",
            intent_type="analysis",
            risk_draft="normal",
            model_confidence=0.95,
            consultation_proposal=ConsultationProposal(
                True, "reasoning_complexity", 0.49
            ),
        ),
        available,
    )
    vetoed = evaluate_cloud_admission(
        candidate,
        CloudControlState(
            cloud_enabled=True,
            deny_cloud=True,
            provider_available=True,
            remaining_turns=3,
        ),
    )

    assert (admitted.admitted, admitted.gate_result) == (True, "admitted_proposal")
    assert (absent.admitted, absent.gate_result) == (False, "absent")
    assert (below.admitted, below.gate_result) == (
        False,
        "benefit_below_threshold",
    )
    assert (vetoed.admitted, vetoed.gate_result, vetoed.denied_reason) == (
        False,
        "vetoed",
        "deny_cloud",
    )


def test_cloud_veto_precedes_proposal_tool_and_benefit_gates() -> None:
    from src.core.control_policy import evaluate_cloud_admission

    denied = CloudControlState(
        cloud_enabled=True,
        deny_cloud=True,
        provider_available=True,
        remaining_turns=3,
    )
    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="analysis",
        missing_info=["detail"],
        suggested_tools=["local.inspect"],
        risk_draft="normal",
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.49
        ),
    )

    decision = evaluate_cloud_admission(candidate, denied)


    assert decision.gate_result == "vetoed"
    assert decision.denied_reason == "deny_cloud"


def test_cloud_admission_distinguishes_not_evaluated_from_vetoed() -> None:
    from src.core.control_policy import evaluate_cloud_admission

    available = CloudControlState(
        cloud_enabled=True,
        force_cloud=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )
    dangerous = ready_candidate(confidence=0.95, risk="dangerous")
    ordinary = ready_candidate(confidence=0.95)

    danger_decision = evaluate_cloud_admission(dangerous, available)
    ordinary_decision = evaluate_cloud_admission(ordinary, available)

    assert danger_decision.gate_result == "not_evaluated"
    assert ordinary_decision.gate_result == "admitted_forced"


def test_no_progress_conditionally_answers_only_without_tools() -> None:
    candidate = IntentCandidate(
        state="ALMOST",
        intent_type="architecture_analysis",
        missing_info=["traffic estimate"],
        suggested_tools=[],
        risk_draft="normal",
        model_confidence=0.55,
    )

    conditional = ControlPolicy().decide(
        candidate, resolution_exhausted=False, no_progress=True
    )
    with_tool = ControlPolicy().decide(
        IntentCandidate(
            state="ALMOST",
            intent_type="architecture_analysis",
            missing_info=["traffic estimate"],
            tool_intent="local_action",
            risk_draft="normal",
            model_confidence=0.55,
        ),
        resolution_exhausted=False,
        no_progress=True,
    )

    assert conditional == NextAction(
        action="PLAN_LOCAL",
        reason="local_conditional_answer",
        requires_user_confirmation=False,
    )
    assert with_tool.action == "ASK_USER"
    assert with_tool.reason == "no_progress"


def test_cloud_admission_enums_and_policy_actions_stay_consistent() -> None:
    from src.core.control_policy import evaluate_cloud_admission

    proposal = ConsultationProposal(True, "reasoning_complexity", 0.9)
    base = IntentCandidate(
        state="READY",
        intent_type="analysis",
        risk_draft="normal",
        model_confidence=0.9,
        consultation_proposal=proposal,
    )
    available = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )
    cases = [
        (replace(base, risk_draft="dangerous"), available, "not_evaluated", "none"),
        (replace(base, consultation_proposal=None), available, "absent", "none"),
        (
            replace(
                base,
                consultation_proposal=ConsultationProposal(
                    False, "reasoning_complexity", 0.9
                ),
            ),
            available,
            "not_suggested",
            "none",
        ),
        (
            replace(
                base,
                consultation_proposal=ConsultationProposal(
                    True, "reasoning_complexity", 0.49
                ),
            ),
            available,
            "benefit_below_threshold",
            "none",
        ),
        (
            replace(base, tool_intent="local_action"),
            available,
            "local_action_proposed",
            "none",
        ),
        (
            replace(base, state="VAGUE", intent_type="unknown", model_confidence=0.2),
            available,
            "not_eligible_local_state",
            "none",
        ),
        (base, replace(available, force_cloud=True), "admitted_forced", "none"),
        (base, available, "admitted_proposal", "none"),
    ]
    vetoes = {
        "deny_cloud": (base, replace(available, deny_cloud=True)),
        "sensitive_execution_chain": (
            base,
            replace(available, task_has_sensitive_execution_chain=True),
        ),
        "cloud_disabled": (base, replace(available, cloud_enabled=False)),
        "provider_unavailable": (base, replace(available, provider_available=False)),
        "budget_exhausted": (base, replace(available, remaining_turns=0)),
        "cooldown_active": (base, replace(available, cooldown_active=True)),
        "empty_task": (
            base,
            replace(available, force_cloud=True, has_task_text=False),
        ),
    }
    cases.extend(
        (candidate, state, "vetoed", reason)
        for reason, (candidate, state) in vetoes.items()
    )

    seen_gate_results: set[str] = set()
    seen_denied_reasons: set[str] = set()
    for candidate, state, expected_gate, expected_reason in cases:
        admission = evaluate_cloud_admission(
            candidate,
            state,
        )
        action = ControlPolicy().decide(candidate, state, resolution_exhausted=False)

        assert admission.gate_result == expected_gate
        assert admission.denied_reason == expected_reason
        assert (admission.gate_result == "vetoed") == (
            admission.denied_reason != "none"
        )
        assert (action.action == "REQUEST_CLOUD") == admission.admitted
        seen_gate_results.add(admission.gate_result)
        seen_denied_reasons.add(admission.denied_reason)

    assert seen_gate_results == {
        "not_evaluated",
        "absent",
        "not_suggested",
        "benefit_below_threshold",
        "local_action_proposed",
        "not_eligible_local_state",
        "vetoed",
        "admitted_forced",
        "admitted_proposal",
    }
    assert seen_denied_reasons == {"none", *vetoes}


def test_sensitive_proposal_is_admitted_and_never_uses_non_normal_risk_denial() -> None:
    from src.core.control_policy import evaluate_cloud_admission

    candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        risk_draft="sensitive",
        model_confidence=0.9,
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.9
        ),
    )
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )

    admission = evaluate_cloud_admission(candidate, cloud_state)

    assert admission.gate_result == "admitted_proposal"
    assert admission.denied_reason == "none"
    assert ControlPolicy().decide(
        candidate, cloud_state, resolution_exhausted=False
    ).action == "REQUEST_CLOUD"


def test_reference_guard_preempts_automatic_cloud_admission() -> None:
    candidate = IntentCandidate(
        state="READY",
        intent_type="deployment",
        risk_draft="normal",
        model_confidence=0.9,
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.9
        ),
    )
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )

    action = ControlPolicy().decide(
        candidate,
        cloud_state,
        resolution_exhausted=False,
        reference_guard=ReferenceGuardResult(True, "none", "那个服务"),
    )

    assert evaluate_cloud_admission(candidate, cloud_state).gate_result == "admitted_proposal"
    assert action == NextAction("ASK_USER", "dangling_reference", False)


def test_reference_guard_yields_to_forced_cloud() -> None:
    action = ControlPolicy().decide(
        ready_candidate(confidence=0.9),
        CloudControlState(
            cloud_enabled=True,
            force_cloud=True,
            provider_available=True,
            remaining_turns=3,
            has_task_text=True,
        ),
        resolution_exhausted=False,
        reference_guard=ReferenceGuardResult(True, "none", "这份配置"),
    )

    assert action.action == "REQUEST_CLOUD"


def test_dangerous_intent_preempts_reference_guard() -> None:
    action = ControlPolicy().decide(
        ready_candidate(confidence=0.9, risk="dangerous"),
        resolution_exhausted=False,
        reference_guard=ReferenceGuardResult(True, "none", "那个服务"),
    )

    assert action.action == "REFUSE"


def test_not_triggered_reference_guard_preserves_normal_cloud_path() -> None:
    candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        risk_draft="normal",
        model_confidence=0.9,
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.9
        ),
    )
    action = ControlPolicy().decide(
        candidate,
        CloudControlState(
            cloud_enabled=True,
            provider_available=True,
            remaining_turns=3,
            has_task_text=True,
        ),
        resolution_exhausted=False,
        reference_guard=ReferenceGuardResult(False),
    )

    assert action.action == "REQUEST_CLOUD"


def test_absent_reference_guard_preserves_existing_behavior() -> None:
    cloud_candidate = IntentCandidate(
        state="READY",
        intent_type="analysis",
        risk_draft="normal",
        model_confidence=0.9,
        consultation_proposal=ConsultationProposal(
            True, "reasoning_complexity", 0.9
        ),
    )
    cloud_state = CloudControlState(
        cloud_enabled=True,
        provider_available=True,
        remaining_turns=3,
        has_task_text=True,
    )
    vague_candidate = IntentCandidate(
        state="VAGUE",
        intent_type="unknown",
        missing_info=["target"],
        risk_draft="normal",
        model_confidence=0.2,
    )

    assert (
        ControlPolicy().decide(
            cloud_candidate, cloud_state, resolution_exhausted=False
        ).action
        == "REQUEST_CLOUD"
    )
    assert (
        ControlPolicy().decide(vague_candidate, resolution_exhausted=False).action
        == "RETRIEVE_MORE"
    )
