"""SQLite implementation of the persistent MemoryBackend boundary."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Sequence
from pathlib import Path

from src.core.interfaces import EmbeddingBackend, MemoryBackend
from src.core.memory_hygiene import sanitize_for_memory, sanitize_memory_value
from src.core.schemas import LocalMindError, MemoryChunk, Result
from src.memory.retrieval import detect_topic_relation, fuse_retrieval, keyword_score, tokenize
from src.memory.vector_index import SQLiteVectorIndex

_DEFAULT_MAX_SEARCH_EPISODES = 500
_REQUIRED_EPISODE_METADATA = ("topic", "session_id")


class SQLiteMemoryBackend(MemoryBackend):
    """Persist conversation episodes and summaries in one SQLite database."""

    _LATEST_VERSION = 2

    def __init__(self, config: dict, *, embedding: EmbeddingBackend | None = None) -> None:
        db_path, max_search_episodes, forbidden_paths, retrieval = _validate_config(config)
        self._db_path = db_path
        self._max_search_episodes = max_search_episodes
        self._forbidden_paths = forbidden_paths
        self._embedding = embedding
        self._keyword_weight, self._vector_weight, self._same_project_boost = retrieval
        self._closed = False
        self._conn: sqlite3.Connection | None = None

        try:
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys=ON")
            if db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._run_migrations()
            self._vector_index = SQLiteVectorIndex(self._connection, self._max_search_episodes)
            self._sync_embedding_metadata()
        except sqlite3.Error as exc:
            self._close_after_failed_initialization()
            raise _memory_error(
                "Unable to open or initialize SQLite memory database",
                "记忆系统初始化失败，请检查磁盘空间和权限。",
                recoverable=False,
                details={"error": str(exc)},
            ) from exc
        except OSError as exc:
            self._close_after_failed_initialization()
            raise _memory_error(
                "Unable to create SQLite memory database directory",
                "记忆系统初始化失败，请检查磁盘空间和权限。",
                recoverable=False,
                details={"error": str(exc)},
            ) from exc
        except LocalMindError:
            self._close_after_failed_initialization()
            raise

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
                _memory_error(
                    f"top_k must be a positive integer, got {top_k!r}",
                    "记忆检索参数无效。",
                    recoverable=True,
                    details={"top_k": top_k},
                )
            )

        try:
            self._ensure_open()
            if max_bytes is not None and (
                not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1
            ):
                return Result.err(
                    _memory_error(
                        "max_bytes must be a positive integer",
                        "记忆检索参数无效。",
                        recoverable=True,
                        details={"max_bytes": max_bytes},
                    )
                )
            query_terms = tokenize(query)
            if not query_terms:
                return Result.ok([])
            normalized_hints = tokenize(" ".join(topic_hints))
            scoring_terms = query_terms | normalized_hints
            if normalized_hints:
                hint_predicates = " OR ".join("topic LIKE ?" for _ in normalized_hints)
                scope_sql = f"WHERE {hint_predicates}"
                scope_params: tuple[object, ...] = tuple(
                    f"%{hint}%" for hint in sorted(normalized_hints)
                )
            elif project_id is None:
                scope_sql = "WHERE project_id IS NULL"
                scope_params = ()
            else:
                scope_sql = "WHERE project_id = ? OR project_id IS NULL"
                scope_params = (project_id,)
            rows = self._connection.execute(
                f"""
                SELECT id, content, topic, session_id, project_id, timestamp, created_at
                FROM episodes
                {scope_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*scope_params, self._max_search_episodes),
            ).fetchall()
            chunks: dict[str, MemoryChunk] = {}
            keyword_scores: dict[str, float] = {}
            for row in rows:
                metadata = _row_metadata(row)
                if normalized_hints and not normalized_hints.intersection(tokenize(metadata["topic"])):
                    continue
                chunk = MemoryChunk(id=row["id"], text=row["content"], metadata=metadata)
                chunks[chunk.id] = chunk
                score = keyword_score(scoring_terms, row["content"], metadata)
                if score > 0:
                    keyword_scores[chunk.id] = min(score / 3.0, 1.0)
            vector_scores, vector_available = self._vector_scores(query, set(chunks), top_k)
            fused = fuse_retrieval(
                keyword_scores,
                vector_scores,
                chunks,
                vector_available=vector_available,
                keyword_weight=self._keyword_weight,
                vector_weight=self._vector_weight,
                project_id=project_id,
                same_project_boost=self._same_project_boost,
            )
            results = []
            used_bytes = 0
            for chunk in fused[:top_k]:
                size = len(chunk.text.encode("utf-8"))
                if max_bytes is not None and used_bytes + size > max_bytes:
                    break
                used_bytes += size
                results.append(chunk)
            return Result.ok(results)
        except LocalMindError as exc:
            return Result.err(exc)
        except sqlite3.Error as exc:
            return Result.err(_sqlite_operation_error("retrieve memory episodes", exc))

    def store_episode(self, content: str, metadata: dict) -> str:
        self._ensure_open()
        if not isinstance(content, str) or not content.strip():
            raise _memory_error(
                "Cannot store a blank memory episode",
                "记忆内容为空，无法存储。",
                recoverable=True,
                details={"metadata": dict(metadata) if isinstance(metadata, dict) else metadata},
            )
        _validate_episode_metadata(metadata)

        sanitized_content = sanitize_for_memory(content, forbidden_paths=self._forbidden_paths)
        for _ in range(2):
            chunk_id = f"ep_{uuid.uuid4().hex[:12]}"
            try:
                self._connection.execute(
                    """
                    INSERT INTO episodes (id, content, topic, session_id, project_id, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        sanitized_content,
                        metadata["topic"],
                        metadata["session_id"],
                        metadata.get("project_id"),
                        metadata.get("timestamp", ""),
                    ),
                )
                self._store_vector(chunk_id, sanitized_content)
                return chunk_id
            except sqlite3.IntegrityError:
                continue
            except sqlite3.Error as exc:
                raise _sqlite_operation_error("store memory episode", exc) from exc

        raise _memory_error(
            "Generated duplicate SQLite memory episode ids twice",
            "记忆存储失败，请稍后重试。",
            recoverable=True,
        )

    def get_summary(self, scope: str, scope_id: str) -> dict | None:
        self._ensure_open()
        try:
            row = self._connection.execute(
                "SELECT summary_json FROM summaries WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _sqlite_operation_error("read memory summary", exc) from exc
        if row is None:
            return None

        try:
            summary = json.loads(row["summary_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise _memory_error(
                "Stored memory summary is not valid JSON",
                "记忆数据损坏，摘要无法读取。",
                recoverable=False,
                details={"error": str(exc)},
            ) from exc
        if not isinstance(summary, dict):
            raise _memory_error(
                "Stored memory summary JSON is not an object",
                "记忆数据损坏，摘要无法读取。",
                recoverable=False,
            )
        return summary

    def save_summary(self, scope: str, scope_id: str, summary: dict) -> None:
        self._ensure_open()
        if (
            not isinstance(scope, str)
            or not scope.strip()
            or not isinstance(scope_id, str)
            or not scope_id.strip()
            or not isinstance(summary, dict)
            or not summary
        ):
            raise _memory_error(
                "Cannot save summary with blank scope, blank scope_id, or empty summary",
                "摘要参数不完整，无法保存。",
                recoverable=True,
                details={"scope": scope, "scope_id": scope_id, "summary": summary},
            )
        try:
            summary_json = json.dumps(
                sanitize_memory_value(summary, forbidden_paths=self._forbidden_paths), ensure_ascii=False
            )
            self._connection.execute(
                """
                INSERT OR REPLACE INTO summaries (scope, scope_id, summary_json, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (scope, scope_id, summary_json),
            )
        except (TypeError, ValueError) as exc:
            raise _memory_error(
                "Memory summary cannot be serialized as JSON",
                "摘要参数不完整，无法保存。",
                recoverable=True,
                details={"error": str(exc)},
            ) from exc
        except sqlite3.Error as exc:
            raise _sqlite_operation_error("save memory summary", exc) from exc

    def detect_topic_relation(self, current_input: str, current_topic: str) -> str:
        self._ensure_open()
        return detect_topic_relation(current_input, current_topic)

    def get_project_record(self, project_id: str) -> dict | None:
        self._ensure_open()
        try:
            row = self._connection.execute(
                "SELECT state_json FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise _sqlite_operation_error("read project record", exc) from exc
        if row is None:
            return None
        try:
            record = json.loads(row["state_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise _memory_error(
                "Stored project record is not valid JSON",
                "记忆数据损坏，项目无法读取。",
                recoverable=False,
            ) from exc
        if not isinstance(record, dict):
            raise _memory_error(
                "Stored project record JSON is not an object",
                "记忆数据损坏，项目无法读取。",
                recoverable=False,
            )
        return record

    def put_project_record(self, record: dict) -> None:
        self._ensure_open()
        if not isinstance(record, dict) or not str(record.get("project_id", "")).strip():
            raise _memory_error(
                "Project record requires a project_id",
                "项目记忆数据无效，无法保存。",
                recoverable=True,
            )
        try:
            state_json = json.dumps(
                sanitize_memory_value(record, forbidden_paths=self._forbidden_paths), ensure_ascii=False
            )
            self._connection.execute(
                """
                INSERT OR REPLACE INTO projects (project_id, state_json, created_at, updated_at)
                VALUES (?, ?, COALESCE((SELECT created_at FROM projects WHERE project_id = ?), datetime('now')), datetime('now'))
                """,
                (record["project_id"], state_json, record["project_id"]),
            )
        except (TypeError, ValueError) as exc:
            raise _memory_error(
                "Project record cannot be serialized as JSON",
                "项目记忆数据无效，无法保存。",
                recoverable=True,
            ) from exc
        except sqlite3.Error as exc:
            raise _sqlite_operation_error("store project record", exc) from exc

    def list_project_ids(self) -> list[str]:
        self._ensure_open()
        try:
            rows = self._connection.execute("SELECT project_id FROM projects ORDER BY project_id").fetchall()
        except sqlite3.Error as exc:
            raise _sqlite_operation_error("list project records", exc) from exc
        return [str(row["project_id"]) for row in rows]

    def close(self) -> None:
        """Close the database connection without leaking close-time failures."""

        if self._closed:
            return
        self._closed = True
        if self._conn is None:
            return
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise _closed_error()
        return self._conn

    def _ensure_open(self) -> None:
        if self._closed:
            raise _closed_error()

    def _store_vector(self, chunk_id: str, content: str) -> None:
        if self._embedding is None or not self._embedding.health_check() or self._embedding.dimensions() < 1:
            return
        result = self._embedding.embed_documents([content])
        if result.is_err or not result.value:
            return
        try:
            self._vector_index.upsert(
                chunk_id, self._embedding.model_id(), self._embedding.dimensions(), result.value[0]
            )
        except (ValueError, sqlite3.Error):
            return

    def _sync_embedding_metadata(self) -> None:
        if self._embedding is None or self._embedding.dimensions() < 1:
            return
        self._connection.executemany(
            "INSERT OR REPLACE INTO memory_meta (key, value) VALUES (?, ?)",
            [
                ("embedding_model_id", self._embedding.model_id()),
                ("embedding_dim", str(self._embedding.dimensions())),
            ],
        )

    def _vector_scores(
        self, query: str, allowed_ids: set[str], top_k: int
    ) -> tuple[dict[str, float], bool]:
        if self._embedding is None or not self._embedding.health_check() or self._embedding.dimensions() < 1:
            return {}, False
        result = self._embedding.embed_query(query)
        if result.is_err or result.value is None:
            return {}, False
        try:
            return dict(
                self._vector_index.search(
                    result.value,
                    self._embedding.model_id(),
                    self._embedding.dimensions(),
                    3 * top_k,
                    allowed_ids=allowed_ids,
                )
            ), True
        except (ValueError, sqlite3.Error):
            return {}, False

    def _run_migrations(self) -> None:
        connection = self._connection
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            row = connection.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
            current_version = 0 if row is None or row["version"] is None else row["version"]
            if current_version > self._LATEST_VERSION:
                raise _migration_error(
                    f"Memory database schema version {current_version} is newer than supported "
                    f"version {self._LATEST_VERSION}"
                )
            for version in range(current_version + 1, self._LATEST_VERSION + 1):
                self._run_migration(version)
        except sqlite3.Error as exc:
            raise _migration_error("Memory database migration failed", exc) from exc

    def _run_migration(self, version: int) -> None:
        if version == 2:
            self._run_migration_v2()
            return
        if version != 1:
            raise _migration_error(f"No migration registered for schema version {version}")
        connection = self._connection
        try:
            connection.execute("BEGIN")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL,
                    project_id TEXT,
                    timestamp TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_episodes_session
                ON episodes(session_id, created_at)
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_topic ON episodes(topic)"
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_episodes_project
                ON episodes(project_id, created_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, scope_id)
                )
                """
            )
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
                (1,),
            )
            connection.execute("COMMIT")
        except sqlite3.Error:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def _run_migration_v2(self) -> None:
        connection = self._connection
        try:
            connection.execute("BEGIN")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_vectors (
                    episode_id TEXT PRIMARY KEY REFERENCES episodes(id) ON DELETE CASCADE,
                    model_id TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            legacy_rows = connection.execute(
                "SELECT scope_id, summary_json, updated_at FROM summaries WHERE scope = 'project'"
            ).fetchall()
            for row in legacy_rows:
                try:
                    summary = json.loads(row["summary_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(summary, dict):
                    continue
                project_id = str(row["scope_id"])
                record = {
                    "project_id": project_id,
                    "title": str(summary.get("title", project_id)),
                    "goal": str(summary.get("goal", "")),
                    "constraints": list(summary.get("constraints", [])),
                    "status": str(summary.get("status", "active")),
                    "summary": str(summary.get("summary", "")),
                    "topic_tags": list(summary.get("topic_tags", [])),
                    "manual_overrides": list(summary.get("manual_overrides", [])),
                    "created_at": row["updated_at"],
                    "updated_at": row["updated_at"],
                }
                connection.execute(
                    "INSERT OR IGNORE INTO projects (project_id, state_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (project_id, json.dumps(record, ensure_ascii=False), row["updated_at"], row["updated_at"]),
                )
                connection.execute(
                    "DELETE FROM summaries WHERE scope = 'project' AND scope_id = ?", (project_id,)
                )
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
                (2,),
            )
            connection.execute("COMMIT")
        except sqlite3.Error:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def _close_after_failed_initialization(self) -> None:
        self._closed = True
        if self._conn is None:
            return
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


def _validate_config(config: dict) -> tuple[str, int, tuple[str, ...], tuple[float, float, float]]:
    if not isinstance(config, dict):
        raise _config_error("SQLite memory configuration must be a mapping")
    db_path = config.get("db_path")
    if not isinstance(db_path, str) or not db_path.strip():
        raise _config_error("SQLite memory config requires a non-empty db_path")
    max_search_episodes = config.get("max_search_episodes", _DEFAULT_MAX_SEARCH_EPISODES)
    if (
        not isinstance(max_search_episodes, int)
        or isinstance(max_search_episodes, bool)
        or max_search_episodes < 1
    ):
        raise _config_error("max_search_episodes must be a positive integer")
    forbidden_paths = config.get("forbidden_paths", ())
    if not isinstance(forbidden_paths, (list, tuple)) or any(
        not isinstance(path, str) or not path.strip() for path in forbidden_paths
    ):
        raise _config_error("forbidden_paths must be a sequence of non-empty strings")
    retrieval = config.get("retrieval", {})
    if not isinstance(retrieval, dict):
        raise _config_error("retrieval must be a mapping")
    keyword_weight = _unit_float(retrieval.get("keyword_weight", 0.6), "keyword_weight")
    vector_weight = _unit_float(retrieval.get("vector_weight", 0.4), "vector_weight")
    same_project_boost = _unit_float(retrieval.get("same_project_boost", 0.1), "same_project_boost")
    if abs(keyword_weight + vector_weight - 1.0) > 1e-9:
        raise _config_error("keyword_weight and vector_weight must sum to 1.0")
    return db_path, max_search_episodes, tuple(forbidden_paths), (
        keyword_weight,
        vector_weight,
        same_project_boost,
    )


def _unit_float(value: object, key: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return float(value)
    raise _config_error(f"{key} must be a number in [0, 1]")


def _validate_episode_metadata(metadata: dict) -> None:
    if not isinstance(metadata, dict):
        missing_metadata = list(_REQUIRED_EPISODE_METADATA)
    else:
        missing_metadata = [
            key for key in _REQUIRED_EPISODE_METADATA if not str(metadata.get(key, "")).strip()
        ]
    if missing_metadata:
        raise _memory_error(
            f"Memory episode metadata missing required keys: {missing_metadata}",
            "记忆元数据不完整，无法存储。",
            recoverable=True,
            details={"missing": missing_metadata, "metadata": metadata},
        )


def _row_metadata(row: sqlite3.Row) -> dict:
    return {
        "topic": row["topic"],
        "session_id": row["session_id"],
        "project_id": row["project_id"],
        "timestamp": row["timestamp"],
        "created_at": row["created_at"],
    }


def _closed_error() -> LocalMindError:
    return _memory_error(
        "SQLite memory backend is closed",
        "记忆系统已关闭。",
        recoverable=False,
    )


def _sqlite_operation_error(operation: str, exc: sqlite3.Error) -> LocalMindError:
    raw_message = str(exc).lower()
    if "locked" in raw_message or "busy" in raw_message:
        user_message = "记忆系统繁忙，请稍后重试。"
        recoverable = True
    elif "full" in raw_message:
        user_message = "磁盘空间不足，记忆存储失败。"
        recoverable = False
    else:
        user_message = "记忆系统暂时不可用。"
        recoverable = False
    return _memory_error(
        f"SQLite failed to {operation}: {exc}",
        user_message,
        recoverable=recoverable,
        details={"operation": operation, "error": str(exc)},
    )


def _memory_error(
    message: str,
    user_message: str,
    *,
    recoverable: bool,
    details: dict | None = None,
) -> LocalMindError:
    return LocalMindError(
        code="MEMORY_ERROR",
        message=message,
        user_message=user_message,
        recoverable=recoverable,
        details=details,
    )


def _config_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=message,
        user_message="系统配置有误，请检查。",
        recoverable=False,
    )


def _migration_error(message: str, exc: sqlite3.Error | None = None) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=message if exc is None else f"{message}: {exc}",
        user_message="记忆数据库升级失败，请检查 data/memory.db 是否被占用或损坏。",
        recoverable=False,
        details={"error": str(exc)} if exc is not None else None,
    )
