"""Plain-text P0a response builder."""

from __future__ import annotations

import unicodedata

from src.core.schemas import ExecutionPlan, ResponseOutput

DISPLAY_LIMIT = 4096


class ResponseBuilder:
    """Format completed tool results without a model call."""

    def build(self, plan: ExecutionPlan, results: dict[int, dict[str, object]]) -> ResponseOutput:
        if not results:
            return ResponseOutput("没有需要执行的操作。", "没有需要执行的操作。")

        lines = []
        for step_index, result in results.items():
            tool_name = plan.steps[step_index].tool_name
            summary = ", ".join(
                f"{sanitize_display_text(str(key))}: {_sanitize_display_value(value)}"
                for key, value in result.items()
            )
            if len(summary) > DISPLAY_LIMIT:
                original_length = len(summary)
                summary = (
                    summary[:DISPLAY_LIMIT]
                    + f"…（已截断显示，原文 {original_length} 码点）"
                )
            lines.append(f"[{step_index}] {tool_name}：{summary}")
        return ResponseOutput(
            display="\n".join(lines),
            narrative_reply=f"执行结果 {len(results)} 条，已以结构化记录留存。",
        )


def _sanitize_display_value(value: object) -> object:
    if isinstance(value, str):
        return sanitize_display_text(value)
    if isinstance(value, dict):
        return {
            sanitize_display_text(str(key)): _sanitize_display_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_display_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_display_value(item) for item in value)
    return value


def sanitize_display_text(value: str) -> str:
    return "".join(
        char
        for char in value
        if char in {"\n", "\t"} or unicodedata.category(char) not in {"Cc", "Cf"}
    )
