"""Behavioral tests for the P4 cloud safety boundary."""

import pytest

from src.core.schemas import AdvisoryResult, CloudRequestPackage, PreparedContextItem, SafetyDenied
from src.safety.authorization import AuthorizationGrant, GrantUsageSnapshot


def _item() -> PreparedContextItem:
    return PreparedContextItem("user_entity", "language", "python", False, "fingerprint")


def _grant() -> AuthorizationGrant:
    return AuthorizationGrant(
        "grant-1", "task-1", "session-1", "deepseek", "advisory",
        frozenset({"user_entity"}), frozenset({"fingerprint"}), 3, 3, 2048, 99.0, "user",
    )


def _package() -> CloudRequestPackage:
    return CloudRequestPackage(
        "task-1", "session-1", "deepseek", "advisory", "grant-1", [_item()], "advice only", 1
    )


def test_cloud_boundary_accepts_grant_bound_package() -> None:
    from src.safety.cloud_boundary import CloudBoundary

    assert CloudBoundary().check_request(_package(), _grant(), GrantUsageSnapshot()) == _package()


def test_cloud_boundary_allows_authorized_non_secret_log_text() -> None:
    from src.safety.cloud_boundary import CloudBoundary

    item = PreparedContextItem("free_text", "log", "timeout while indexing", False, "log-fingerprint")
    grant = AuthorizationGrant(
        "grant-1", "task-1", "session-1", "deepseek", "advisory",
        frozenset({"free_text"}), frozenset({"log-fingerprint"}), 3, 8, 2048, 99.0, "user",
    )
    package = CloudRequestPackage(
        "task-1", "session-1", "deepseek", "advisory", "grant-1", [item], "advice only", 1
    )

    assert CloudBoundary().check_request(package, grant, GrantUsageSnapshot()) == package


def test_cloud_boundary_allows_only_safely_redacted_free_text() -> None:
    from src.safety.cloud_boundary import CloudBoundary

    item = PreparedContextItem(
        "free_text",
        "brief_goal",
        "Analyze [已脱敏:secret] without exposing it.",
        True,
        "redacted-fingerprint",
    )
    grant = AuthorizationGrant(
        "grant-1", "task-1", "session-1", "deepseek", "advisory",
        frozenset({"free_text"}), frozenset({"redacted-fingerprint"}),
        3, 8, 2048, 99.0, "user",
    )
    package = CloudRequestPackage(
        "task-1", "session-1", "deepseek", "advisory", "grant-1",
        [item], "advice only", 1,
    )

    assert CloudBoundary().check_request(package, grant, GrantUsageSnapshot()) == package

    malformed = CloudRequestPackage(
        package.task_id,
        package.session_id,
        package.provider,
        package.purpose,
        package.grant_id,
        [PreparedContextItem("free_text", "brief_goal", "hidden", True, "redacted-fingerprint")],
        package.allowed_scope,
        package.turn,
    )
    with pytest.raises(SafetyDenied):
        CloudBoundary().check_request(malformed, grant, GrantUsageSnapshot())


@pytest.mark.parametrize("package", [
    CloudRequestPackage("task-1", "session-1", "wrong", "advisory", "grant-1", [_item()], "advice", 1),
    CloudRequestPackage("task-1", "session-1", "deepseek", "advisory", "grant-1", [_item()], "advice", 2),
    CloudRequestPackage("task-1", "session-1", "deepseek", "advisory", "grant-1", [
        PreparedContextItem("user_entity", "language", "python", False, "other")
    ], "advice", 1),
])
def test_cloud_boundary_denies_binding_turn_or_fingerprint_mismatch(package: CloudRequestPackage) -> None:
    from src.safety.cloud_boundary import CloudBoundary

    with pytest.raises(SafetyDenied) as captured:
        CloudBoundary().check_request(package, _grant(), GrantUsageSnapshot())

    assert captured.value.code == "SAFETY_CLOUD_BLOCK"


def test_cloud_boundary_forces_local_validation_on_advisory_response() -> None:
    from src.safety.cloud_boundary import CloudBoundary

    checked = CloudBoundary().check_response(
        AdvisoryResult(analysis="Use an index.", requires_local_validation=False)
    )

    assert checked.requires_local_validation is True


def test_cloud_boundary_blocks_executable_cloud_response_markers() -> None:
    from src.safety.cloud_boundary import CloudBoundary

    with pytest.raises(SafetyDenied) as captured:
        CloudBoundary().check_response(AdvisoryResult(analysis="Here is an execution_plan."))

    assert captured.value.code == "SAFETY_CLOUD_BLOCK"
