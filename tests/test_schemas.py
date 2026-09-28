"""Tests for core schema data structures."""

from dataclasses import fields

from src.core.schemas import (
    AdvisoryResult,
    AuditEvent,
    CloudAuditEvent,
    ConsultationProposal,
    ConsultOutcome,
    ContextCandidate,
    ExecutionPlan,
    ExecutionStep,
    InputEvent,
    IntentCandidate,
    LocalMindError,
    MinimalContext,
    NextAction,
    Result,
    TaskBrief,
)


def test_result_ok_and_err_are_mutually_exclusive() -> None:
    ok_result = Result.ok({"answer": 42})
    error = LocalMindError(
        code="CONFIG_ERROR",
        message="Missing config section",
        user_message="Config is missing a required section.",
        recoverable=True,
    )
    err_result = Result.err(error)

    assert ok_result.is_ok is True
    assert ok_result.is_err is False
    assert ok_result.value == {"answer": 42}
    assert ok_result.error is None

    assert err_result.is_ok is False
    assert err_result.is_err is True
    assert err_result.error is error
    assert err_result.value is None


def test_result_rejects_invalid_states() -> None:
    error = LocalMindError(
        code="CONFIG_ERROR",
        message="Missing config section",
        user_message="Config is missing a required section.",
    )

    try:
        Result()
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("Result() should reject empty value and error")

    try:
        Result(value={"answer": 42}, error=error)
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("Result should reject simultaneous value and error")


def test_intent_candidate_defaults_to_vague_low_risk_candidate() -> None:
    candidate = IntentCandidate()

    assert candidate.state == "VAGUE"
    assert candidate.intent_type == "unknown"
    assert candidate.entities == {}
    assert candidate.missing_info == []
    assert candidate.suggested_tools == []
    assert candidate.risk_draft == "normal"
    assert candidate.model_confidence == 0.0
    assert candidate.consultation_proposal is None


def test_consultation_proposal_keeps_only_local_model_suggestions() -> None:
    proposal = ConsultationProposal(
        should_consult=True,
        escalation_reason="architecture_tradeoff",
        expected_benefit=0.8,
        candidate_context=[
            ContextCandidate(
                category="user_entity",
                label="database_engine",
                value="postgresql",
            )
        ],
        reasoning="A current external reference could help.",
    )
    candidate = IntentCandidate(consultation_proposal=proposal)

    assert candidate.consultation_proposal is proposal
    assert proposal.candidate_context[0].source == "model_proposed"


def test_input_event_matches_project_plan_entry_shape() -> None:
    event = InputEvent(
        text="查一下 project-a 的端口是否还在运行",
        session_id="sess_001",
        project_id="proj_project-a",
        timestamp="2026-07-01T10:30:00",
        source="cli",
    )

    assert event.text == "查一下 project-a 的端口是否还在运行"
    assert event.session_id == "sess_001"
    assert event.project_id == "proj_project-a"
    assert event.timestamp == "2026-07-01T10:30:00"
    assert event.source == "cli"


def test_input_event_allows_missing_project_id_and_defaults_to_cli_source() -> None:
    event = InputEvent(
        text="hello",
        session_id="sess_002",
        timestamp="2026-07-01T10:31:00",
    )

    assert event.project_id is None
    assert event.source == "cli"


def test_core_flow_schemas_match_project_plan_shape() -> None:
    context = MinimalContext(
        system_prompt="You are LocalMind.",
        current_input="check localmind port",
        relevant_history=["previous turn"],
        project_state={"project": "localmind"},
        tool_defs=(),
    )
    action = NextAction(
        action="PLAN_LOCAL",
        reason="Intent is ready",
        requires_user_confirmation=False,
    )
    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool_name="system.check_port",
                action="check",
                params={"port": 11434},
                risk_level="normal",
            )
        ]
    )

    assert context.current_input == "check localmind port"
    assert context.project_state == {"project": "localmind"}
    assert action.action == "PLAN_LOCAL"
    assert plan.steps[0].params["port"] == 11434


def test_minimal_context_defaults_current_input_to_empty_string() -> None:
    context = MinimalContext(system_prompt="You are LocalMind.")

    assert context.current_input == ""


def test_audit_event_matches_guarded_executor_audit_contract() -> None:
    expected_fields = [
        "audit_id",
        "task_id",
        "intent_id",
        "tool_name",
        "params_redacted",
        "risk_level",
        "verdict",
        "reason",
        "timestamp",
    ]

    assert [field.name for field in fields(AuditEvent)] == expected_fields

    event = AuditEvent(
        audit_id="audit_001",
        task_id="task_20260701_001",
        intent_id="intent_001",
        tool_name="system.check_port",
        params_redacted={"project": "project-a"},
        risk_level="normal",
        verdict="allowed",
        reason="All safety checks passed",
        timestamp="2026-07-01T10:30:05",
    )

    assert event.params_redacted == {"project": "project-a"}
    assert event.verdict == "allowed"


def test_cloud_advisory_schemas_preserve_subturn_and_audit_boundaries() -> None:
    advisory = AdvisoryResult(
        analysis="Need more context.",
        needs_more_info=True,
        followup_question="Which database?",
    )
    event = CloudAuditEvent(
        audit_id="cloud_audit_001",
        task_id="task_001",
        session_id="session_001",
        intent_id="intent_001",
        turn=2,
        provider="deepseek",
        purpose="advisory",
        grant_id="grant_001",
        issued_by="user",
        authorized_categories=["user_entity"],
        context_items=[],
        package_context_items=0,
        package_context_bytes=0,
        consumed_turns=2,
        cooldown_until=None,
        verdict="allowed",
        reason="ok",
        timestamp="2026-08-14T00:00:00+00:00",
    )

    assert advisory.needs_more_info is True
    assert advisory.followup_question == "Which database?"
    assert event.grant_id == "grant_001"
    assert event.turn == 2


def test_task_brief_and_followup_outcome_preserve_local_cloud_boundary() -> None:
    brief = TaskBrief(
        goal="Compare two retry designs.",
        constraints="Do not add dependencies.",
        known_facts="The backend is SQLite.",
        evidence="A timeout occurs under concurrent writes.",
        attempts="Local retry with backoff was considered.",
        question="Which design is safer?",
    )
    advisory = AdvisoryResult(
        analysis="More evidence could distinguish the designs.",
        needs_more_info=True,
        requested_context_categories=("memory_evidence",),
        followup_question="Please provide the affected query.",
    )
    outcome = ConsultOutcome(
        status="suspended",
        requested_categories=("memory_evidence",),
    )

    assert brief.question == "Which design is safer?"
    assert brief.unknowns == ()
    assert advisory.requested_context_categories == ("memory_evidence",)
    assert outcome.result is None
    assert "followup_question" not in [field.name for field in fields(CloudAuditEvent)]
