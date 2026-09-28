"""Finite, task-bound authorization grants for cloud advisory calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from src.core.schemas import CloudRequestPackage, LocalMindError, PrivacyPreparation


@dataclass(frozen=True)
class AuthorizationGrant:
    """Immutable upper bound for one task's cloud consultation."""

    grant_id: str
    task_id: str
    session_id: str
    provider: str
    purpose: str
    authorized_categories: frozenset[str]
    payload_fingerprints: frozenset[str]
    max_turns: int
    max_context_items: int
    max_context_bytes: int
    expires_at: float
    issued_by: str


@dataclass
class GrantUsage:
    reserved_turns: int = 0
    consumed_turns: int = 0
    consumed_context_bytes: int = 0
    cooldown_until: float | None = None


@dataclass(frozen=True)
class GrantUsageSnapshot:
    consumed_turns: int = 0


@dataclass
class _TaskLedger:
    consumed_turns: int = 0
    expansion_count: int = 0
    authorized_categories: set[str] = field(default_factory=set)
    payload_fingerprints: set[str] = field(default_factory=set)
    cooldown_until: float | None = None


class AuthorizationManager:
    """Own mutable grant usage state; only the protected gateway consumes it."""

    def __init__(
        self,
        grant_ttl_seconds: int,
        max_turns_per_task: int,
        max_context_items: int,
        max_context_bytes: int,
        cooldown_seconds: int,
    ) -> None:
        _bounded_int(grant_ttl_seconds, "grant_ttl_seconds", 1, 86_400)
        _bounded_int(max_turns_per_task, "max_turns_per_task", 1, 3)
        _bounded_int(max_context_items, "max_context_items", 1, 100)
        _bounded_int(max_context_bytes, "max_context_bytes", 256, 65_536)
        _bounded_int(cooldown_seconds, "cooldown_seconds", 1, 3600)
        self._grant_ttl_seconds = grant_ttl_seconds
        self._max_turns_per_task = max_turns_per_task
        self._max_context_items = max_context_items
        self._max_context_bytes = max_context_bytes
        self._cooldown_seconds = cooldown_seconds
        self._usage: dict[str, GrantUsage] = {}
        self._task_grants: dict[str, str] = {}
        self._task_ledgers: dict[str, _TaskLedger] = {}

    def create_user_grant(
        self, preparation: PrivacyPreparation, task_id: str, session_id: str,
        provider: str, purpose: str, now: float,
    ) -> AuthorizationGrant:
        return self._create_grant(preparation, task_id, session_id, provider, purpose, now, "user")

    def create_policy_grant(
        self, preparation: PrivacyPreparation, task_id: str, session_id: str,
        provider: str, purpose: str, now: float, *, escalation_risk: str = "sensitive",
    ) -> AuthorizationGrant:
        if escalation_risk != "normal":
            raise _authorization_required(
                "Policy grants require normal effective authorization risk",
                reason="sensitive_policy_grant_forbidden",
            )
        ledger = self._ledger_for(task_id)
        additions = [
            item for item in preparation.candidates
            if item.fingerprint not in ledger.payload_fingerprints
        ]
        if not additions:
            raise _authorization_required("Policy grants require a new low-risk user entity")
        if any(item.category != "user_entity" for item in additions):
            raise _authorization_required("Policy grants only add low-risk user entities")
        return self._create_grant(
            preparation, task_id, session_id, provider, purpose, now, "privacy_policy"
        )

    def validate(
        self, grant: AuthorizationGrant, package: CloudRequestPackage, task_id: str,
        session_id: str, provider: str, purpose: str, now: float,
    ) -> GrantUsageSnapshot:
        if not isinstance(grant, AuthorizationGrant) or not isinstance(package, CloudRequestPackage):
            raise _authorization_expired("Grant or package had an invalid type")
        if now >= grant.expires_at:
            raise _authorization_expired("Grant expired")
        if (grant.task_id, grant.session_id, grant.provider, grant.purpose) != (
            task_id, session_id, provider, purpose,
        ):
            raise _authorization_expired("Grant binding did not match request")
        if (package.task_id, package.session_id, package.provider, package.purpose, package.grant_id) != (
            grant.task_id, grant.session_id, grant.provider, grant.purpose, grant.grant_id,
        ):
            raise _authorization_expired("Package binding did not match grant")
        usage = self._usage_for(grant)
        ledger = self._ledger_for(grant.task_id)
        if ledger.cooldown_until is not None and now < ledger.cooldown_until:
            raise _cooldown_error()
        if (
            usage.consumed_turns + usage.reserved_turns > grant.max_turns
            or ledger.consumed_turns + usage.reserved_turns > self._max_turns_per_task
        ):
            raise _budget_error()
        if package.turn != usage.consumed_turns + 1:
            raise _authorization_required("Package turn does not follow consumed turns")
        if len(package.context_items) > grant.max_context_items or package.context_bytes > grant.max_context_bytes:
            raise _authorization_required("Package exceeds its authorized context bounds")
        for item in package.context_items:
            if item.category not in grant.authorized_categories or item.fingerprint not in grant.payload_fingerprints:
                raise _authorization_required("Package contains an unauthorized context item")
        return GrantUsageSnapshot(consumed_turns=usage.consumed_turns)

    def reserve_turn(self, grant: AuthorizationGrant, now: float) -> None:
        usage = self._usage_for(grant)
        if now >= grant.expires_at:
            raise _authorization_expired("Grant expired")
        ledger = self._ledger_for(grant.task_id)
        if ledger.cooldown_until is not None and now < ledger.cooldown_until:
            raise _cooldown_error()
        if (
            usage.consumed_turns + usage.reserved_turns >= grant.max_turns
            or ledger.consumed_turns + usage.reserved_turns >= self._max_turns_per_task
        ):
            raise _budget_error()
        usage.reserved_turns += 1

    def release_turn(self, grant: AuthorizationGrant) -> None:
        usage = self._usage_for(grant)
        if usage.reserved_turns:
            usage.reserved_turns -= 1

    def consume_reserved_turn(
        self, grant: AuthorizationGrant, package_context_bytes: int, now: float
    ) -> GrantUsageSnapshot:
        del now
        usage = self._usage_for(grant)
        if usage.reserved_turns < 1:
            raise _budget_error()
        usage.reserved_turns -= 1
        usage.consumed_turns += 1
        usage.consumed_context_bytes += package_context_bytes
        self._ledger_for(grant.task_id).consumed_turns += 1
        return GrantUsageSnapshot(consumed_turns=usage.consumed_turns)

    def enter_cooldown(self, grant: AuthorizationGrant, now: float) -> None:
        cooldown_until = now + self._cooldown_seconds
        self._usage_for(grant).cooldown_until = cooldown_until
        self._ledger_for(grant.task_id).cooldown_until = cooldown_until

    def revoke_task(self, task_id: str, session_id: str) -> None:
        grant_id = self._task_grants.get(task_id)
        if grant_id is not None:
            grant_usage = self._usage.get(grant_id)
            if grant_usage is not None:
                grant_usage.reserved_turns = 0
            self._usage.pop(grant_id, None)
            self._task_grants.pop(task_id, None)

    def remaining_turns(self, task_id: str) -> int:
        grant_id = self._task_grants.get(task_id)
        if grant_id is None:
            ledger = self._task_ledgers.get(task_id)
            return max(0, self._max_turns_per_task - ledger.consumed_turns) if ledger else self._max_turns_per_task
        usage = self._usage.get(grant_id)
        ledger = self._task_ledgers.get(task_id)
        consumed = ledger.consumed_turns if ledger else 0
        return max(0, self._max_turns_per_task - consumed - (usage.reserved_turns if usage else 0))

    def cooldown_active(self, task_id: str, now: float) -> bool:
        ledger = self._task_ledgers.get(task_id)
        return bool(ledger and ledger.cooldown_until is not None and now < ledger.cooldown_until)

    def usage_snapshot(self, grant: AuthorizationGrant) -> GrantUsageSnapshot:
        return GrantUsageSnapshot(consumed_turns=self._usage_for(grant).consumed_turns)

    def cooldown_until(self, grant: AuthorizationGrant) -> float | None:
        return self._ledger_for(grant.task_id).cooldown_until

    def _create_grant(
        self, preparation: PrivacyPreparation, task_id: str, session_id: str,
        provider: str, purpose: str, now: float, issued_by: str,
    ) -> AuthorizationGrant:
        if not all(isinstance(value, str) and value for value in (task_id, session_id, provider, purpose)):
            raise _authorization_required("Grant binding values must be non-empty")
        if not preparation.candidates:
            raise _authorization_required("Cannot grant an empty package")
        if len(preparation.candidates) > self._max_context_items or preparation.prepared_context_bytes > self._max_context_bytes:
            raise _authorization_required("Preparation exceeds configured bounds")
        ledger = self._ledger_for(task_id)
        if ledger.consumed_turns >= self._max_turns_per_task:
            raise _budget_error()
        fingerprints = {item.fingerprint for item in preparation.candidates}
        categories = set(preparation.required_categories)
        is_first_grant = not ledger.authorized_categories and not ledger.payload_fingerprints
        is_expansion = not categories <= ledger.authorized_categories or not fingerprints <= ledger.payload_fingerprints
        if not is_first_grant and is_expansion and ledger.expansion_count >= 2:
            raise _budget_error()
        old_grant_id = self._task_grants.get(task_id)
        if old_grant_id is not None:
            self._usage.pop(old_grant_id, None)
        grant = AuthorizationGrant(
            grant_id=uuid4().hex,
            task_id=task_id,
            session_id=session_id,
            provider=provider,
            purpose=purpose,
            authorized_categories=preparation.required_categories,
            payload_fingerprints=frozenset(item.fingerprint for item in preparation.candidates),
            max_turns=self._max_turns_per_task,
            max_context_items=self._max_context_items,
            max_context_bytes=self._max_context_bytes,
            expires_at=now + self._grant_ttl_seconds,
            issued_by=issued_by,
        )
        self._usage[grant.grant_id] = GrantUsage()
        self._task_grants[task_id] = grant.grant_id
        if not is_first_grant and is_expansion:
            ledger.expansion_count += 1
        ledger.authorized_categories.update(categories)
        ledger.payload_fingerprints.update(fingerprints)
        return grant

    def _usage_for(self, grant: AuthorizationGrant) -> GrantUsage:
        usage = self._usage.get(grant.grant_id)
        if usage is None:
            raise _authorization_expired("Grant is not active")
        return usage

    def _ledger_for(self, task_id: str) -> _TaskLedger:
        return self._task_ledgers.setdefault(task_id, _TaskLedger())


def _bounded_int(value: object, name: str, low: int, high: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise LocalMindError("CONFIG_ERROR", f"{name} must be {low}..{high}", "系统配置有误，请检查 cloud_advisory.config。")


def _cloud_error(code: str, message: str, user_message: str) -> LocalMindError:
    return LocalMindError(code, message, user_message, recoverable=False)


def _authorization_required(
    message: str, *, reason: str | None = None
) -> LocalMindError:
    error = _cloud_error(
        "CLOUD_AUTHORIZATION_REQUIRED",
        message,
        "该云端咨询需要你的确认后才能发送。",
    )
    error.details = {"reason": reason} if reason is not None else None
    return error


def _authorization_expired(message: str) -> LocalMindError:
    return _cloud_error("CLOUD_AUTHORIZATION_EXPIRED", message, "云端授权已失效，需要重新确认。")


def _budget_error() -> LocalMindError:
    return _cloud_error("CLOUD_BUDGET_EXCEEDED", "Cloud turn budget is exhausted", "本次云端咨询已达到预算限制。")


def _cooldown_error() -> LocalMindError:
    return _cloud_error("CLOUD_COOLDOWN_ACTIVE", "Cloud task is cooling down", "云端咨询暂处于冷却期，请稍后再试。")
