"""Adapter-local SQLite vector storage and cosine search."""

from __future__ import annotations

import math
import sqlite3
import struct
from collections.abc import Iterable


class SQLiteVectorIndex:
    """Store float32 vectors and scan a bounded compatible subset locally."""

    def __init__(self, connection: sqlite3.Connection, max_scan: int) -> None:
        self._connection = connection
        self._max_scan = max_scan

    def upsert(self, episode_id: str, model_id: str, dim: int, vector: list[float]) -> None:
        _validate_vector(vector, dim)
        self._connection.execute(
            """
            INSERT OR REPLACE INTO episode_vectors (episode_id, model_id, dim, vector)
            VALUES (?, ?, ?, ?)
            """,
            (episode_id, model_id, dim, struct.pack(f"<{dim}f", *vector)),
        )

    def search(
        self,
        query_vector: list[float],
        model_id: str,
        dim: int,
        top_n: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        _validate_vector(query_vector, dim)
        if allowed_ids is not None and not allowed_ids:
            return []

        sql = "SELECT episode_id, vector FROM episode_vectors WHERE model_id = ? AND dim = ?"
        params: list[object] = [model_id, dim]
        if allowed_ids is not None:
            placeholders = ", ".join("?" for _ in allowed_ids)
            sql += f" AND episode_id IN ({placeholders})"
            params.extend(sorted(allowed_ids))
        sql += " ORDER BY episode_id LIMIT ?"
        params.append(self._max_scan)
        rows = self._connection.execute(sql, params).fetchall()

        scored = []
        for episode_id, blob in rows:
            vector = list(struct.unpack(f"<{dim}f", blob))
            scored.append((str(episode_id), _cosine(query_vector, vector)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_n]

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM episode_vectors").fetchone()
        return int(row[0])


def _validate_vector(vector: Iterable[float], dim: int) -> None:
    values = list(vector)
    if dim < 1 or len(values) != dim or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise ValueError("vector must contain finite numeric values matching dim")


def _cosine(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True)) / (left_norm * right_norm)
