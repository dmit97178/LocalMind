"""Tests for ContextAssembler."""

from dataclasses import dataclass

from src.core.interfaces import ToolBackend
from src.core.schemas import (
    InputEvent,
    LocalMindError,
    MemoryChunk,
    MinimalContext,
    ProjectState,
    Result,
    ToolCapability,
    ToolDef,
    TopicDecision,
)
from src.memory.in_memory_backend import InMemoryMemoryBackend


@dataclass
class ListingOnlyToolBackend(ToolBackend):
    tools: list[ToolDef]

    def list_tools(self) -> list[ToolDef]:
        return list(self.tools)

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        return Result.ok({"tool_name": tool_name, "params": params})


def test_enabled_empty_capability_directory_is_distinct_from_disabled() -> None:
    from src.core.context_assembler import ContextAssembler

    backend = ListingOnlyToolBackend(tools=[])
    event = InputEvent(text="hello", session_id="s", timestamp="now")
    topic = _topic("s", "hello", None)
    enabled = ContextAssembler(InMemoryMemoryBackend(), backend, 4096, True)
    disabled = ContextAssembler(InMemoryMemoryBackend(), backend, 4096, False)

    assert enabled.assemble(event, topic, None).capabilities == ()
    assert disabled.assemble(event, topic, None).capabilities is None


def test_assembler_rejects_runtime_capability_catalog_without_active_coverage() -> None:
    import pytest

    from src.core.context_assembler import ContextAssembler

    class MissingCoverage(ListingOnlyToolBackend):
        def list_capabilities(self) -> list[ToolCapability]:
            return [ToolCapability("system.time", "Get time", ("system.get_time",))]

    backend = MissingCoverage(tools=[
        ToolDef("system.get_time", "Get time", {"type": "object", "properties": {}, "required": []}),
        ToolDef("file.read", "Read file", {"type": "object", "properties": {}, "required": []}),
    ])
    assembler = ContextAssembler(InMemoryMemoryBackend(), backend, 4096, True)

    with pytest.raises(LocalMindError) as error:
        assembler.assemble(InputEvent("read", "s", "now"), _topic("s", "read", None), None)
    assert error.value.details["reason"] == "capability_coverage_missing"


def test_assemble_builds_minimal_context_from_input_event() -> None:
    from src.core.context_assembler import ContextAssembler

    memory = InMemoryMemoryBackend()
    memory.save_summary(
        "conversation",
        "sess_001",
        {"summary": "User is checking the local model port."},
    )
    memory.store_episode(
        "Ollama usually listens on port 11434.",
        {"topic": "ollama port", "session_id": "sess_001"},
    )
    tools = ListingOnlyToolBackend(
        tools=[
            ToolDef(
                name="system.check_port",
                description="Check whether a local port is listening.",
                parameters={
                    "type": "object",
                    "properties": {"port": {"type": "integer"}},
                    "required": ["port"],
                },
            )
        ]
    )
    assembler = ContextAssembler(memory=memory, tools=tools, max_context_bytes=4096, capabilities_enabled=False)

    context = assembler.assemble(
        InputEvent(
            text="check ollama port",
            session_id="sess_001",
            project_id="proj_localmind",
            timestamp="2026-07-08T10:30:00",
        ),
        topic=_topic("sess_001", "ollama-port", "proj_localmind"),
        project_state=_project("proj_localmind"),
    )

    assert isinstance(context, MinimalContext)
    assert "LocalMind" in context.system_prompt
    assert context.current_input == "check ollama port"
    assert context.project_state == {
        "project_id": "proj_localmind",
        "summary": "Project summary",
        "summary_is_manual": False,
    }
    assert context.project_id == "proj_localmind"
    assert tuple(tool.name for tool in context.tool_defs) == ("system.check_port",)
    assert context.relevant_history == [
        "[本地模型推断，未经用户确认] 会话摘要: User is checking the local model port.",
        "[本地历史片段（逐字）] Ollama usually listens on port 11434.",
    ]
    assert assembler.last_retrieval_stats is not None
    assert assembler.last_retrieval_stats.hits == 1
    assert assembler.last_retrieval_stats.kw_enabled is True
    assert assembler.last_retrieval_stats.vec_enabled is False
    assert assembler.last_retrieval_stats.degraded is False


def test_assemble_omits_project_state_when_project_id_is_missing() -> None:
    from src.core.context_assembler import ContextAssembler

    memory = InMemoryMemoryBackend()
    memory.save_summary(
        "conversation",
        "sess_001",
        {"summary": "User is discussing local memory."},
    )
    assembler = ContextAssembler(memory=memory, tools=ListingOnlyToolBackend(tools=[]), max_context_bytes=4096, capabilities_enabled=False)

    context = assembler.assemble(
        InputEvent(
            text="summarize memory backend",
            session_id="sess_001",
            timestamp="2026-07-08T10:31:00",
        ),
        topic=_topic("sess_001", "memory", None),
        project_state=None,
    )

    assert context.current_input == "summarize memory backend"
    assert context.project_state is None
    assert context.relevant_history == [
        "[本地模型推断，未经用户确认] 会话摘要: User is discussing local memory.",
    ]


def test_assemble_uses_empty_context_when_memory_has_no_matches() -> None:
    from src.core.context_assembler import ContextAssembler

    assembler = ContextAssembler(memory=InMemoryMemoryBackend(), tools=ListingOnlyToolBackend(tools=[]), max_context_bytes=4096, capabilities_enabled=False)

    context = assembler.assemble(
        InputEvent(
            text="brand new task",
            session_id="sess_new",
            project_id="proj_missing",
            timestamp="2026-07-08T10:32:00",
        ),
        topic=_topic("sess_new", "new-task", "proj_missing"),
        project_state=None,
    )

    assert context.current_input == "brand new task"
    assert context.relevant_history == []
    assert context.project_state is None
    assert context.tool_defs == ()


def test_assemble_applies_differentiated_memory_retention() -> None:
    from src.core.context_assembler import ContextAssembler

    memory = InMemoryMemoryBackend()
    query = "alpha beta gamma delta epsilon"
    full_text = "alpha beta gamma delta epsilon full context"
    summary_text = "alpha beta " + ("x" * 190) + "TAIL_MUST_NOT_APPEAR" + ("y" * 280)
    discard_text = "alpha weak context"
    metadata = {"topic": "notes", "session_id": "sess_001"}
    memory.store_episode(full_text, metadata)
    memory.store_episode(summary_text, metadata)
    memory.store_episode(discard_text, metadata)
    assembler = ContextAssembler(memory=memory, tools=ListingOnlyToolBackend(tools=[]), max_context_bytes=4096, capabilities_enabled=False)

    context = assembler.assemble(
        InputEvent(text=query, session_id="sess_001", timestamp="2026-07-20T10:00:00"),
        topic=_topic("sess_001", "notes", None),
        project_state=None,
    )

    history = "\n".join(context.relevant_history)
    assert f"[本地历史片段（逐字）] {full_text}" in history
    assert f"[本地历史片段（逐字）] {summary_text}" in history
    assert discard_text not in history


def test_assemble_summarizes_mid_score_project_memory() -> None:
    from src.core.context_assembler import ContextAssembler

    memory = InMemoryMemoryBackend()
    summary_text = "alpha " + ("x" * 190) + "TAIL_MUST_NOT_APPEAR" + ("y" * 280)
    memory.store_episode(
        summary_text,
        {"topic": "notes", "session_id": "sess_001", "project_id": "proj_x"},
    )
    assembler = ContextAssembler(memory=memory, tools=ListingOnlyToolBackend(tools=[]), max_context_bytes=4096, capabilities_enabled=False)

    context = assembler.assemble(
        InputEvent(text="alpha beta gamma", session_id="sess_001", timestamp="now"),
        topic=_topic("sess_001", "notes", "proj_x"),
        project_state=_project("proj_x"),
    )

    history = "\n".join(context.relevant_history)
    assert f"[本地历史片段（逐字）] {summary_text[:200]}" in history
    assert "TAIL_MUST_NOT_APPEAR" not in history


def test_topic_hint_stats_reflect_chunks_that_survive_session_filtering() -> None:
    from src.core.context_assembler import ContextAssembler

    class HintMemory(InMemoryMemoryBackend):
        def retrieve(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return Result.ok(
                [
                    MemoryChunk(
                        id="vector-other",
                        text="other-session vector result",
                        metadata={"session_id": "other"},
                        similarity_score=1.0,
                        vector_score=0.9,
                    ),
                    MemoryChunk(
                        id="keyword-current",
                        text="current-session keyword result",
                        metadata={"session_id": "sess_001"},
                        similarity_score=0.8,
                    ),
                ]
            )

    assembler = ContextAssembler(
        memory=HintMemory(), tools=ListingOnlyToolBackend(tools=[]), max_context_bytes=4096,
        capabilities_enabled=False,
    )

    assembler.assemble(
        InputEvent(text="notes", session_id="sess_001", timestamp="now"),
        topic=TopicDecision("sess_001", "shift_with_reference", "notes", "older", None, False),
        project_state=None,
    )

    assert assembler.last_retrieval_stats is not None
    assert assembler.last_retrieval_stats.hits == 1
    assert assembler.last_retrieval_stats.vec_enabled is False
    assert assembler.last_retrieval_stats.degraded is False


def test_assemble_marks_only_explicit_retrieval_failure_as_degraded() -> None:
    from src.core.context_assembler import ContextAssembler

    class FailedMemory(InMemoryMemoryBackend):
        def retrieve(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            return Result.err(
                LocalMindError(
                    "MEMORY_ERROR",
                    "retrieval unavailable",
                    "记忆检索暂不可用。",
                )
            )

    assembler = ContextAssembler(
        memory=FailedMemory(), tools=ListingOnlyToolBackend(tools=[]), max_context_bytes=4096,
        capabilities_enabled=False,
    )

    assembler.assemble(
        InputEvent(text="notes", session_id="sess", timestamp="now"),
        topic=_topic("sess", "notes", None),
        project_state=None,
    )

    assert assembler.last_retrieval_stats is not None
    assert assembler.last_retrieval_stats.degraded is True
    assert assembler.last_retrieval_stats.kw_enabled is False


def _topic(session_id: str, label: str, project_id: str | None) -> TopicDecision:
    return TopicDecision(session_id, "same_topic", label, None, project_id, False)


def _project(project_id: str) -> ProjectState:
    return ProjectState(project_id, "Project", "", (), "active", "Project summary", (), frozenset(), "now", "now")
