"""Demonstrate SQLite memory persistence without requiring a model backend."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from src.memory.sqlite_backend import SQLiteMemoryBackend

    db_path = PROJECT_ROOT / "data" / "p2_demo.db"
    _remove_database_files(db_path)
    first = SQLiteMemoryBackend({"db_path": str(db_path)})
    try:
        first.store_episode(
            "User asked to verify SQLite memory persistence.",
            {"topic": "sqlite memory", "session_id": "p2-demo"},
        )
        first.store_episode(
            "Assistant confirmed persistent retrieval after restart.",
            {"topic": "sqlite memory", "session_id": "p2-demo"},
        )
    finally:
        first.close()

    second = SQLiteMemoryBackend({"db_path": str(db_path)})
    try:
        result = second.retrieve("sqlite memory persistence")
        if result.is_err:
            if result.error is None:
                raise RuntimeError("failed result did not include an error")
            raise result.error
        print(f"Persistent chunks after restart: {len(result.value or [])}")
        for chunk in result.value or []:
            print(f"- {chunk.text}")
    finally:
        second.close()
        _remove_database_files(db_path)


def _remove_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
