"""The single network side-effect outlet for cloud advisory turns."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from src.core.interfaces import CloudAdvisoryBackend, CloudGrant
from src.core.schemas import (
    AdvisoryResult,
    CloudAuditEvent,
    CloudRequestPackage,
    LocalMindError,
    SafetyDenied,
)
from src.safety.authorization import AuthorizationGrant, AuthorizationManager
from src.safety.cloud_boundary import CloudBoundary

_PRE_FLIGHT_DENIAL_REASONS = frozenset({
    "user_cancelled",
    "authorization_expired",
    "session_mismatch",
    "superseded_by_new_input",
})


@dataclass
class SideEffectGateway:
    """Reserve, validate, consume, call and audit exactly one cloud turn."""

    boundary: CloudBoundary
    cloud_backend: CloudAdvisoryBackend | None
    authorization: AuthorizationManager
    audit_log: list[CloudAuditEvent] = field(default_factory=list)
    now: Callable[[], float] = time.time

    def execute_cloud_turn(
        self, package: CloudRequestPackage, grant: CloudGrant, task_id: str,
        intent_id: str, turn: int,
    ) -> AdvisoryResult:
        if self.cloud_backend is None:
            raise LocalMindError("CAPABILITY_MISMATCH", "Cloud backend is not configured", "当前后端不支持云端咨询。")
        if not isinstance(grant, AuthorizationGrant):
            raise SafetyDenied("SAFETY_CLOUD_BLOCK", "Cloud grant had a forged type", "数据发送到云端被安全策略拦截。")
        now = self.now()
        self.authorization.reserve_turn(grant, now)
        try:
            snapshot = self.authorization.validate(
                grant, package, task_id, package.session_id, package.provider, package.purpose, now
            )
            checked = self.boundary.check_request(package, grant, snapshot)
        except LocalMindError as exc:
            self.authorization.release_turn(grant)
            self._audit(package, grant, task_id, intent_id, turn, "denied", exc.code)
            raise
        self.authorization.consume_reserved_turn(grant, checked.context_bytes, now)
        try:
            result = self.cloud_backend.advise(checked)
            cleaned = self.boundary.check_response(result)
        except LocalMindError as exc:
            self.authorization.enter_cooldown(grant, now)
            self._audit(checked, grant, task_id, intent_id, turn, "denied" if isinstance(exc, SafetyDenied) else "error", exc.code)
            raise
        if not cleaned.needs_more_info:
            self.authorization.enter_cooldown(grant, now)
        self._audit(checked, grant, task_id, intent_id, turn, "allowed", "ok", cleaned)
        return cleaned

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        """Audit a pending authorization ending before any cloud turn begins."""

        if reason not in _PRE_FLIGHT_DENIAL_REASONS:
            raise SafetyDenied(
                "SAFETY_CLOUD_BLOCK",
                f"Unknown preflight cloud denial reason: {reason}",
                "数据发送到云端被安全策略拦截。",
            )
        self.audit_log.append(CloudAuditEvent(
            audit_id=uuid4().hex[:12],
            task_id=task_id,
            session_id=session_id,
            intent_id="",
            turn=0,
            provider="",
            purpose="",
            grant_id="",
            issued_by="",
            authorized_categories=[],
            context_items=[],
            package_context_items=0,
            package_context_bytes=0,
            consumed_turns=0,
            cooldown_until=None,
            verdict="denied",
            reason=reason,
            requested_context_categories=(),
            has_followup=False,
            timestamp=datetime.now(UTC).isoformat(),
        ))

    def _audit(
        self, package: CloudRequestPackage, grant: AuthorizationGrant, task_id: str,
        intent_id: str, turn: int, verdict: str, reason: str, result: AdvisoryResult | None = None,
    ) -> None:
        snapshot = self.authorization.usage_snapshot(grant)
        categories = _normalized_followup_categories(result) if result is not None else ()
        self.audit_log.append(CloudAuditEvent(
            audit_id=uuid4().hex[:12], task_id=task_id, session_id=package.session_id,
            intent_id=intent_id, turn=turn, provider=grant.provider, purpose=grant.purpose,
            grant_id=grant.grant_id, issued_by=grant.issued_by,
            authorized_categories=sorted(grant.authorized_categories),
            context_items=[{"category": item.category, "label": item.label, "redacted": item.redacted, "fingerprint_prefix": item.fingerprint[:12]} for item in package.context_items],
            package_context_items=len(package.context_items), package_context_bytes=package.context_bytes,
            consumed_turns=snapshot.consumed_turns, cooldown_until=self.authorization.cooldown_until(grant),
            verdict=verdict, reason=reason, requested_context_categories=categories,
            has_followup=bool(categories), timestamp=datetime.now(UTC).isoformat(),
        ))


def _normalized_followup_categories(result: AdvisoryResult) -> tuple[str, ...]:
    allowed = {"memory_evidence", "user_entity"}
    categories: list[str] = []
    for category in result.requested_context_categories:
        value = category.strip().lower() if isinstance(category, str) else ""
        if value in allowed and value not in categories:
            categories.append(value)
    return tuple(categories)
