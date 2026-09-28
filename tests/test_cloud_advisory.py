"""Tests for the protected cloud advisory execution path."""

from dataclasses import dataclass, field

import pytest

from src.core.interfaces import CloudAdvisoryBackend
from src.core.schemas import (
    AdvisoryResult,
    CloudRequestPackage,
    PreparedContextItem,
    PrivacyPreparation,
)
from src.safety.authorization import AuthorizationManager
from src.safety.privacy_policy import PrivacyPolicy


@dataclass
class RecordingCloudBackend(CloudAdvisoryBackend):
    response: AdvisoryResult
    requests: list[CloudRequestPackage] = field(default_factory=list)

    def advise(self, request: CloudRequestPackage) -> AdvisoryResult:
        self.requests.append(request)
        return self.response


def _authorized_package() -> tuple[AuthorizationManager, object, CloudRequestPackage]:
    item = PreparedContextItem("user_entity", "language", "python", False, "fingerprint")
    preparation = PrivacyPreparation([item], [], frozenset({"user_entity"}), 80)
    manager = AuthorizationManager(600, 3, 3, 2048, 300)
    grant = manager.create_user_grant(preparation, "task-1", "session-1", "deepseek", "advisory", 10.0)
    package = PrivacyPolicy("balanced", 3, 2048).build_package(preparation, grant)
    return manager, grant, package


def test_side_effect_gateway_consumes_before_network_and_audits_safe_metadata() -> None:
    from src.safety.cloud_boundary import CloudBoundary
    from src.safety.side_effect_gateway import SideEffectGateway

    manager, grant, package = _authorized_package()
    backend = RecordingCloudBackend(
        AdvisoryResult(
            analysis="Use an index.",
            needs_more_info=True,
            requested_context_categories=("memory_evidence",),
            followup_question="Send the customer query.",
        )
    )
    audit_log = []
    gateway = SideEffectGateway(CloudBoundary(), backend, manager, audit_log, now=lambda: 11.0)

    result = gateway.execute_cloud_turn(package, grant, "task-1", "intent-1", 1)

    assert result.analysis == "Use an index."
    assert manager.remaining_turns("task-1") == 2
    assert audit_log[0].context_items == [{
        "category": "user_entity", "label": "language", "redacted": False, "fingerprint_prefix": "fingerprint"[:12]
    }]
    assert "python" not in str(audit_log[0])
    assert audit_log[0].requested_context_categories == ("memory_evidence",)
    assert audit_log[0].has_followup is True
    assert "customer query" not in str(audit_log[0])


def test_cloud_service_suspends_for_allowlisted_followup_categories() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService

    _, grant, package = _authorized_package()

    @dataclass
    class Gateway:
        calls: list[CloudRequestPackage] = field(default_factory=list)

        def execute_cloud_turn(self, request, received_grant, task_id, intent_id, turn):
            assert received_grant is grant
            self.calls.append(request)
            return AdvisoryResult(
                "more",
                needs_more_info=True,
                requested_context_categories=("memory_evidence", "unknown_category"),
                followup_question="Please provide more evidence.",
            )

    gateway = Gateway()
    result = CloudAdvisoryService(gateway, max_turns=3).consult(package, grant, "task-1", "intent-1")

    assert result.status == "suspended"
    assert result.result is not None
    assert result.result.analysis == "more"
    assert result.requested_categories == ("memory_evidence",)
    assert [item.turn for item in gateway.calls] == [1]


def test_real_gateway_converges_when_followup_has_no_allowlisted_category() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.safety.cloud_boundary import CloudBoundary
    from src.safety.side_effect_gateway import SideEffectGateway

    @dataclass
    class TwoTurnBackend(CloudAdvisoryBackend):
        calls: int = 0

        def advise(self, request: CloudRequestPackage) -> AdvisoryResult:
            del request
            self.calls += 1
            return AdvisoryResult("more", needs_more_info=True, requested_context_categories=("unknown",))

    manager, grant, package = _authorized_package()
    backend = TwoTurnBackend()
    service = CloudAdvisoryService(
        SideEffectGateway(CloudBoundary(), backend, manager, [], now=lambda: 11.0),
        max_turns=3,
    )

    result = service.consult(package, grant, "task-1", "intent-1")

    assert result.status == "completed"
    assert result.result is not None
    assert result.result.analysis == "more"
    assert result.result.needs_more_info is False
    assert backend.calls == 1


def test_gateway_rejects_a_forged_protocol_grant_before_network() -> None:
    from src.safety.cloud_boundary import CloudBoundary
    from src.safety.side_effect_gateway import SideEffectGateway

    manager, _, package = _authorized_package()
    backend = RecordingCloudBackend(AdvisoryResult(analysis="unused"))
    gateway = SideEffectGateway(CloudBoundary(), backend, manager, [], now=lambda: 11.0)

    with pytest.raises(Exception) as captured:
        gateway.execute_cloud_turn(package, object(), "task-1", "intent-1", 1)

    assert getattr(captured.value, "code", None) == "SAFETY_CLOUD_BLOCK"
    assert backend.requests == []


def test_gateway_records_a_minimal_preflight_denial_without_changing_usage() -> None:
    from src.safety.cloud_boundary import CloudBoundary
    from src.safety.side_effect_gateway import SideEffectGateway

    manager, grant, _ = _authorized_package()
    audit_log = []
    gateway = SideEffectGateway(
        CloudBoundary(), RecordingCloudBackend(AdvisoryResult(analysis="unused")), manager, audit_log
    )

    gateway.record_denial("task-1", "session-1", "user_cancelled")

    assert len(audit_log) == 1
    event = audit_log[0]
    assert event.task_id == "task-1"
    assert event.session_id == "session-1"
    assert event.verdict == "denied"
    assert event.reason == "user_cancelled"
    assert event.turn == 0
    assert event.provider == event.grant_id == event.issued_by == event.intent_id == ""
    assert event.authorized_categories == []
    assert event.context_items == []
    assert event.package_context_items == event.package_context_bytes == event.consumed_turns == 0
    assert event.cooldown_until is None
    assert event.requested_context_categories == ()
    assert event.has_followup is False
    assert manager.usage_snapshot(grant).consumed_turns == 0

    with pytest.raises(Exception) as captured:
        gateway.record_denial("task-1", "session-1", "not_a_valid_reason")

    assert getattr(captured.value, "code", None) == "SAFETY_CLOUD_BLOCK"
