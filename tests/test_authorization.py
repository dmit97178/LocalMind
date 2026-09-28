"""Tests for finite, task-bound cloud authorization grants."""

import pytest

from src.core.schemas import (
    PreparedContextItem,
    PrivacyPreparation,
)


def _preparation() -> PrivacyPreparation:
    return PrivacyPreparation(
        candidates=[
            PreparedContextItem(
                category="user_entity",
                label="language",
                value="python",
                redacted=False,
                fingerprint="local-fingerprint",
            )
        ],
        denied=[],
        required_categories=frozenset({"user_entity"}),
        prepared_context_bytes=80,
    )


def _prepared(*items: PreparedContextItem) -> PrivacyPreparation:
    return PrivacyPreparation(
        candidates=list(items),
        denied=[],
        required_categories=frozenset(item.category for item in items),
        prepared_context_bytes=80 * len(items),
    )


def _item(category: str, fingerprint: str) -> PreparedContextItem:
    if category == "user_entity":
        return PreparedContextItem(category, "language", "python", False, fingerprint)
    return PreparedContextItem(
        category, "brief_goal", "Analyze the retry design.", False, fingerprint
    )


def test_authorization_grant_is_bound_and_cannot_be_used_by_another_session() -> None:
    from src.safety.authorization import AuthorizationManager
    from src.safety.privacy_policy import PrivacyPolicy

    manager = AuthorizationManager(600, 3, 3, 2048, 300)
    preparation = _preparation()
    grant = manager.create_user_grant(
        preparation, "task-1", "session-1", "deepseek", "advisory", now=10.0
    )
    package = PrivacyPolicy("balanced", 3, 2048).build_package(preparation, grant)

    with pytest.raises(Exception) as captured:
        manager.validate(
            grant, package, "task-1", "other-session", "deepseek", "advisory", now=11.0
        )

    assert getattr(captured.value, "code", None) == "CLOUD_AUTHORIZATION_EXPIRED"


@pytest.mark.parametrize("budget", [255, 65_537])
def test_authorization_manager_rejects_context_byte_budgets_outside_the_contract_range(budget: int) -> None:
    from src.safety.authorization import AuthorizationManager

    with pytest.raises(Exception) as captured:
        AuthorizationManager(600, 3, 8, budget, 300)

    assert getattr(captured.value, "code", None) == "CONFIG_ERROR"


@pytest.mark.parametrize("items,budget", [(1, 256), (100, 65_536)])
def test_authorization_manager_accepts_context_limit_boundary_values(items: int, budget: int) -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, items, budget, 300)

    assert (manager._max_context_items, manager._max_context_bytes) == (items, budget)


def test_authorization_grant_cannot_be_reused_for_another_provider() -> None:
    from dataclasses import replace

    from src.safety.authorization import AuthorizationManager
    from src.safety.privacy_policy import PrivacyPolicy

    manager = AuthorizationManager(600, 3, 3, 2048, 300)
    preparation = _preparation()
    grant = manager.create_user_grant(
        preparation, "task-1", "session-1", "deepseek", "advisory", now=10.0
    )
    package = PrivacyPolicy("balanced", 3, 2048).build_package(preparation, grant)
    glm_package = replace(package, provider="glm")

    with pytest.raises(Exception) as captured:
        manager.validate(
            grant,
            glm_package,
            "task-1",
            "session-1",
            "glm",
            "advisory",
            now=11.0,
        )

    assert getattr(captured.value, "code", None) == "CLOUD_AUTHORIZATION_EXPIRED"


def test_authorization_reservation_consumes_turn_before_network_and_sets_cooldown() -> None:
    from src.safety.authorization import AuthorizationManager
    from src.safety.privacy_policy import PrivacyPolicy

    manager = AuthorizationManager(600, 1, 3, 2048, 300)
    preparation = _preparation()
    grant = manager.create_user_grant(
        preparation, "task-1", "session-1", "deepseek", "advisory", now=10.0
    )
    package = PrivacyPolicy("balanced", 3, 2048).build_package(preparation, grant)

    manager.reserve_turn(grant, now=11.0)
    snapshot = manager.validate(
        grant, package, "task-1", "session-1", "deepseek", "advisory", now=11.0
    )
    assert snapshot.consumed_turns == 0
    consumed = manager.consume_reserved_turn(grant, package.context_bytes, now=11.0)
    manager.enter_cooldown(grant, now=11.0)

    assert consumed.consumed_turns == 1
    assert manager.remaining_turns("task-1") == 0
    assert manager.cooldown_active("task-1", now=12.0) is True


def test_task_ledger_caps_expansions_and_revokes_the_previous_active_grant() -> None:
    from src.safety.authorization import AuthorizationManager

    def preparation(fingerprint: str) -> PrivacyPreparation:
        return PrivacyPreparation(
            candidates=[
                PreparedContextItem("user_entity", "language", "python", False, fingerprint)
            ],
            denied=[],
            required_categories=frozenset({"user_entity"}),
            prepared_context_bytes=80,
        )

    manager = AuthorizationManager(600, 3, 8, 2048, 300)
    first = manager.create_user_grant(
        preparation("first"), "task-1", "session-1", "deepseek", "architecture_tradeoff", 10.0
    )
    second = manager.create_user_grant(
        preparation("second"), "task-1", "session-1", "deepseek", "architecture_tradeoff", 11.0
    )
    third = manager.create_user_grant(
        preparation("third"), "task-1", "session-1", "deepseek", "architecture_tradeoff", 12.0
    )

    with pytest.raises(Exception) as old_grant:
        manager.usage_snapshot(first)
    assert getattr(old_grant.value, "code", None) == "CLOUD_AUTHORIZATION_EXPIRED"
    assert manager.usage_snapshot(third).consumed_turns == 0

    with pytest.raises(Exception) as expansion_limit:
        manager.create_user_grant(
            preparation("fourth"), "task-1", "session-1", "deepseek", "architecture_tradeoff", 13.0
        )
    assert getattr(expansion_limit.value, "code", None) == "CLOUD_BUDGET_EXCEEDED"
    assert second.grant_id != third.grant_id


def test_policy_grant_allows_an_all_entity_first_preparation() -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)

    grant = manager.create_policy_grant(
        _prepared(_item("user_entity", "entity-1")),
        "task-1",
        "session-1",
        "deepseek",
        "architecture_tradeoff",
        10.0,
        escalation_risk="normal",
    )

    assert grant.issued_by == "privacy_policy"


def test_policy_grant_rejects_a_free_text_first_preparation() -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)

    with pytest.raises(Exception) as captured:
        manager.create_policy_grant(
            _prepared(_item("user_entity", "entity-1"), _item("free_text", "brief-1")),
            "task-1",
            "session-1",
            "deepseek",
            "architecture_tradeoff",
            10.0,
        )

    assert getattr(captured.value, "code", None) == "CLOUD_AUTHORIZATION_REQUIRED"


def test_policy_grant_inherits_user_authorized_text_and_adds_an_entity() -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)
    manager.create_user_grant(
        _prepared(_item("free_text", "brief-1")),
        "task-1",
        "session-1",
        "deepseek",
        "architecture_tradeoff",
        10.0,
    )

    grant = manager.create_policy_grant(
        _prepared(_item("free_text", "brief-1"), _item("user_entity", "entity-1")),
        "task-1",
        "session-1",
        "deepseek",
        "architecture_tradeoff",
        11.0,
        escalation_risk="normal",
    )

    assert grant.issued_by == "privacy_policy"
    assert grant.payload_fingerprints == frozenset({"brief-1", "entity-1"})


@pytest.mark.parametrize("risk", ["sensitive", "dangerous", "unknown"])
def test_policy_grant_rejects_non_normal_authorization_risk_without_state_change(
    risk: str,
) -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)
    before = manager.remaining_turns("task-1")

    with pytest.raises(Exception) as captured:
        manager.create_policy_grant(
            _prepared(_item("user_entity", "entity-1")),
            "task-1",
            "session-1",
            "deepseek",
            "architecture_tradeoff",
            10.0,
            escalation_risk=risk,
        )

    assert getattr(captured.value, "code", None) == "CLOUD_AUTHORIZATION_REQUIRED"
    assert getattr(captured.value, "recoverable", None) is False
    assert getattr(captured.value, "details", {}).get("reason") == (
        "sensitive_policy_grant_forbidden"
    )
    assert manager.remaining_turns("task-1") == before
    assert "task-1" not in manager._task_grants


def test_policy_grant_default_risk_fails_closed() -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)

    with pytest.raises(Exception) as captured:
        manager.create_policy_grant(
            _prepared(_item("user_entity", "entity-1")),
            "task-1",
            "session-1",
            "deepseek",
            "architecture_tradeoff",
            10.0,
        )

    assert getattr(captured.value, "details", {}).get("reason") == (
        "sensitive_policy_grant_forbidden"
    )


def test_policy_grant_rejects_new_free_text_after_user_authorization() -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)
    manager.create_user_grant(
        _prepared(_item("free_text", "brief-1")),
        "task-1",
        "session-1",
        "deepseek",
        "architecture_tradeoff",
        10.0,
    )

    with pytest.raises(Exception) as captured:
        manager.create_policy_grant(
            _prepared(_item("free_text", "brief-1"), _item("free_text", "brief-2")),
            "task-1",
            "session-1",
            "deepseek",
            "architecture_tradeoff",
            11.0,
        )

    assert getattr(captured.value, "code", None) == "CLOUD_AUTHORIZATION_REQUIRED"


def test_policy_grant_rejects_a_preparation_with_no_new_fingerprint() -> None:
    from src.safety.authorization import AuthorizationManager

    manager = AuthorizationManager(600, 3, 8, 2048, 300)
    preparation = _prepared(_item("user_entity", "entity-1"))
    manager.create_user_grant(
        preparation, "task-1", "session-1", "deepseek", "architecture_tradeoff", 10.0
    )

    with pytest.raises(Exception) as captured:
        manager.create_policy_grant(
            preparation, "task-1", "session-1", "deepseek", "architecture_tradeoff", 11.0
        )

    assert getattr(captured.value, "code", None) == "CLOUD_AUTHORIZATION_REQUIRED"
