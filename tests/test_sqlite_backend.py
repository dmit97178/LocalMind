"""Tests for the P2 SQLite MemoryBackend implementation."""

from __future__ import annotations

import sqlite3

import pytest

from src.core.interfaces import EmbeddingBackend, MemoryBackend
from src.core.schemas import LocalMindError, Result
from src.memory.in_memory_backend import InMemoryMemoryBackend
from src.memory.sqlite_backend import SQLiteMemoryBackend


@pytest.fixture
def backend() -> SQLiteMemoryBackend:
    instance = SQLiteMemoryBackend({"db_path": ":memory:"})
    yield instance
    instance.close()


def test_sqlite_backend_implements_memory_backend(backend: SQLiteMemoryBackend) -> None:
    assert isinstance(backend, MemoryBackend)


def test_store_episode_and_retrieve_matching_content(backend: SQLiteMemoryBackend) -> None:
    chunk_id = backend.store_episode(
        "User wants to check Ollama port 11434",
        {"topic": "ollama", "session_id": "session-1"},
    )

    result = backend.retrieve("check ollama port")

    assert result.is_ok is True
    assert result.value is not None
    assert result.value[0].id == chunk_id
    assert result.value[0].text == "User wants to check Ollama port 11434"
    assert result.value[0].similarity_score == 1.0


@pytest.mark.parametrize("content", ["", "   ", "\t\n"])
def test_store_episode_rejects_blank_content(
    backend: SQLiteMemoryBackend, content: str
) -> None:
    with pytest.raises(LocalMindError, match="Cannot store a blank") as exc_info:
        backend.store_episode(content, {"topic": "notes", "session_id": "session-1"})

    assert exc_info.value.code == "MEMORY_ERROR"
    assert exc_info.value.recoverable is True


@pytest.mark.parametrize("metadata", [{}, {"topic": "notes"}, {"session_id": "session-1"}])
def test_store_episode_rejects_missing_required_metadata(
    backend: SQLiteMemoryBackend, metadata: dict
) -> None:
    with pytest.raises(LocalMindError, match="metadata missing") as exc_info:
        backend.store_episode("content", metadata)

    assert exc_info.value.code == "MEMORY_ERROR"


def test_retrieve_empty_query_and_invalid_top_k(backend: SQLiteMemoryBackend) -> None:
    backend.store_episode("Ollama port check", {"topic": "ollama", "session_id": "session-1"})

    assert backend.retrieve("   ").value == []
    invalid_result = backend.retrieve("ollama", top_k=0)
    assert invalid_result.is_err is True
    assert invalid_result.error is not None
    assert invalid_result.error.code == "MEMORY_ERROR"


def test_retrieve_orders_by_score_then_id_and_searches_all_sessions(
    backend: SQLiteMemoryBackend,
) -> None:
    first_id = backend.store_episode(
        "alpha beta", {"topic": "notes", "session_id": "session-1"}
    )
    second_id = backend.store_episode(
        "alpha beta gamma", {"topic": "notes", "session_id": "session-2"}
    )
    third_id = backend.store_episode(
        "alpha beta", {"topic": "notes", "session_id": "session-3"}
    )

    result = backend.retrieve("alpha beta gamma")

    assert result.value is not None
    assert [chunk.id for chunk in result.value] == [second_id, *sorted([first_id, third_id])]
    assert [chunk.similarity_score for chunk in result.value] == [1.0, 2 / 3, 2 / 3]


def test_summary_read_write_and_overwrite(backend: SQLiteMemoryBackend) -> None:
    assert backend.get_summary("conversation", "missing") is None

    backend.save_summary("conversation", "session-1", {"summary": "first"})
    backend.save_summary("conversation", "session-1", {"summary": "second"})

    assert backend.get_summary("conversation", "session-1") == {"summary": "second"}


def test_save_summary_rejects_invalid_inputs(backend: SQLiteMemoryBackend) -> None:
    for scope, scope_id, summary in [
        ("", "session-1", {"summary": "text"}),
        ("conversation", "", {"summary": "text"}),
        ("conversation", "session-1", {}),
    ]:
        with pytest.raises(LocalMindError) as exc_info:
            backend.save_summary(scope, scope_id, summary)
        assert exc_info.value.code == "MEMORY_ERROR"


def test_close_is_idempotent_and_prevents_future_operations(backend: SQLiteMemoryBackend) -> None:
    backend.close()
    backend.close()

    with pytest.raises(LocalMindError, match="closed") as exc_info:
        backend.store_episode("content", {"topic": "notes", "session_id": "session-1"})
    assert exc_info.value.code == "MEMORY_ERROR"

    result = backend.retrieve("content")
    assert result.is_err is True
    assert result.error is not None
    assert result.error.code == "MEMORY_ERROR"

    with pytest.raises(LocalMindError) as topic_exc_info:
        backend.detect_topic_relation("continue", "notes")
    assert topic_exc_info.value.code == "MEMORY_ERROR"


def test_sqlite_and_in_memory_have_equivalent_retrieval_and_topic_relations(
    backend: SQLiteMemoryBackend,
) -> None:
    in_memory = InMemoryMemoryBackend()
    episodes = [
        ("检查 Ollama 端口 11434", {"topic": "端口检查", "session_id": "s1"}),
        ("项目使用 SQLite 存储记忆", {"topic": "记忆", "session_id": "s2"}),
    ]
    for content, metadata in episodes:
        backend.store_episode(content, metadata)
        in_memory.store_episode(content, metadata)

    sqlite_result = backend.retrieve("端口检查")
    memory_result = in_memory.retrieve("端口检查")

    assert sqlite_result.value is not None
    assert memory_result.value is not None
    assert [(chunk.text, chunk.similarity_score) for chunk in sqlite_result.value] == [
        (chunk.text, chunk.similarity_score) for chunk in memory_result.value
    ]
    for current_input, topic in [
        ("继续刚才那个端口检查", "ollama port"),
        ("换个话题，讨论数据库索引", "ollama port"),
        ("帮我看看这个", "ollama port"),
    ]:
        assert backend.detect_topic_relation(current_input, topic) == in_memory.detect_topic_relation(
            current_input, topic
        )


def test_initial_migration_records_schema_version(backend: SQLiteMemoryBackend) -> None:
    row = backend._conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()

    assert row is not None
    assert row["version"] == backend._LATEST_VERSION


def test_constructor_reports_an_incompatible_future_schema(tmp_path) -> None:
    db_path = tmp_path / "future-schema.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
        connection.execute("INSERT INTO schema_version (version, applied_at) VALUES (3, 'now')")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(LocalMindError) as exc_info:
        SQLiteMemoryBackend({"db_path": str(db_path)})

    assert exc_info.value.code == "CONFIG_ERROR"
    assert exc_info.value.user_message == "记忆数据库升级失败，请检查 data/memory.db 是否被占用或损坏。"


def test_file_database_uses_wal_mode_and_persists_episodes(tmp_path) -> None:
    db_path = tmp_path / "memory.db"
    first = SQLiteMemoryBackend({"db_path": str(db_path)})
    first.store_episode("persistent ollama note", {"topic": "ollama", "session_id": "s1"})
    first.close()

    connection = sqlite3.connect(db_path)
    try:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()

    second = SQLiteMemoryBackend({"db_path": str(db_path)})
    try:
        result = second.retrieve("ollama")
        assert journal_mode == "wal"
        assert result.value is not None
        assert [chunk.text for chunk in result.value] == ["persistent ollama note"]
    finally:
        second.close()


def test_sqlite_backend_creates_p5_tables_and_persists_project_record(tmp_path) -> None:
    db_path = tmp_path / "memory.db"
    backend = SQLiteMemoryBackend({"db_path": str(db_path)})

    backend.put_project_record(
        {
            "project_id": "client-launch",
            "title": "Client launch",
            "goal": "Ship safely",
            "constraints": [],
            "status": "active",
            "summary": "",
            "topic_tags": [],
            "manual_overrides": [],
            "created_at": "2026-09-09T00:00:00+00:00",
            "updated_at": "2026-09-09T00:00:00+00:00",
        }
    )

    record = backend.get_project_record("client-launch")
    assert record is not None
    assert record["title"] == "Client launch"
    assert backend.list_project_ids() == ["client-launch"]
    assert {"episode_vectors", "projects", "memory_meta"}.issubset(_table_names(db_path))
    backend.close()


def test_v2_migration_moves_legacy_project_summary_into_projects(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            INSERT INTO schema_version VALUES (1, 'now');
            CREATE TABLE summaries (scope TEXT NOT NULL, scope_id TEXT NOT NULL, summary_json TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY (scope, scope_id));
            INSERT INTO summaries VALUES ('project', 'legacy-project', '{"summary":"old summary"}', 'now');
            CREATE TABLE episodes (id TEXT PRIMARY KEY, content TEXT NOT NULL, topic TEXT NOT NULL,
                session_id TEXT NOT NULL, project_id TEXT, timestamp TEXT NOT NULL, created_at TEXT NOT NULL);
            """
        )
        connection.commit()
    finally:
        connection.close()

    backend = SQLiteMemoryBackend({"db_path": str(db_path)})

    assert backend.get_summary("project", "legacy-project") is None
    assert backend.get_project_record("legacy-project") is not None
    assert backend.get_project_record("legacy-project")["summary"] == "old summary"
    backend.close()


def test_sqlite_backend_sanitizes_all_text_write_paths(backend: SQLiteMemoryBackend) -> None:
    chunk_id = backend.store_episode(
        "api_key=sk-live-secret", {"topic": "secrets", "session_id": "s1"}
    )
    backend.save_summary("conversation", "s1", {"summary": "~/.ssh/id_rsa"})
    backend.put_project_record({"project_id": "alpha", "summary": "token=sk-live-secret"})

    episode = backend.retrieve("secrets")

    assert episode.value is not None
    assert "sk-live-secret" not in episode.value[0].text
    assert backend.get_summary("conversation", "s1") == {"summary": "[已脱敏:path]"}
    assert backend.get_project_record("alpha") == {
        "project_id": "alpha",
        "summary": "token=[已脱敏:secret]",
    }
    topic_result = backend.retrieve("secrets")
    assert topic_result.value is not None
    assert topic_result.value[0].id == chunk_id


def test_sqlite_backend_retrieve_applies_p5_scope_hints_and_byte_budget(
    backend: SQLiteMemoryBackend,
) -> None:
    project_id = backend.store_episode(
        "alpha deployment checklist", {"topic": "deploy", "session_id": "s1", "project_id": "alpha"}
    )
    unassigned_id = backend.store_episode(
        "alpha shared note", {"topic": "notes", "session_id": "s1"}
    )
    beta_id = backend.store_episode(
        "alpha private beta deployment", {"topic": "deploy", "session_id": "s1", "project_id": "beta"}
    )

    scoped = backend.retrieve("alpha", project_id="alpha")
    unassigned = backend.retrieve("alpha", project_id=None)
    hinted = backend.retrieve("deployment", topic_hints=("deploy",))
    budgeted = backend.retrieve(
        "alpha", project_id="alpha", max_bytes=len(b"alpha deployment checklist")
    )

    assert scoped.value is not None
    assert {chunk.id for chunk in scoped.value} == {project_id, unassigned_id}
    assert unassigned.value is not None
    assert [chunk.id for chunk in unassigned.value] == [unassigned_id]
    assert hinted.value is not None
    assert {chunk.id for chunk in hinted.value} == {project_id, beta_id}
    assert budgeted.value is not None
    assert [chunk.id for chunk in budgeted.value] == [project_id]


def test_sqlite_backend_topic_hint_recalls_without_query_term_overlap(
    backend: SQLiteMemoryBackend,
) -> None:
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


def test_sqlite_backend_applies_topic_hint_filter_before_scan_limit(
    backend: SQLiteMemoryBackend,
) -> None:
    target_id = backend.store_episode(
        "legacy deployment evidence", {"topic": "legacy", "session_id": "s1"}
    )
    for index in range(501):
        backend.store_episode(
            f"unrelated deployment note {index}", {"topic": "recent", "session_id": "s1"}
        )
    backend._conn.execute("UPDATE episodes SET created_at = '2000-01-01' WHERE id = ?", (target_id,))

    result = backend.retrieve("deployment", topic_hints=("legacy",))

    assert result.value is not None
    assert [chunk.id for chunk in result.value] == [target_id]


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


class _FailingEmbeddingStub(_EmbeddingStub):
    def embed_documents(self, texts: list[str]) -> Result[list[list[float]]]:
        del texts
        return Result.err(LocalMindError("EMBEDDING_ERROR", "offline", "语义检索暂不可用，已切换关键词检索。", True))

    def embed_query(self, text: str) -> Result[list[float]]:
        del text
        return Result.err(LocalMindError("EMBEDDING_ERROR", "offline", "语义检索暂不可用，已切换关键词检索。", True))


class _AlternateEmbeddingStub(_EmbeddingStub):
    def model_id(self) -> str:
        return "alternate-embed"


def test_sqlite_backend_retrieves_semantic_vector_matches(tmp_path) -> None:
    backend = SQLiteMemoryBackend(
        {"db_path": str(tmp_path / "memory.db"), "retrieval": {"keyword_weight": 0.6, "vector_weight": 0.4}},
        embedding=_EmbeddingStub(),
    )
    backend.store_episode("database schema migration", {"topic": "data", "session_id": "s1"})

    result = backend.retrieve("architecture design")

    assert result.value is not None
    assert result.value[0].match_source == "vector"
    assert result.value[0].vector_score == 1.0
    backend.close()


def test_sqlite_backend_records_embedding_model_metadata(tmp_path) -> None:
    db_path = tmp_path / "memory.db"
    backend = SQLiteMemoryBackend({"db_path": str(db_path)}, embedding=_EmbeddingStub())

    rows = backend._conn.execute("SELECT key, value FROM memory_meta ORDER BY key").fetchall()

    assert [(row["key"], row["value"]) for row in rows] == [
        ("embedding_dim", "2"),
        ("embedding_model_id", "test-embed"),
    ]
    backend.close()


def test_sqlite_backend_degrades_to_keyword_retrieval_when_embedding_fails(tmp_path) -> None:
    backend = SQLiteMemoryBackend({"db_path": str(tmp_path / "memory.db")}, embedding=_FailingEmbeddingStub())
    backend.store_episode("database schema migration", {"topic": "data", "session_id": "s1"})

    result = backend.retrieve("database")

    assert result.is_ok is True
    assert result.value is not None
    assert result.value[0].match_source == "keyword"
    backend.close()


def test_sqlite_backend_hides_vectors_written_by_a_different_embedding_model(tmp_path) -> None:
    db_path = tmp_path / "memory.db"
    first = SQLiteMemoryBackend({"db_path": str(db_path)}, embedding=_EmbeddingStub())
    first.store_episode("database schema migration", {"topic": "data", "session_id": "s1"})
    first.close()

    second = SQLiteMemoryBackend({"db_path": str(db_path)}, embedding=_AlternateEmbeddingStub())
    result = second.retrieve("architecture design")

    assert result.value == []
    second.close()


def _table_names(db_path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"db_path": ""},
        {"db_path": ":memory:", "max_search_episodes": 0},
        {"db_path": ":memory:", "max_search_episodes": True},
    ],
)
def test_constructor_rejects_invalid_config(config: dict) -> None:
    with pytest.raises(LocalMindError) as exc_info:
        SQLiteMemoryBackend(config)

    assert exc_info.value.code == "CONFIG_ERROR"
