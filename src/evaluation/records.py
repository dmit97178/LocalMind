"""Small, metadata-only JSONL helpers shared by the evaluation parent and child."""

from __future__ import annotations

import json
from pathlib import Path


def append_record(path: Path, record: dict[str, object]) -> None:
    """Append one JSON object using the canonical evaluation JSONL encoding."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")


def read_records(path: Path) -> list[dict[str, object]]:
    """Read complete JSON object lines, ignoring a partial final child-process line."""

    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
