"""Deterministic reduction and redaction of model-proposed cloud context."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import unicodedata

from src.core.schemas import (
    CloudRequestPackage,
    ConsultationProposal,
    ContextCandidate,
    LocalMindError,
    PreparedContextItem,
    PrivacyDenial,
    PrivacyPreparation,
    SafetyDenied,
)
from src.safety.authorization import AuthorizationGrant
from src.safety.guarded_executor import contains_bare_secret, contains_sensitive_value
from src.safety.secret_scan import (
    CREDENTIAL_LABELS,
    SECRET_REDACTION_PLACEHOLDER,
    redact_outbound,
    scan_credentials,
)

_MODES = {"strict", "balanced", "convenient"}
_BRIEF_LABELS = {
    "brief_goal",
    "brief_constraints",
    "brief_facts",
    "brief_evidence",
    "brief_attempts",
    "brief_question",
    "brief_unknowns",
    "brief_project_note",
}
_LABEL_RE = re.compile(r"^[a-z0-9_]+$")
_MIN_CONTEXT_BYTES = 256
_MAX_CONTEXT_BYTES = 65_536
_USER_ENTITY_VALUES = {
    "language": {"python", "java", "go", "rust", "javascript", "typescript", "sql"},
    "database_engine": {"postgresql", "mysql", "sqlite", "mssql", "oracle"},
    "os_family": {"windows", "linux", "macos"},
    "runtime_family": {"python", "nodejs", "java", "dotnet"},
    "error_class": {"timeout", "connection_refused", "permission_denied", "not_found", "parse_error"},
    "project_kind": {"cli", "web", "api", "desktop", "data_pipeline"},
}


class PrivacyPolicy:
    """Prepare only bounded, redacted values; this class never sends a request."""

    def __init__(
        self,
        mode: str,
        max_context_items: int,
        max_context_bytes: int,
        allowed_scope: str = "仅提供分析建议，不生成执行命令或计划",
    ) -> None:
        if mode not in _MODES:
            raise _config_error("privacy_mode is invalid")
        if (
            not isinstance(max_context_items, int)
            or isinstance(max_context_items, bool)
            or not 1 <= max_context_items <= 100
        ):
            raise _config_error("max_context_items must be 1..100")
        if (
            not isinstance(max_context_bytes, int)
            or isinstance(max_context_bytes, bool)
            or not _MIN_CONTEXT_BYTES <= max_context_bytes <= _MAX_CONTEXT_BYTES
        ):
            raise _config_error(
                f"max_context_bytes must be {_MIN_CONTEXT_BYTES}..{_MAX_CONTEXT_BYTES}"
            )
        if not isinstance(allowed_scope, str) or not allowed_scope.strip():
            raise _config_error("allowed_scope must be non-empty")
        self.mode = mode
        self.max_context_items = max_context_items
        self.max_context_bytes = max_context_bytes
        self.allowed_scope = allowed_scope.strip()
        self._hmac_key = secrets.token_bytes(32)

    def prepare(
        self, proposal: ConsultationProposal | None, context: object, task_id: str,
        session_id: str, provider: str, purpose: str,
    ) -> PrivacyPreparation:
        del context, task_id, session_id, provider, purpose
        candidates: list[PreparedContextItem] = []
        denied: list[PrivacyDenial] = []
        model_free_text_seen = False
        for candidate in proposal.candidate_context if proposal else []:
            if candidate.category == "free_text" and candidate.source == "model_proposed":
                if model_free_text_seen:
                    denied.append(PrivacyDenial("free_text", "unknown", "too_many_model_free_text_candidates"))
                    continue
                model_free_text_seen = True
            accepted, denial = self._prepare_candidate(candidate)
            candidates.extend(accepted)
            if denial is not None:
                denied.append(denial)
        prepared_bytes = _items_bytes(candidates)
        if len(candidates) > self.max_context_items or prepared_bytes > self.max_context_bytes:
            raise SafetyDenied(
                "SAFETY_CLOUD_BLOCK", "Prepared cloud context exceeds package bounds",
                "数据发送到云端被安全策略拦截。", recoverable=False,
            )
        return PrivacyPreparation(
            candidates=candidates,
            denied=denied,
            required_categories=frozenset(item.category for item in candidates),
            prepared_context_bytes=prepared_bytes,
        )

    def build_package(
        self, preparation: PrivacyPreparation, grant: AuthorizationGrant, turn: int = 1
    ) -> CloudRequestPackage:
        if not isinstance(grant, AuthorizationGrant) or turn != 1:
            raise _authorization_required("First package requires a valid grant and turn one")
        if not preparation.candidates or not preparation.required_categories <= grant.authorized_categories:
            raise _authorization_required("Grant does not cover prepared categories")
        selected = [
            item for item in preparation.candidates if item.fingerprint in grant.payload_fingerprints
        ]
        if len(selected) != len(preparation.candidates):
            raise _authorization_required("Grant does not cover prepared payloads")
        if len(selected) > grant.max_context_items or _items_bytes(selected) > grant.max_context_bytes:
            raise _authorization_required("Grant package bounds were exceeded")
        return CloudRequestPackage(
            task_id=grant.task_id,
            session_id=grant.session_id,
            provider=grant.provider,
            purpose=grant.purpose,
            grant_id=grant.grant_id,
            context_items=selected,
            allowed_scope=self.allowed_scope,
            turn=turn,
        )

    def _prepare_candidate(
        self, candidate: ContextCandidate
    ) -> tuple[list[PreparedContextItem], PrivacyDenial | None]:
        category = candidate.category.strip().lower() if isinstance(candidate.category, str) else "unknown"
        raw_label = candidate.label.strip() if isinstance(candidate.label, str) else ""
        if contains_sensitive_value(raw_label) or contains_bare_secret(raw_label):
            return [], PrivacyDenial(category, "unknown", "sensitive_label")
        label = raw_label.lower() or "unknown"
        source = candidate.source if isinstance(candidate.source, str) else "unknown"
        if not _is_valid_label(label):
            return [], PrivacyDenial(category, "unknown", "invalid_label")
        is_brief_section = label in _BRIEF_LABELS
        if is_brief_section and source != "local_task_context":
            return [], PrivacyDenial(category, label, "brief_label_requires_local_task_context")
        is_allowlisted_local_entity = category == "user_entity" and label in _USER_ENTITY_VALUES
        if source == "local_task_context" and not (is_brief_section or is_allowlisted_local_entity):
            return [], PrivacyDenial(category, label, "unknown_local_task_context_label")
        if category == "secret":
            if label != "unknown":
                return [self._item("secret_placeholder", label, "present", True)], None
            return [], PrivacyDenial(category, label, "secret without a safe placeholder label")
        if category == "user_entity":
            value = candidate.value.strip().lower() if isinstance(candidate.value, str) else None
            if value is not None and value in _USER_ENTITY_VALUES.get(label, set()):
                return [self._item("user_entity", label, value, False)], None
            return [], PrivacyDenial(category, label, "not in the fixed allowlist")
        if category == "free_text":
            if not isinstance(candidate.value, str) or not candidate.value.strip():
                return [], PrivacyDenial(category, label, "free text is not non-empty text")
            value = candidate.value.strip()
            if (
                source == "model_proposed"
                and len(value.encode("utf-8")) > 1500
            ):
                return [], PrivacyDenial(category, label, "free_text_too_long")
            if contains_sensitive_value(value) or contains_bare_secret(value):
                hits = scan_credentials(value)
                redacted = redact_outbound(value)
                secret_labels = tuple(
                    dict.fromkeys(
                        hit.normalized_label
                        for hit in hits
                        if hit.normalized_label is not None
                    )
                )
                if contains_sensitive_value(redacted) or contains_bare_secret(redacted):
                    return [], PrivacyDenial(category, label, "free text contains residual sensitive data")
                if not _has_task_semantics(redacted):
                    return [], PrivacyDenial(category, label, "free text contains no task semantics after redaction")
                items = [self._item("free_text", label, redacted, True)]
                items.extend(
                    self._item("secret_placeholder", secret_label, "present", True)
                    for secret_label in secret_labels
                    if _is_valid_label(secret_label)
                )
                return items, None
            return [self._item("free_text", label, value, False)], None
        return [], PrivacyDenial(category, label, "untrusted or unsupported category")

    def _item(self, category: str, label: str, value: str | int | float | bool, redacted: bool) -> PreparedContextItem:
        serialized = json.dumps(
            {"category": category, "label": label, "value": value, "redacted": redacted},
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        )
        fingerprint = hmac.new(self._hmac_key, serialized.encode("utf-8"), hashlib.sha256).hexdigest()
        return PreparedContextItem(category, label, value, redacted, fingerprint)


def _items_bytes(items: list[PreparedContextItem]) -> int:
    payload = [
        {"category": item.category, "label": item.label, "value": item.value, "redacted": item.redacted}
        for item in items
    ]
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _is_valid_label(label: str) -> bool:
    return bool(label) and len(label) <= 64 and _LABEL_RE.fullmatch(label) is not None


def _has_task_semantics(value: str) -> bool:
    remainder = value.replace(SECRET_REDACTION_PLACEHOLDER, "")
    for label in sorted(CREDENTIAL_LABELS, key=len, reverse=True):
        remainder = re.sub(re.escape(label), "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"(?:等于|[=:：＝]|是|为)", "", remainder)
    return any(
        not char.isspace() and not unicodedata.category(char).startswith(("P", "Z"))
        for char in remainder
    )


def _config_error(message: str) -> LocalMindError:
    return LocalMindError("CONFIG_ERROR", message, "系统配置有误，请检查 cloud_advisory.config。")


def _authorization_required(message: str) -> LocalMindError:
    return LocalMindError(
        "CLOUD_AUTHORIZATION_REQUIRED", message, "该云端咨询需要你的确认后才能发送。"
    )
