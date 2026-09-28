"""P0 in-memory implementation of MemoryBackend."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import sqrt

from src.core.interfaces import EmbeddingBackend, MemoryBackend
from src.core.memory_hygiene import sanitize_for_memory, sanitize_memory_value
from src.core.schemas import LocalMindError, MemoryChunk, Result
from src.memory.retrieval import detect_topic_relation, fuse_retrieval, keyword_score, tokenize

_REQUIRED_EPISODE_METADATA = ("topic", "session_id")


@dataclass
class InMemoryMemoryBackend(MemoryBackend):
    """Volatile memory backend used for P0 core-loop development."""

    _chunks: list[MemoryChunk] = field(default_factory=list)
    summaries: dict[tuple[str, str], dict] = field(default_factory=dict)
    project_records: dict[str, dict] = field(default_factory=dict)
    forbidden_paths: tuple[str, ...] = ()
    embedding: EmbeddingBackend | None = None
    _vectors: dict[str, list[float]] = field(default_factory=dict)
    keyword_weight: float = 0.6
    vector_weight: float = 0.4
    same_project_boost: float = 0.1
    _next_id: int = 1

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        max_bytes: int | None = None,
        topic_hints: Sequence[str] = (),
        project_id: str | None = None,
    ) -> Result[list[MemoryChunk]]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            return Result.err(
                LocalMindError(
                    code="MEMORY_ERROR",
                    message=f"top_k must be >= 1, got {top_k}",
                    user_message="记忆检索参数无效。",
                    recoverable=True,
                    details={"top_k": top_k},
                )
            )

        query_terms = tokenize(query)
        if not query_terms:
            return Result.ok([])

        if max_bytes is not None and (
            not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1
        ):
            return Result.err(_memory_error("max_bytes must be a positive integer", {"max_bytes": max_bytes}))

        hint_terms = tokenize(" ".join(topic_hints))
        scoring_terms = query_terms | hint_terms
        chunks: dict[str, MemoryChunk] = {}
        keyword_scores: dict[str, float] = {}
        for chunk in self._chunks:
            if hint_terms:
                if not hint_terms.intersection(tokenize(str(chunk.metadata.get("topic", "")))):
                    continue
            elif chunk.metadata.get("project_id") not in {project_id, None}:
                continue
            score = keyword_score(scoring_terms, chunk.text, chunk.metadata)
            if score > 0:
                chunks[chunk.id] = chunk
                keyword_scores[chunk.id] = min(score / 3.0, 1.0)
            else:
                chunks[chunk.id] = chunk

        vector_scores, vector_available = self._vector_scores(query, set(chunks))

        fused = fuse_retrieval(
            keyword_scores,
            vector_scores,
            chunks,
            vector_available=vector_available,
            keyword_weight=self.keyword_weight,
            vector_weight=self.vector_weight,
            project_id=project_id,
            same_project_boost=self.same_project_boost,
        )
        results: list[MemoryChunk] = []
        used_bytes = 0
        for chunk in fused[:top_k]:
            text_bytes = len(chunk.text.encode("utf-8"))
            if max_bytes is not None and used_bytes + text_bytes > max_bytes:
                break
            used_bytes += text_bytes
            results.append(chunk)
        return Result.ok(results)

    def store_episode(self, content: str, metadata: dict) -> str:
        if not content.strip():
            raise LocalMindError(
                code="MEMORY_ERROR",
                message="Cannot store a blank memory episode",
                user_message="记忆内容为空，无法存储。",
                recoverable=True,
                details={"metadata": dict(metadata)},
            )

        missing_metadata = [
            key for key in _REQUIRED_EPISODE_METADATA if not str(metadata.get(key, "")).strip()
        ]
        if missing_metadata:
            raise LocalMindError(
                code="MEMORY_ERROR",
                message=f"Memory episode metadata missing required keys: {missing_metadata}",
                user_message="记忆元数据不完整，无法存储。",
                recoverable=True,
                details={"missing": missing_metadata, "metadata": dict(metadata)},
            )

        chunk_id = f"mem_{self._next_id:06d}"
        self._next_id += 1
        sanitized = sanitize_for_memory(content, forbidden_paths=self.forbidden_paths)
        self._chunks.append(MemoryChunk(chunk_id, sanitized, dict(metadata), 0.0))
        self._store_vector(chunk_id, sanitized)
        return chunk_id

    def get_summary(self, scope: str, scope_id: str) -> dict | None:
        summary = self.summaries.get((scope, scope_id))
        if summary is None:
            return None
        return dict(summary)

    def save_summary(self, scope: str, scope_id: str, summary: dict) -> None:
        if (
            not isinstance(scope, str)
            or not scope.strip()
            or not isinstance(scope_id, str)
            or not scope_id.strip()
            or not isinstance(summary, dict)
            or not summary
        ):
            raise LocalMindError(
                code="MEMORY_ERROR",
                message="Cannot save summary with blank scope, blank scope_id, or empty summary",
                user_message="摘要参数不完整，无法保存。",
                recoverable=True,
                details={
                    "scope": scope,
                    "scope_id": scope_id,
                    "summary": dict(summary) if isinstance(summary, dict) else summary,
                },
            )

        self.summaries[(scope, scope_id)] = sanitize_memory_value(
            summary, forbidden_paths=self.forbidden_paths
        )

    def detect_topic_relation(self, current_input: str, current_topic: str) -> str:
        return detect_topic_relation(current_input, current_topic)

    def get_project_record(self, project_id: str) -> dict | None:
        record = self.project_records.get(project_id)
        return None if record is None else dict(record)

    def put_project_record(self, record: dict) -> None:
        if not isinstance(record, dict) or not str(record.get("project_id", "")).strip():
            raise LocalMindError(
                code="MEMORY_ERROR",
                message="Project record requires a project_id",
                user_message="项目记忆数据无效，无法保存。",
                recoverable=True,
            )
        self.project_records[str(record["project_id"])] = sanitize_memory_value(
            record, forbidden_paths=self.forbidden_paths
        )

    def list_project_ids(self) -> list[str]:
        return sorted(self.project_records)

    def _store_vector(self, chunk_id: str, text: str) -> None:
        if self.embedding is None or not self.embedding.health_check() or self.embedding.dimensions() < 1:
            return
        result = self.embedding.embed_documents([text])
        if result.is_ok and result.value:
            self._vectors[chunk_id] = result.value[0]

    def _vector_scores(self, query: str, allowed_ids: set[str]) -> tuple[dict[str, float], bool]:
        if self.embedding is None or not self.embedding.health_check() or self.embedding.dimensions() < 1:
            return {}, False
        result = self.embedding.embed_query(query)
        if result.is_err or result.value is None:
            return {}, False
        scores = {
            chunk_id: _cosine(result.value, vector)
            for chunk_id, vector in self._vectors.items()
            if chunk_id in allowed_ids
        }
        return scores, True


def _memory_error(message: str, details: dict) -> LocalMindError:
    return LocalMindError(
        code="MEMORY_ERROR",
        message=message,
        user_message="记忆检索参数无效。",
        recoverable=True,
        details=details,
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(left_item * right_item for left_item, right_item in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
