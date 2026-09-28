"""Session-isolated deterministic topic routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.schemas import TopicDecision

_TOPIC_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


@dataclass
class _SessionTopicState:
    current_topic: str = ""
    current_project_id: str | None = None
    history: list[str] | None = None


class TopicTracker:
    """Track one independent current topic and project per session."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionTopicState] = {}

    def current_topic(self, session_id: str) -> str:
        return self._sessions.get(session_id, _SessionTopicState()).current_topic

    def current_project_id(self, session_id: str) -> str | None:
        return self._sessions.get(session_id, _SessionTopicState()).current_project_id

    def topics_history(self, session_id: str) -> tuple[str, ...]:
        state = self._sessions.get(session_id)
        if state is None or state.history is None:
            return ()
        return tuple(state.history)

    def on_turn(
        self,
        session_id: str,
        input_text: str,
        *,
        relation: str,
        project_id: str | None,
    ) -> TopicDecision:
        state = self._sessions.setdefault(session_id, _SessionTopicState())
        previous_topic = state.current_topic
        project_switched = project_id != state.current_project_id

        if not previous_topic:
            relation = "new_topic"

        if relation not in {"same_topic", "new_topic", "shift_with_reference", "ambiguous"}:
            relation = "ambiguous"

        referenced_topic = previous_topic if relation == "shift_with_reference" else None
        if project_switched or relation in {"new_topic", "shift_with_reference"}:
            topic_label = _derive_topic_label(input_text)
        else:
            topic_label = previous_topic

        state.current_topic = topic_label
        state.current_project_id = project_id
        if state.history is None:
            state.history = []
        if not state.history or state.history[-1] != topic_label:
            state.history.append(topic_label)
        return TopicDecision(
            session_id=session_id,
            relation=relation,
            topic_label=topic_label,
            referenced_topic=referenced_topic,
            project_id=project_id,
            project_switched=project_switched,
        )

    def end_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def _derive_topic_label(input_text: str) -> str:
    words = [word.lower() for word in _TOPIC_WORD_RE.findall(input_text)]
    label = "-".join(words[:3])
    return label or "untitled-topic"
