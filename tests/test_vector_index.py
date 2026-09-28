"""P5 local SQLite vector-index behavior."""

import sqlite3

import pytest

from src.memory.vector_index import SQLiteVectorIndex


def test_vector_index_filters_before_ranking_and_treats_empty_allowed_ids_as_empty() -> None:
    connection = _connection()
    index = SQLiteVectorIndex(connection, max_scan=10)
    index.upsert("alpha", "embed-v1", 2, [1.0, 0.0])
    index.upsert("beta", "embed-v1", 2, [0.0, 1.0])

    assert index.search([1.0, 0.0], "embed-v1", 2, 3, allowed_ids=set()) == []
    assert index.search([1.0, 0.0], "embed-v1", 2, 3, allowed_ids={"beta"}) == [("beta", 0.0)]


def test_vector_index_returns_cosine_ranked_matches() -> None:
    connection = _connection()
    index = SQLiteVectorIndex(connection, max_scan=10)
    index.upsert("exact", "embed-v1", 2, [1.0, 0.0])
    index.upsert("near", "embed-v1", 2, [0.8, 0.6])

    results = index.search([1.0, 0.0], "embed-v1", 2, 2)

    assert [episode_id for episode_id, _ in results] == ["exact", "near"]
    assert results[0][1] == 1.0
    assert results[1][1] == pytest.approx(0.8)


def test_vector_index_hides_other_models_and_respects_scan_limit() -> None:
    connection = _connection()
    index = SQLiteVectorIndex(connection, max_scan=1)
    index.upsert("a", "embed-v1", 2, [1.0, 0.0])
    index.upsert("b", "embed-v1", 2, [0.0, 1.0])
    index.upsert("other", "embed-v2", 2, [1.0, 0.0])

    assert index.search([1.0, 0.0], "embed-v2", 2, 3) == [("other", 1.0)]
    assert len(index.search([1.0, 0.0], "embed-v1", 2, 3)) == 1


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE episode_vectors (episode_id TEXT PRIMARY KEY, model_id TEXT, dim INTEGER, vector BLOB)"
    )
    return connection
