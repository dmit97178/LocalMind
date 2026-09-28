"""Business rules and ownership for persistent project state."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from src.core.interfaces import ProjectRecordStore
from src.core.schemas import LocalMindError, ProjectState
from src.core.text_utils import tokenize

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MANUAL_FIELDS = frozenset({"title", "goal", "constraints", "status", "summary", "topic_tags"})
_STATUSES = frozenset({"active", "paused", "done", "archived"})


class ProjectStore:
    """Apply project validation and manual-override rules over a record store."""

    def __init__(
        self, records: ProjectRecordStore, *, auto_create: bool, summary_max_chars: int
    ) -> None:
        if (
            not isinstance(summary_max_chars, int)
            or isinstance(summary_max_chars, bool)
            or summary_max_chars < 1
        ):
            raise _memory_error("summary_max_chars must be a positive integer")
        self._records = records
        self._auto_create = auto_create
        self._summary_max_chars = summary_max_chars

    @staticmethod
    def normalize_project_id(value: str) -> str:
        """Normalize a user-facing project label into a valid project id."""

        return _normalize_project_id(value)

    def resolve(self, input_text: str, explicit_project_id: str | None) -> str | None:
        if explicit_project_id is not None and explicit_project_id.strip():
            return _normalize_project_id(explicit_project_id)

        input_tokens = tokenize(input_text)
        matches = []
        for project_id in self._records.list_project_ids():
            state = self.load(project_id)
            if state is not None and input_tokens.intersection(
                tokenize(" ".join((state.title, *state.topic_tags)))
            ):
                matches.append(state.project_id)
        return matches[0] if len(matches) == 1 else None

    def ensure(self, project_id: str) -> ProjectState | None:
        normalized = _normalize_project_id(project_id)
        current = self.load(normalized)
        if current is not None or not self._auto_create:
            return current
        now = _timestamp()
        state = ProjectState(
            normalized, normalized, "", (), "active", "", (), frozenset(), now, now
        )
        self._write(state)
        return state

    def load(self, project_id: str) -> ProjectState | None:
        record = self._records.get_project_record(project_id)
        return None if record is None else _state_from_record(record, self._summary_max_chars)

    def set_manual(self, project_id: str, field: str, value: object) -> None:
        state = self._require(project_id)
        _validate_manual_field(field)
        updated = _replace_field(state, field, value)
        self._write(replace(updated, manual_overrides=updated.manual_overrides | {field}))

    def clear_manual(self, project_id: str, field: str) -> None:
        state = self._require(project_id)
        _validate_manual_field(field)
        self._write(replace(state, manual_overrides=state.manual_overrides - {field}))

    def update_auto(
        self, project_id: str, *, summary: str | None = None, add_topic_tags: Sequence[str] = ()
    ) -> None:
        state = self.load(project_id)
        if state is None:
            return
        updated = state
        if summary is not None and "summary" not in state.manual_overrides:
            updated = _replace_field(updated, "summary", summary[: self._summary_max_chars])
        if add_topic_tags and "topic_tags" not in state.manual_overrides:
            updated = _replace_field(
                updated,
                "topic_tags",
                tuple(dict.fromkeys((*updated.topic_tags, *add_topic_tags)))[:32],
            )
        self._write(updated)

    def list_project_ids(self) -> list[str]:
        return self._records.list_project_ids()

    def _require(self, project_id: str) -> ProjectState:
        state = self.load(project_id)
        if state is None:
            raise _memory_error(f"Unknown project id: {project_id}")
        return state

    def _write(self, state: ProjectState) -> None:
        _validate_state(state, self._summary_max_chars)
        updated = replace(state, updated_at=_timestamp())
        self._records.put_project_record(
            {
                "project_id": updated.project_id,
                "title": updated.title,
                "goal": updated.goal,
                "constraints": list(updated.constraints),
                "status": updated.status,
                "summary": updated.summary,
                "topic_tags": list(updated.topic_tags),
                "manual_overrides": sorted(updated.manual_overrides),
                "created_at": updated.created_at,
                "updated_at": updated.updated_at,
            }
        )


def _normalize_project_id(value: str) -> str:
    normalized = re.sub(r"\s+", "-", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9_-]", "", normalized).strip("-_")
    if not _PROJECT_ID_RE.fullmatch(normalized):
        raise _memory_error(f"Invalid project id: {value!r}")
    return normalized


def _state_from_record(record: dict, summary_max_chars: int) -> ProjectState:
    try:
        state = ProjectState(
            project_id=str(record["project_id"]),
            title=str(record["title"]),
            goal=str(record["goal"]),
            constraints=tuple(record["constraints"]),
            status=str(record["status"]),
            summary=str(record["summary"]),
            topic_tags=tuple(record["topic_tags"]),
            manual_overrides=frozenset(record["manual_overrides"]),
            created_at=str(record["created_at"]),
            updated_at=str(record["updated_at"]),
        )
    except (KeyError, TypeError) as exc:
        raise _memory_error("Project record has an invalid shape") from exc
    _validate_state(state, summary_max_chars)
    return state


def _replace_field(state: ProjectState, field: str, value: object) -> ProjectState:
    if field == "constraints" and isinstance(value, (list, tuple)):
        return replace(state, constraints=tuple(value))
    if field == "topic_tags" and isinstance(value, (list, tuple)):
        return replace(state, topic_tags=tuple(value))
    if isinstance(value, str):
        if field == "title":
            return replace(state, title=value)
        if field == "goal":
            return replace(state, goal=value)
        if field == "status":
            return replace(state, status=value)
        if field == "summary":
            return replace(state, summary=value)
    raise _memory_error(f"Invalid value for project field: {field!r}")


def _validate_manual_field(field: str) -> None:
    if field not in _MANUAL_FIELDS:
        raise _memory_error(f"Invalid manual project field: {field!r}")


def _validate_state(state: ProjectState, summary_max_chars: int) -> None:
    if not _PROJECT_ID_RE.fullmatch(state.project_id):
        raise _memory_error("Project state has an invalid project_id")
    if not state.title or len(state.title) > 80 or len(state.goal) > 500:
        raise _memory_error("Project state title or goal exceeds its limit")
    if state.status not in _STATUSES or len(state.summary) > summary_max_chars:
        raise _memory_error("Project state status or summary is invalid")
    if len(state.constraints) > 10 or any(
        not isinstance(item, str) or len(item) > 200 for item in state.constraints
    ):
        raise _memory_error("Project state constraints are invalid")
    if len(state.topic_tags) > 32 or any(not isinstance(item, str) for item in state.topic_tags):
        raise _memory_error("Project state topic tags are invalid")
    if not state.manual_overrides.issubset(_MANUAL_FIELDS):
        raise _memory_error("Project state manual overrides are invalid")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _memory_error(message: str) -> LocalMindError:
    return LocalMindError("MEMORY_ERROR", message, "项目记忆数据无效，无法保存。", recoverable=True)
