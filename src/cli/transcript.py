"""Optional, sanitized conversation transcript for resumable CLI demos."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.core.memory_hygiene import sanitize_for_memory

_ROLES = frozenset({"user", "assistant"})


@dataclass(frozen=True)
class TranscriptStore:
    """Append and replay a human-readable dialogue without storing raw secrets."""

    path: Path

    def __init__(self, path: str | Path) -> None:
        object.__setattr__(self, "path", Path(path))

    def append(self, role: str, content: str) -> None:
        if role not in _ROLES:
            raise ValueError(f"Unsupported transcript role: {role}")
        record = {
            "role": role,
            "content": sanitize_for_memory(content),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")

    def read_recent(self, *, turns: int) -> tuple[tuple[str, str], ...]:
        if turns < 0:
            raise ValueError("turns must be non-negative")
        if turns == 0 or not self.path.exists():
            return ()
        records: list[tuple[str, str]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(record, dict):
                continue
            role = record.get("role")
            content = record.get("content")
            if role in _ROLES and isinstance(content, str):
                records.append((role, content))
        return tuple(records[-turns * 2 :])
