"""Minimal context assembly for one model call."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.capabilities import validate_active_capabilities
from src.core.interfaces import MemoryBackend, ToolBackend
from src.core.retention import KEEP_FULL, KEEP_SUMMARY, classify_retention
from src.core.schemas import (
    InputEvent,
    MemoryChunk,
    MinimalContext,
    ProjectState,
    RetrievalStats,
    TopicDecision,
)
from src.core.tool_validation import validate_tool_catalog

_SYSTEM_PROMPT = (
    "You are LocalMind, a local-first personal office agent. "
    "Use only the provided minimal context and return structured intent candidates."
)
_MEMORY_TOP_K = 3
_SESSION_SUMMARY_PREFIX = "[本地模型推断，未经用户确认] 会话摘要: "
_VERBATIM_MEMORY_PREFIX = "[本地历史片段（逐字）] "


@dataclass
class ContextAssembler:
    """Assemble only the context needed for the next intent-resolution call."""

    memory: MemoryBackend
    tools: ToolBackend
    max_context_bytes: int
    capabilities_enabled: bool
    last_retrieval_stats: RetrievalStats | None = None

    def assemble(
        self,
        input_event: InputEvent,
        topic: TopicDecision,
        project_state: ProjectState | None,
    ) -> MinimalContext:
        """Build MinimalContext from normalized input and memory summaries."""

        session_summary = self.memory.get_summary("conversation", input_event.session_id)
        relevant_memories = self._retrieve_relevant_memories(
            input_event.text,
            topic,
            input_event.session_id,
        )
        tool_defs = validate_tool_catalog(self.tools.list_tools())
        capabilities = (
            validate_active_capabilities(tuple(self.tools.list_capabilities()), tool_defs)
            if self.capabilities_enabled else None
        )
        history = _trim_history(
            [*_format_session_summary(session_summary), *_format_memory_chunks(relevant_memories)],
            self.max_context_bytes,
        )

        return MinimalContext(
            system_prompt=_SYSTEM_PROMPT,
            current_input=input_event.text,
            relevant_history=history,
            project_state=_project_state_dict(project_state),
            tool_defs=tool_defs,
            capabilities=capabilities,
            project_id=topic.project_id,
        )

    def _retrieve_relevant_memories(
        self,
        query: str,
        topic: TopicDecision,
        session_id: str,
    ) -> list[MemoryChunk]:
        hints = (topic.referenced_topic,) if topic.relation == "shift_with_reference" and topic.referenced_topic else ()
        result = self.memory.retrieve(
            query,
            top_k=_MEMORY_TOP_K,
            max_bytes=self.max_context_bytes,
            topic_hints=hints,
            project_id=topic.project_id,
        )
        if result.is_err:
            self.last_retrieval_stats = RetrievalStats(0, False, False, True)
            return []
        memories = result.value or []
        vector_enabled = any(chunk.vector_score is not None for chunk in memories)
        self.last_retrieval_stats = RetrievalStats(
            hits=len(memories),
            kw_enabled=True,
            vec_enabled=vector_enabled,
            degraded=False,
        )
        if hints:
            filtered = [
                chunk for chunk in memories if chunk.metadata.get("session_id") == session_id
            ]
            filtered_vector_enabled = any(
                chunk.vector_score is not None for chunk in filtered
            )
            self.last_retrieval_stats = RetrievalStats(
                hits=len(filtered),
                kw_enabled=True,
                vec_enabled=filtered_vector_enabled,
                degraded=False,
            )
            return filtered
        return memories


def _project_state_dict(state: ProjectState | None) -> dict | None:
    if state is None:
        return None
    return {
        "project_id": state.project_id,
        "summary": state.summary,
        "summary_is_manual": "summary" in state.manual_overrides,
    }


def _trim_history(history: list[str], max_bytes: int) -> list[str]:
    kept = list(history)
    while kept and sum(len(item.encode("utf-8")) for item in kept) > max_bytes:
        longest_index = max(range(len(kept)), key=lambda index: len(kept[index].encode("utf-8")))
        kept.pop(longest_index)
    return kept


def _format_session_summary(summary: dict | None) -> list[str]:
    text = _summary_text(summary)
    if not text:
        return []
    return [f"{_SESSION_SUMMARY_PREFIX}{text}"]


def _format_memory_chunks(chunks: list[MemoryChunk]) -> list[str]:
    history: list[str] = []
    for chunk in chunks:
        retention = classify_retention(chunk.similarity_score)
        if retention == KEEP_FULL:
            history.append(f"{_VERBATIM_MEMORY_PREFIX}{chunk.text}")
        elif retention == KEEP_SUMMARY:
            history.append(f"{_VERBATIM_MEMORY_PREFIX}{chunk.text[:200]}")
    return history


def _summary_text(summary: dict | None) -> str:
    if not summary:
        return ""
    preferred = summary.get("summary")
    if isinstance(preferred, str):
        return preferred.strip()
    return _compact_dict(summary)


def _compact_dict(value: dict[str, Any]) -> str:
    parts = [f"{key}: {item}" for key, item in value.items() if str(item).strip()]
    return "; ".join(parts)
