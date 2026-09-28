"""Canonical risk vocabulary for model-produced intent candidates."""

from __future__ import annotations

RISK_LEVELS = ("normal", "sensitive", "dangerous")
APPROVAL_PROFILES = ("standard", "high_impact")
LEGACY_RISK_MAP = {
    "low": "normal",
    "medium": "sensitive",
    "high": "sensitive",
}
_RISK_ORDER = {"normal": 0, "sensitive": 1, "dangerous": 2}


def normalize_risk_draft(raw: object) -> tuple[str, str]:
    """Return a closed risk value and its normalization provenance."""

    if not isinstance(raw, str) or not raw.strip():
        return "sensitive", "absent"
    normalized = raw.strip().lower()
    if normalized in RISK_LEVELS:
        return normalized, "declared"
    if normalized in LEGACY_RISK_MAP:
        return LEGACY_RISK_MAP[normalized], "mapped_legacy"
    return "sensitive", "unrecognized"


def effective_authorization_risk(
    causal_risk: str,
    *,
    payload_candidates_sensitive: bool = True,
    sensitive_execution_chain: bool = True,
) -> str:
    """Raise a model risk lower bound using deterministic authorization facts."""

    normalized, _ = normalize_risk_draft(causal_risk)
    deterministic = (
        "sensitive"
        if payload_candidates_sensitive or sensitive_execution_chain
        else "normal"
    )
    effective_rank = max(_RISK_ORDER[normalized], _RISK_ORDER[deterministic])
    return next(risk for risk, rank in _RISK_ORDER.items() if rank == effective_rank)


def read_approval_profile(raw: object) -> str:
    """Normalize an approval profile, failing closed to the most restricted value."""

    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in APPROVAL_PROFILES:
            return normalized
    return "high_impact"
