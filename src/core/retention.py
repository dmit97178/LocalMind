"""Context-retention policy for retrieved memory chunks."""

from __future__ import annotations

KEEP_FULL = "keep_full"
KEEP_SUMMARY = "keep_summary"
DISCARD = "discard"
HIGH_THRESHOLD = 0.60
LOW_THRESHOLD = 0.35


def classify_retention(
    similarity_score: float,
    *,
    high_threshold: float = HIGH_THRESHOLD,
    low_threshold: float = LOW_THRESHOLD,
) -> str:
    """Classify a retrieved chunk according to its P5 normalized retrieval score."""

    if similarity_score >= high_threshold:
        return KEEP_FULL
    if similarity_score >= low_threshold:
        return KEEP_SUMMARY
    return DISCARD
