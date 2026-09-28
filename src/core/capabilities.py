"""Pure capability-to-tool membership checks."""

import json
from collections.abc import Sequence

from src.core.schemas import LocalMindError, ToolCapability, ToolDef


def validate_active_capabilities(
    capabilities: Sequence[ToolCapability], tools: Sequence[ToolDef]
) -> tuple[ToolCapability, ...]:
    """Check the runtime directory against the active tool set."""

    items = tuple(capabilities)
    _validate_capability_shapes(items)
    active_names = {tool.name for tool in tools}
    covered = {name for item in items for name in item.tools}
    missing = sorted(active_names - covered)
    if missing:
        raise _catalog_error("capability_coverage_missing", uncovered_tools=missing)
    if len(items) > 8:
        raise _catalog_error("capability_catalog_too_large", capability_count=len(items))
    size = len(json.dumps(
        [{"capability_id": item.capability_id, "summary": item.summary} for item in items],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8"))
    if size > 2048:
        raise _catalog_error("capability_catalog_too_large", catalog_bytes=size)
    return items


def validate_capability_declarations(
    capabilities: Sequence[ToolCapability], registered_tools: Sequence[ToolDef]
) -> tuple[ToolCapability, ...]:
    """Validate declarations against the registration set before active filtering."""

    items = tuple(capabilities)
    _validate_capability_shapes(items)
    registered_names = {tool.name for tool in registered_tools}
    for item in items:
        unknown = sorted(set(item.tools) - registered_names)
        if unknown:
            raise _catalog_error("capability_declaration_invalid", unknown_tools=unknown)
    return items


def _validate_capability_shapes(items: tuple[ToolCapability, ...]) -> None:
    ids: set[str] = set()
    for item in items:
        if (
            not item.capability_id or item.capability_id in ids
            or not item.summary or len(item.summary) > 80
            or not item.tools or len(set(item.tools)) != len(item.tools)
        ):
            raise _catalog_error("capability_declaration_invalid")
        ids.add(item.capability_id)


def _catalog_error(reason: str, **details: object) -> LocalMindError:
    return LocalMindError(
        "CONFIG_ERROR", f"Invalid capability catalog: {reason}", "工具能力配置有误。",
        details={"reason": reason, **details},
    )


def capability_tool_names(
    capability_id: str,
    capabilities: Sequence[ToolCapability],
) -> frozenset[str]:
    for capability in capabilities:
        if capability.capability_id == capability_id:
            return frozenset(capability.tools)
    return frozenset()


def capability_relevance(
    capability_id: str | None,
    tool_name: str,
    capabilities: Sequence[ToolCapability],
) -> str:
    if not capability_id or not any(
        capability.capability_id == capability_id for capability in capabilities
    ):
        return "unrouted"
    return (
        "relevant"
        if tool_name in capability_tool_names(capability_id, capabilities)
        else "irrelevant"
    )
