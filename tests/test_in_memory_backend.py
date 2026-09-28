"""Tests for the P0 in-memory memory backend."""

from src.core.interfaces import EmbeddingBackend, MemoryBackend
from src.core.schemas import LocalMindError, MemoryChunk, Result
from src.memory.in_memory_backend import InMemoryMemoryBackend

ZH_CHECK_PORT = "检查 Ollama 端口 11434"
ZH_PORT_PROBLEM = "Ollama 端口还是不通"
ZH_CONTINUE_PORT_CHECK = "继续刚才那个端口检查"
ZH_NEW_TOPIC_INDEX = "换个话题，讨论数据库索引"
ZH_LOOK_AT_THIS = "帮我看看这个"


def test_in_memory_backend_implements_memory_backend() -> None:
    backend = InMemoryMemoryBackend()

    assert isinstance(backend, MemoryBackend)


def test_store_episode_returns_chunk_id_and_retrieve_matches_keywords() -> None:
    backend = InMemoryMemoryBackend()

    first_id = backend.store_episode(
        "User wants to check Ollama port 11434",
        {"topic": "ollama", "session_id": "session-1"},
    )
    second_id = backend.store_episode(
        "Project uses SQLite for local memory",
        {"topic": "memory", "session_id": "session-1"},
    )

    result = backend.retrieve("check ollama port", top_k=1)

    assert result.is_ok is True
    assert first_id != second_id
    assert result.value == [
        MemoryChunk(
            id=first_id,
            text="User wants to check Ollama port 11434",
            metadata={"topic": "ollama", "session_id": "session-1"},
            similarity_score=1.0,
        )
    ]


def test_store_episode_rejects_blank_content() -> None:
    backend = InMemoryMemoryBackend()

    for content in ["", "   ", "\t\n"]:
        try:
            backend.store_episode(content, {"topic": "notes", "session_id": "session-1"})
        except LocalMindError as exc:
            assert exc.code == "MEMORY_ERROR"
            assert exc.recoverable is True
        else:
            raise AssertionError("store_episode should reject blank content")


def test_store_episode_rejects_missing_required_metadata() -> None:
    backend = InMemoryMemoryBackend()

    for metadata in [{}, {"topic": "notes"}, {"session_id": "session-1"}]:
        try:
            backend.store_episode("content", metadata)
        except LocalMindError as exc:
            assert exc.code == "MEMORY_ERROR"
            assert exc.recoverable is True
        else:
            raise AssertionError("store_episode should reject incomplete metadata")


def test_retrieve_matches_chinese_subterms_without_external_segmenter() -> None:
    backend = InMemoryMemoryBackend()
    first_id = backend.store_episode(
        ZH_CHECK_PORT,
        {"topic": "端口检查", "session_id": "session-1"},
    )
    backend.store_episode(
        "项目使用 SQLite 存储记忆",
        {"topic": "记忆", "session_id": "session-1"},
    )

    result = backend.retrieve("端口检查", top_k=1)

    assert result.is_ok is True
    assert result.value is not None
    assert result.value[0].id == first_id
    assert result.value[0].similarity_score > 0


def test_retrieve_returns_empty_ok_result_when_nothing_matches() -> None:
    backend = InMemoryMemoryBackend()
    backend.store_episode("Only unrelated project notes", {"topic": "notes", "session_id": "s1"})

    result = backend.retrieve("ollama port", top_k=5)

    assert result.is_ok is True
    assert result.value == []


def test_retrieve_scopes_normal_queries_to_current_project_and_unassigned_pool() -> None:
    backend = InMemoryMemoryBackend()
    backend.store_episode("alpha launch plan", {"topic": "launch", "session_id": "s1", "project_id": "alpha"})
    backend.store_episode("beta launch plan", {"topic": "launch", "session_id": "s2", "project_id": "beta"})
    backend.store_episode("unassigned launch note", {"topic": "launch", "session_id": "s3"})

    result = backend.retrieve("launch", project_id="alpha")

    assert result.is_ok is True
    assert result.value is not None
    assert {chunk.metadata.get("project_id") for chunk in result.value} == {"alpha", None}


def test_store_episode_sanitizes_content_before_retaining_it() -> None:
    backend = InMemoryMemoryBackend()
    chunk_id = backend.store_episode(
        "api_key=sk-live-secret ~/.ssh/id_rsa", {"topic": "security", "session_id": "s1"}
    )

    result = backend.retrieve("security", project_id=None)

    assert result.is_ok is True
    assert result.value is not None
    assert result.value[0].id == chunk_id
    assert "sk-live-secret" not in result.value[0].text
    assert "~/.ssh/id_rsa" not in result.value[0].text

    topic_result = backend.retrieve("security", project_id=None)

    assert topic_result.value is not None
    assert topic_result.value[0].id == chunk_id


def test_in_memory_backend_sanitizes_structured_writes() -> None:
    backend = InMemoryMemoryBackend()

    backend.save_summary("conversation", "s1", {"summary": "~/.ssh/id_rsa"})
    backend.put_project_record({"project_id": "alpha", "summary": "token=sk-live-secret"})

    assert backend.get_summary("conversation", "s1") == {"summary": "[已脱敏:path]"}
    assert backend.get_project_record("alpha") == {
        "project_id": "alpha",
        "summary": "token=[已脱敏:secret]",
    }


class _EmbeddingStub(EmbeddingBackend):
    def embed_documents(self, texts: list[str]) -> Result[list[list[float]]]:
        return Result.ok([self._vector(text) for text in texts])

    def embed_query(self, text: str) -> Result[list[float]]:
        return Result.ok(self._vector(text))

    def dimensions(self) -> int:
        return 2

    def model_id(self) -> str:
        return "test-embed"

    def health_check(self) -> bool:
        return True

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [1.0, 0.0] if "database" in text or "architecture" in text else [0.0, 1.0]


def test_in_memory_backend_retrieves_semantic_vector_matches() -> None:
    backend = InMemoryMemoryBackend(embedding=_EmbeddingStub())
    backend.store_episode("database schema migration", {"topic": "data", "session_id": "s1"})

    result = backend.retrieve("architecture design")

    assert result.value is not None
    assert result.value[0].match_source == "vector"
    assert result.value[0].vector_score == 1.0


def test_retrieve_returns_memory_error_for_invalid_top_k() -> None:
    backend = InMemoryMemoryBackend()

    result = backend.retrieve("anything", top_k=0)

    assert result.is_err is True
    assert result.error is not None
    assert result.error.code == "MEMORY_ERROR"
    assert result.error.recoverable is True


def test_in_memory_backend_rejects_boolean_retrieval_limits_and_non_mapping_summary() -> None:
    backend = InMemoryMemoryBackend()

    assert backend.retrieve("anything", top_k=True).is_err is True
    assert backend.retrieve("anything", max_bytes=True).is_err is True
    try:
        backend.save_summary("conversation", "s1", ["not a mapping"])
    except LocalMindError as exc:
        assert exc.code == "MEMORY_ERROR"
    else:
        raise AssertionError("save_summary should reject a non-mapping summary")


def test_get_summary_returns_none_for_missing_summary() -> None:
    backend = InMemoryMemoryBackend()

    assert backend.get_summary("conversation", "missing") is None


def test_get_summary_returns_constructor_seeded_summary_copy() -> None:
    backend = InMemoryMemoryBackend(
        summaries={
            ("conversation", "session-1"): {
                "summary": "用户正在检查 Ollama 端口"
            }
        }
    )

    summary = backend.get_summary("conversation", "session-1")

    assert summary == {"summary": "用户正在检查 Ollama 端口"}
    assert summary is not backend.summaries[("conversation", "session-1")]


def test_save_summary_overwrites_summary_and_get_summary_returns_copy() -> None:
    backend = InMemoryMemoryBackend()

    backend.save_summary("conversation", "session-1", {"summary": "first"})
    backend.save_summary("conversation", "session-1", {"summary": "second"})
    summary = backend.get_summary("conversation", "session-1")

    assert summary == {"summary": "second"}
    assert summary is not backend.summaries[("conversation", "session-1")]


def test_save_summary_rejects_invalid_inputs() -> None:
    backend = InMemoryMemoryBackend()

    invalid_inputs = [
        ("", "session-1", {"summary": "text"}),
        ("conversation", "", {"summary": "text"}),
        ("conversation", "session-1", {}),
    ]
    for scope, scope_id, summary in invalid_inputs:
        try:
            backend.save_summary(scope, scope_id, summary)
        except LocalMindError as exc:
            assert exc.code == "MEMORY_ERROR"
            assert exc.recoverable is True
        else:
            raise AssertionError("save_summary should reject invalid inputs")


def test_detect_topic_relation_returns_allowed_values() -> None:
    backend = InMemoryMemoryBackend()

    assert backend.detect_topic_relation(ZH_CONTINUE_PORT_CHECK, "ollama port") == (
        "shift_with_reference"
    )
    assert backend.detect_topic_relation("ollama port still fails", "ollama port") == "same_topic"
    assert backend.detect_topic_relation(ZH_NEW_TOPIC_INDEX, "ollama port") == "new_topic"
    assert backend.detect_topic_relation(ZH_LOOK_AT_THIS, "ollama port") == "ambiguous"


def test_detect_topic_relation_matches_chinese_topic_subterms() -> None:
    backend = InMemoryMemoryBackend()

    assert backend.detect_topic_relation(ZH_PORT_PROBLEM, "端口检查") == "same_topic"


def test_topic_hint_recalls_without_query_term_overlap() -> None:
    backend = InMemoryMemoryBackend()
    target_id = backend.store_episode(
        "release window is Friday at 22:00",
        {"topic": "project-apollo-玄武", "session_id": "s1"},
    )

    result = backend.retrieve(
        "继续之前的话题：把上线前检查清单列出来",
        topic_hints=("project-apollo-玄武",),
    )

    assert result.value is not None
    assert [chunk.id for chunk in result.value] == [target_id]
