"""Input normalization for the P0a main loop."""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.schemas import InputEvent, LocalMindError


class InputNormalizer:
    """Normalize raw CLI input into an InputEvent."""

    def normalize(
        self,
        raw_text: str,
        session_id: str,
        project_id: str | None = None,
    ) -> InputEvent:
        text = raw_text.strip()
        if not text:
            raise LocalMindError(
                code="INVALID_INPUT",
                message="Input text is blank after trimming whitespace",
                user_message="输入不能为空。",
                recoverable=True,
            )

        return InputEvent(
            text=text,
            session_id=session_id,
            project_id=project_id,
            timestamp=datetime.now(UTC).isoformat(),
            source="cli",
        )
