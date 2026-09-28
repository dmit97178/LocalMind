"""Shared keyword retrieval and topic-relation helpers."""

from __future__ import annotations

from collections.abc import Mapping

from src.core.schemas import MemoryChunk
from src.core.text_utils import tokenize

_STRONG_REFERENCE_TERMS = {
    "previous",
    "above",
    "刚才",
    "继续",
    "上面",
    "之前",
}
_WEAK_REFERENCE_TERMS = {"it", "that", "this", "那个", "这个"}
_NEW_TOPIC_TERMS = {
    "换个话题",
    "新话题",
    "另外",
    "另一个",
    "next topic",
}
def keyword_score(query_terms: set[str], text: str, metadata: dict) -> float:
    """Return the number of query terms found in text or metadata."""

    text_terms = tokenize(text)
    metadata_terms = tokenize(" ".join(str(value) for value in metadata.values()))
    return float(len(query_terms.intersection(text_terms | metadata_terms)))


def fuse_retrieval(
    keyword_scores: Mapping[str, float],
    vector_scores: Mapping[str, float],
    chunks: Mapping[str, MemoryChunk],
    *,
    vector_available: bool,
    keyword_weight: float,
    vector_weight: float,
    project_id: str | None,
    same_project_boost: float,
) -> list[MemoryChunk]:
    """Merge bounded keyword and vector recalls into deterministic chunks."""

    chunk_ids = set(keyword_scores) | set(vector_scores)
    results: list[MemoryChunk] = []
    for chunk_id in chunk_ids:
        chunk = chunks.get(chunk_id)
        if chunk is None:
            continue
        keyword = keyword_scores.get(chunk_id)
        vector = vector_scores.get(chunk_id)
        if vector_available:
            score = keyword_weight * (keyword or 0.0) + vector_weight * max(vector or 0.0, 0.0)
        else:
            score = keyword or 0.0
        if project_id is not None and chunk.metadata.get("project_id") == project_id:
            score = min(score + same_project_boost, 1.0)
        source = "both" if keyword is not None and vector is not None else "keyword" if keyword is not None else "vector"
        results.append(
            MemoryChunk(
                id=chunk.id,
                text=chunk.text,
                metadata=dict(chunk.metadata),
                similarity_score=score,
                vector_score=vector,
                match_source=source,
            )
        )
    return _sort_by_score_timestamp_id(results)


def _sort_by_score_timestamp_id(chunks: list[MemoryChunk]) -> list[MemoryChunk]:
    ordered = sorted(chunks, key=lambda chunk: chunk.id)
    ordered.sort(key=lambda chunk: str(chunk.metadata.get("timestamp", "")), reverse=True)
    ordered.sort(key=lambda chunk: chunk.similarity_score, reverse=True)
    return ordered


def detect_topic_relation(current_input: str, current_topic: str) -> str:
    """Classify the relationship between an input and the current topic."""

    input_lower = current_input.lower()
    if any(term in input_lower for term in _NEW_TOPIC_TERMS):
        return "new_topic"

    input_terms = tokenize(current_input)
    topic_terms = tokenize(current_topic)
    if input_terms and topic_terms and input_terms.intersection(topic_terms):
        return "same_topic"

    if any(term in input_lower for term in _STRONG_REFERENCE_TERMS):
        if topic_terms:
            return "shift_with_reference"
        return "ambiguous"

    if any(term in input_lower for term in _WEAK_REFERENCE_TERMS):
        return "ambiguous"

    return "ambiguous"
