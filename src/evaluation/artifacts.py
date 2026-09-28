"""Parent-side archival of the sanitized artifacts emitted by evaluation runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def archive_run(
    instance_dir: Path,
    run_id: str,
    evals_dir: Path,
    *,
    transcript: bool,
    remove_instance: bool = True,
) -> Path | None:
    """Archive projected run artifacts, then remove the isolated instance.

    The child process owns all state inside ``instance_dir``.  The parent only
    promotes its JSONL event projection and, when requested, its sanitized
    transcript.  A killed child can leave a partial final JSONL line, which is
    removed before the file becomes a durable evaluation artifact.
    """

    source = instance_dir / "runs" / f"{run_id}.jsonl"
    archived: Path | None = None

    if source.exists():
        _truncate_invalid_jsonl_tail(source)
        evals_dir.mkdir(parents=True, exist_ok=True)
        destination = evals_dir / f"run_{run_id}.jsonl"
        if destination.exists():
            raise FileExistsError(f"evaluation artifact already exists: {destination}")
        shutil.move(str(source), str(destination))
        archived = destination

    if transcript:
        source_transcript = instance_dir / "transcripts" / f"{run_id}.md"
        if source_transcript.exists():
            transcript_dir = evals_dir / "transcripts"
            transcript_dir.mkdir(parents=True, exist_ok=True)
            destination_transcript = transcript_dir / f"run_{run_id}.md"
            if destination_transcript.exists():
                raise FileExistsError(
                    f"evaluation transcript already exists: {destination_transcript}"
                )
            shutil.move(str(source_transcript), str(destination_transcript))

    if remove_instance:
        shutil.rmtree(instance_dir)
    return archived


def _truncate_invalid_jsonl_tail(path: Path) -> None:
    """Remove only an incomplete or invalid tail, rejecting interior corruption."""

    lines = path.read_text(encoding="utf-8").splitlines()
    valid_lines: list[str] = []
    found_invalid = False

    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            found_invalid = True
            continue
        if not isinstance(value, dict):
            found_invalid = True
            continue
        if found_invalid:
            raise ValueError(f"JSONL corruption before final line: {path}")
        valid_lines.append(line)

    if found_invalid:
        content = "\n".join(valid_lines)
        path.write_text(f"{content}\n" if content else "", encoding="utf-8")
