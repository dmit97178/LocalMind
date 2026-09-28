"""Independent final validation for authorized cloud advisory packages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from src.core.schemas import AdvisoryResult, CloudRequestPackage, PreparedContextItem, SafetyDenied
from src.safety.authorization import AuthorizationGrant, GrantUsageSnapshot
from src.safety.guarded_executor import contains_bare_secret, contains_sensitive_value
from src.safety.secret_scan import SECRET_REDACTION_PLACEHOLDER

_EXECUTABLE_MARKERS = {"approved", "execution_plan", "tool_calls"}
_ALLOWED_CATEGORIES = {"user_entity", "free_text", "secret_placeholder"}


class CloudBoundary:
    """Fail closed when a package expands or contradicts its local authorization."""

    def check_request(
        self,
        package: CloudRequestPackage,
        grant: AuthorizationGrant,
        usage_snapshot: GrantUsageSnapshot,
    ) -> CloudRequestPackage:
        if not isinstance(package, CloudRequestPackage):
            raise _cloud_denied("Cloud request is not a CloudRequestPackage")
        if not isinstance(grant, AuthorizationGrant) or not isinstance(usage_snapshot, GrantUsageSnapshot):
            raise _cloud_denied("Cloud authorization or usage snapshot had an invalid type")
        if (package.task_id, package.session_id, package.provider, package.purpose, package.grant_id) != (
            grant.task_id, grant.session_id, grant.provider, grant.purpose, grant.grant_id,
        ):
            raise _cloud_denied("Cloud package binding did not match grant")
        if package.turn != usage_snapshot.consumed_turns + 1:
            raise _cloud_denied("Cloud package turn did not match consumed turns")
        if not isinstance(package.allowed_scope, str) or not package.allowed_scope.strip():
            raise _cloud_denied("Cloud request scope is not non-empty text")
        if len(package.context_items) > grant.max_context_items or package.context_bytes > grant.max_context_bytes:
            raise _cloud_denied("Cloud package exceeds authorized bounds")
        for item in package.context_items:
            self._check_item(item, grant)
        return package

    def check_response(self, result: AdvisoryResult) -> AdvisoryResult:
        if not isinstance(result, AdvisoryResult) or not isinstance(result.analysis, str):
            raise _cloud_denied("Cloud response has an invalid analysis field")
        if _contains_executable_marker(result.analysis) or _contains_executable_marker(result.suggested_tools):
            raise _cloud_denied("Cloud response contains executable markers", user_message="云端返回内容被安全策略拦截。")
        return replace(result, requires_local_validation=True)

    @staticmethod
    def _check_item(item: object, grant: AuthorizationGrant) -> None:
        if not isinstance(item, PreparedContextItem):
            raise _cloud_denied("Cloud package item had an invalid type")
        if item.category not in _ALLOWED_CATEGORIES or item.category not in grant.authorized_categories:
            raise _cloud_denied("Cloud package item category was unauthorized")
        if item.fingerprint not in grant.payload_fingerprints:
            raise _cloud_denied("Cloud package item fingerprint was unauthorized")
        if not isinstance(item.value, str | int | float | bool) or isinstance(item.value, float) and not item.value == item.value:
            raise _cloud_denied("Cloud package item value was not a finite scalar")
        if item.category == "secret_placeholder":
            if not item.redacted or item.value != "present":
                raise _cloud_denied("Secret placeholder was malformed")
            return
        if item.redacted and not (
            item.category == "free_text"
            and isinstance(item.value, str)
            and SECRET_REDACTION_PLACEHOLDER in item.value
        ):
            raise _cloud_denied("Cloud package item was not eligible for egress")
        if isinstance(item.value, str) and (contains_bare_secret(item.value) or contains_sensitive_value(item.value)):
            raise _cloud_denied("Cloud package item still contained sensitive text")


def _contains_executable_marker(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in _EXECUTABLE_MARKERS)
    if isinstance(value, Mapping):
        return any(_contains_executable_marker(key) or _contains_executable_marker(item) for key, item in value.items())
    if isinstance(value, Sequence):
        return any(_contains_executable_marker(item) for item in value)
    return False


def _cloud_denied(message: str, *, user_message: str = "数据发送到云端被安全策略拦截。") -> SafetyDenied:
    return SafetyDenied("SAFETY_CLOUD_BLOCK", message, user_message, recoverable=False)
