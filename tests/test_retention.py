"""P5 retention thresholds use the normalized retrieval score."""

from src.core.retention import DISCARD, KEEP_FULL, KEEP_SUMMARY, classify_retention


def test_classify_retention_uses_p5_normalized_thresholds() -> None:
    assert classify_retention(0.60) == KEEP_FULL
    assert classify_retention(0.35) == KEEP_SUMMARY
    assert classify_retention(0.34) == DISCARD
