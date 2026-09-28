"""Explicitly backfill missing vectors for the configured local embedding model."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/default.toml")
    args = parser.parse_args()
    config_path = PROJECT_ROOT / args.config
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)

    from src.main import create_memory_backend
    from src.memory.sqlite_backend import SQLiteMemoryBackend

    backend = create_memory_backend(config)
    if not isinstance(backend, SQLiteMemoryBackend) or backend._embedding is None:
        print("No SQLite embedding backend is configured.")
        return 1
    if not backend._embedding.health_check():
        print("Local embedding backend is unavailable.")
        return 1

    model_id = backend._embedding.model_id()
    dimensions = backend._embedding.dimensions()
    connection = backend._conn
    if connection is None:
        print("SQLite backend is closed.")
        return 1
    rows = connection.execute(
        """
        SELECT episodes.id, episodes.content
        FROM episodes
        LEFT JOIN episode_vectors ON episode_vectors.episode_id = episodes.id
            AND episode_vectors.model_id = ? AND episode_vectors.dim = ?
        WHERE episode_vectors.episode_id IS NULL
        ORDER BY episodes.created_at, episodes.id
        """,
        (model_id, dimensions),
    ).fetchall()
    for row in rows:
        backend._store_vector(str(row["id"]), str(row["content"]))
    print(f"Backfilled {len(rows)} episode(s) for {model_id} ({dimensions} dimensions).")
    backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
