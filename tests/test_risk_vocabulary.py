"""Closed risk vocabulary normalization."""

from __future__ import annotations

import inspect

import pytest

from src.core.risk_vocabulary import RISK_LEVELS, normalize_risk_draft


@pytest.mark.parametrize(
    ("raw", "expected_risk", "expected_resolution"),
    [
        ("normal", "normal", "declared"),
        ("Sensitive", "sensitive", "declared"),
        ("\tDANGEROUS\n", "dangerous", "declared"),
        ("low", "normal", "mapped_legacy"),
        (" LOW ", "normal", "mapped_legacy"),
        ("medium", "sensitive", "mapped_legacy"),
        (" HIGH ", "sensitive", "mapped_legacy"),
        ("moderate", "sensitive", "unrecognized"),
        ("critical", "sensitive", "unrecognized"),
        ("not normal", "sensitive", "unrecognized"),
        ("很高", "sensitive", "unrecognized"),
        (None, "sensitive", "absent"),
        ("", "sensitive", "absent"),
        ("   ", "sensitive", "absent"),
        (42, "sensitive", "absent"),
        (["normal"], "sensitive", "absent"),
    ],
)
def test_normalize_risk_draft_is_total_and_closed(
    raw: object,
    expected_risk: str,
    expected_resolution: str,
) -> None:
    risk, resolution = normalize_risk_draft(raw)

    assert (risk, resolution) == (expected_risk, expected_resolution)
    assert risk in RISK_LEVELS
    assert resolution in {"declared", "mapped_legacy", "absent", "unrecognized"}


def test_only_an_explicit_dangerous_token_normalizes_to_dangerous() -> None:
    samples: tuple[object, ...] = (
        "dangerous",
        " DANGEROUS ",
        "high",
        "critical",
        None,
        42,
    )

    normalized = [normalize_risk_draft(value) for value in samples]

    assert normalized[:2] == [("dangerous", "declared")] * 2
    assert all(risk != "dangerous" for risk, _ in normalized[2:])


@pytest.mark.parametrize(
    ("causal_risk", "payload_sensitive", "execution_sensitive", "expected"),
    [
        ("normal", False, False, "normal"),
        ("normal", True, False, "sensitive"),
        ("normal", False, True, "sensitive"),
        ("sensitive", False, False, "sensitive"),
        ("dangerous", False, False, "dangerous"),
        ("unexpected", False, False, "sensitive"),
    ],
)
def test_effective_authorization_risk_only_raises_the_model_lower_bound(
    causal_risk: str,
    payload_sensitive: bool,
    execution_sensitive: bool,
    expected: str,
) -> None:
    from src.core.risk_vocabulary import effective_authorization_risk

    assert effective_authorization_risk(
        causal_risk,
        payload_candidates_sensitive=payload_sensitive,
        sensitive_execution_chain=execution_sensitive,
    ) == expected


def test_effective_authorization_risk_defaults_fail_closed_and_has_only_two_signals() -> None:
    from src.core.risk_vocabulary import effective_authorization_risk

    assert effective_authorization_risk("normal") == "sensitive"
    parameters = inspect.signature(effective_authorization_risk).parameters
    assert set(parameters) == {
        "causal_risk",
        "payload_candidates_sensitive",
        "sensitive_execution_chain",
    }
    assert not any(
        forbidden in name
        for name in parameters
        for forbidden in ("high_impact", "preflight", "approval_profile")
    )
