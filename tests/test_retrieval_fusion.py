"""P5 deterministic hybrid retrieval fusion."""

import pytest

from src.core.schemas import MemoryChunk
from src.memory.retrieval import fuse_retrieval


def test_fuse_retrieval_merges_keyword_and_vector_hits() -> None:
    chunks = {
        "both": _chunk("both", "2026-09-09T01:00:00+00:00", "alpha"),
        "vector": _chunk("vector", "2026-09-09T02:00:00+00:00", "alpha"),
    }

    result = fuse_retrieval(
        {"both": 2 / 3},
        {"both": 0.5, "vector": 0.9},
        chunks,
        vector_available=True,
        keyword_weight=0.6,
        vector_weight=0.4,
        project_id="alpha",
        same_project_boost=0.1,
    )

    assert [(chunk.id, chunk.match_source) for chunk in result] == [
        ("both", "both"),
        ("vector", "vector"),
    ]
    assert result[0].similarity_score == 0.7
    assert result[0].vector_score == 0.5
    assert result[1].similarity_score == pytest.approx(0.46)


def test_fuse_retrieval_uses_keyword_score_unchanged_when_vector_is_unavailable() -> None:
    chunk = _chunk("keyword", "2026-09-09T01:00:00+00:00", None)

    result = fuse_retrieval(
        {"keyword": 2 / 3},
        {},
        {"keyword": chunk},
        vector_available=False,
        keyword_weight=0.6,
        vector_weight=0.4,
        project_id=None,
        same_project_boost=0.1,
    )

    assert result == [MemoryChunk("keyword", "text", chunk.metadata, 2 / 3)]


def test_fuse_retrieval_uses_timestamp_then_id_for_ties() -> None:
    older = _chunk("a", "2026-09-09T01:00:00+00:00", None)
    newer = _chunk("b", "2026-09-09T02:00:00+00:00", None)

    result = fuse_retrieval(
        {"a": 0.5, "b": 0.5},
        {},
        {"a": older, "b": newer},
        vector_available=False,
        keyword_weight=0.6,
        vector_weight=0.4,
        project_id=None,
        same_project_boost=0.1,
    )

    assert [chunk.id for chunk in result] == ["b", "a"]


def _chunk(chunk_id: str, timestamp: str, project_id: str | None) -> MemoryChunk:
    return MemoryChunk(chunk_id, "text", {"timestamp": timestamp, "project_id": project_id})
