"""Tests for deterministic cloud-context reduction and redaction."""

import json

import pytest

from src.core.schemas import ConsultationProposal, ContextCandidate, MinimalContext, SafetyDenied


def _proposal(*items: ContextCandidate) -> ConsultationProposal:
    return ConsultationProposal(
        should_consult=True,
        escalation_reason="architecture_tradeoff",
        expected_benefit=0.8,
        candidate_context=list(items),
    )


def test_prepare_keeps_only_allowlisted_entity_and_never_trusts_model_category() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    prepared = PrivacyPolicy("balanced", 3, 2048).prepare(
        _proposal(
            ContextCandidate("fixed_config", "database_engine", "PostgreSQL"),
            ContextCandidate("user_entity", "database_engine", "PostgreSQL"),
            ContextCandidate("user_entity", "host", "private.example"),
        ),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="deepseek",
        purpose="advisory",
    )

    assert [(item.category, item.label, item.value) for item in prepared.candidates] == [
        ("user_entity", "database_engine", "postgresql")
    ]
    assert len(prepared.denied) == 2
    assert all("private.example" not in str(item) for item in prepared.denied)


def test_prepare_replaces_a_detected_secret_without_retaining_its_value() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    prepared = PrivacyPolicy("balanced", 3, 2048).prepare(
        _proposal(ContextCandidate("secret", "api_key", secret)),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="deepseek",
        purpose="advisory",
    )

    assert [(item.category, item.label, item.value, item.redacted) for item in prepared.candidates] == [
        ("secret_placeholder", "api_key", "present", True)
    ]
    assert secret not in str(prepared)


def test_prepare_rejects_a_sensitive_raw_label_before_normalization() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    jwt_label = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123"
    prepared = PrivacyPolicy("balanced", 8, 2048).prepare(
        _proposal(ContextCandidate("free_text", jwt_label, "harmless text")),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="deepseek",
        purpose="advisory",
    )

    assert prepared.candidates == []
    assert prepared.denied[0].reason == "sensitive_label"
    assert jwt_label not in str(prepared)


def test_prepare_rejects_an_oversized_batch_instead_of_silently_truncating() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    with pytest.raises(SafetyDenied) as captured:
        PrivacyPolicy("balanced", 1, 2048).prepare(
            _proposal(
                ContextCandidate("user_entity", "language", "python"),
                ContextCandidate("user_entity", "os_family", "linux"),
            ),
            MinimalContext(system_prompt="test"),
            task_id="task-1",
            session_id="session-1",
            provider="deepseek",
            purpose="advisory",
        )

    assert captured.value.code == "SAFETY_CLOUD_BLOCK"


def test_prepare_keeps_a_long_local_task_brief_section_within_the_package_budget() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    long_evidence = "x" * 401
    prepared = PrivacyPolicy("balanced", 8, 2048).prepare(
        _proposal(
            ContextCandidate("free_text", "brief_goal", "Compare retry designs.", "local_task_context"),
            ContextCandidate("free_text", "brief_evidence", long_evidence, "local_task_context"),
            ContextCandidate("free_text", "brief_question", "Which is safer?", "local_task_context"),
        ),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="deepseek",
        purpose="architecture_tradeoff",
    )

    assert [(item.label, item.value) for item in prepared.candidates] == [
        ("brief_goal", "Compare retry designs."),
        ("brief_evidence", long_evidence),
        ("brief_question", "Which is safer?"),
    ]
    assert prepared.denied == []


def test_prepare_rejects_the_whole_package_when_long_brief_sections_exceed_its_budget() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    with pytest.raises(SafetyDenied) as captured:
        PrivacyPolicy("balanced", 8, 600).prepare(
            _proposal(
                ContextCandidate("free_text", "brief_goal", "a" * 401, "local_task_context"),
                ContextCandidate("free_text", "brief_evidence", "b" * 401, "local_task_context"),
            ),
            MinimalContext(system_prompt="test"),
            task_id="task-1",
            session_id="session-1",
            provider="deepseek",
            purpose="architecture_tradeoff",
        )

    assert captured.value.code == "SAFETY_CLOUD_BLOCK"


def test_prepare_accepts_a_package_at_32768_bytes_and_rejects_one_byte_more() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    def brief_value_for_total_bytes(total_bytes: int) -> str:
        payload = [
            {"category": "free_text", "label": "brief_goal", "value": "", "redacted": False}
        ]
        overhead = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        return "x" * (total_bytes - overhead)

    policy = PrivacyPolicy("balanced", 8, 32_768)
    accepted = policy.prepare(
        _proposal(
            ContextCandidate(
                "free_text", "brief_goal", brief_value_for_total_bytes(32_768), "local_task_context"
            )
        ),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="deepseek",
        purpose="architecture_tradeoff",
    )

    assert accepted.prepared_context_bytes == 32_768

    with pytest.raises(SafetyDenied) as captured:
        policy.prepare(
            _proposal(
                ContextCandidate(
                    "free_text", "brief_goal", brief_value_for_total_bytes(32_769), "local_task_context"
                )
            ),
            MinimalContext(system_prompt="test"),
            task_id="task-1",
            session_id="session-1",
            provider="deepseek",
            purpose="architecture_tradeoff",
        )

    assert captured.value.code == "SAFETY_CLOUD_BLOCK"


@pytest.mark.parametrize("budget", [255, 65_537])
def test_privacy_policy_rejects_context_byte_budgets_outside_the_contract_range(budget: int) -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    with pytest.raises(Exception) as captured:
        PrivacyPolicy("balanced", 8, budget)

    assert getattr(captured.value, "code", None) == "CONFIG_ERROR"


@pytest.mark.parametrize("items", [0, 101])
def test_privacy_policy_rejects_context_item_limits_outside_the_contract_range(items: int) -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    with pytest.raises(Exception) as captured:
        PrivacyPolicy("balanced", items, 8192)

    assert getattr(captured.value, "code", None) == "CONFIG_ERROR"


@pytest.mark.parametrize("items,budget", [(1, 256), (100, 65_536)])
def test_privacy_policy_accepts_context_limit_boundary_values(items: int, budget: int) -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    policy = PrivacyPolicy("balanced", items, budget)

    assert (policy.max_context_items, policy.max_context_bytes) == (items, budget)


def test_prepare_accepts_allowlisted_local_task_entity_for_followup() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    prepared = PrivacyPolicy("balanced", 8, 2048).prepare(
        _proposal(ContextCandidate("user_entity", "language", "python", "local_task_context")),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="deepseek",
        purpose="architecture_tradeoff",
    )

    assert [(item.category, item.label, item.value) for item in prepared.candidates] == [
        ("user_entity", "language", "python")
    ]


def test_prepare_accepts_each_safe_local_unknown_and_rejects_model_spoofing() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    prepared = PrivacyPolicy("balanced", 12, 2048).prepare(
        _proposal(
            ContextCandidate("free_text", "brief_unknowns", "traffic profile", "local_task_context"),
            ContextCandidate("free_text", "brief_unknowns", "availability target", "local_task_context"),
            ContextCandidate("free_text", "brief_unknowns", "untrusted", "model_proposed"),
        ),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="glm",
        purpose="reasoning_complexity",
    )

    assert [item.value for item in prepared.candidates] == [
        "traffic profile",
        "availability target",
    ]
    assert [item.reason for item in prepared.denied] == [
        "brief_label_requires_local_task_context"
    ]


def test_credential_only_section_is_dropped_while_safe_sections_are_retained() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    secret = "api_key=sk-abcdefghijklmnopqrstuvwxyz123456"
    prepared = PrivacyPolicy("balanced", 12, 2048).prepare(
        _proposal(
            ContextCandidate("free_text", "brief_unknowns", secret, "local_task_context"),
            ContextCandidate("free_text", "brief_unknowns", "safe detail", "local_task_context"),
            ContextCandidate("free_text", "brief_unknowns", "x" * 401, "local_task_context"),
        ),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="glm",
        purpose="reasoning_complexity",
    )

    assert [item.value for item in prepared.candidates] == ["safe detail", "x" * 401]
    assert [item.reason for item in prepared.denied] == [
        "free text contains no task semantics after redaction"
    ]
    assert secret not in str(prepared)


def test_credential_only_section_is_denied_after_redaction() -> None:
    from src.safety.privacy_policy import PrivacyPolicy

    prepared = PrivacyPolicy("balanced", 8, 2048).prepare(
        _proposal(ContextCandidate("free_text", "brief_goal", "密码：123456", "local_task_context")),
        MinimalContext(system_prompt="test"),
        task_id="task-1",
        session_id="session-1",
        provider="glm",
        purpose="reasoning_complexity",
    )

    assert prepared.candidates == []
    assert [denial.reason for denial in prepared.denied] == [
        "free text contains no task semantics after redaction"
    ]
