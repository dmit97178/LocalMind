"""Built-in system tools with no external dependencies."""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.schemas import ToolContext


def echo(params: dict, context: ToolContext) -> dict:
    del context
    message = params["message"]
    return {"message": str(message)}


def get_time(params: dict, context: ToolContext) -> dict:
    del params, context
    return {"timestamp": datetime.now(UTC).isoformat()}
