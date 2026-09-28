"""Builtin tool registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.core.schemas import PreflightReport, ToolContext, ToolDef
from src.tools import file_tools, system_tools

ToolHandler = Callable[[dict, ToolContext], dict]
ToolPreflight = Callable[[dict, ToolContext], PreflightReport]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDef
    handler: ToolHandler
    preflight: ToolPreflight | None = None


BUILTIN_TOOLS: dict[str, RegisteredTool] = {
    "system.echo": RegisteredTool(
        definition=ToolDef(
            name="system.echo",
            description="Echo a message.",
            parameters={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            risk_level="normal",
        ),
        handler=system_tools.echo,
    ),
    "system.get_time": RegisteredTool(
        definition=ToolDef(
            name="system.get_time",
            description="Return the current UTC timestamp.",
            parameters={"type": "object", "properties": {}, "required": []},
            risk_level="normal",
        ),
        handler=system_tools.get_time,
    ),
    "file.read": RegisteredTool(
        definition=ToolDef(
            name="file.read",
            description="Read a UTF-8 text file.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            risk_level="sensitive",
        ),
        handler=file_tools.read_file,
        preflight=file_tools.preflight_read,
    ),
    "file.list_dir": RegisteredTool(
        definition=ToolDef(
            name="file.list_dir",
            description="List direct children of a directory.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            risk_level="normal",
        ),
        handler=file_tools.list_dir,
        preflight=file_tools.preflight_list_dir,
    ),
    "file.stat": RegisteredTool(
        definition=ToolDef(
            name="file.stat",
            description="Return file or directory metadata without reading content.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            risk_level="normal",
        ),
        handler=file_tools.stat_file,
        preflight=file_tools.preflight_stat,
    ),
    "file.write": RegisteredTool(
        definition=ToolDef(
            name="file.write",
            description="Write a UTF-8 text file inside the configured workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            risk_level="sensitive",
        ),
        handler=file_tools.write_file,
        preflight=file_tools.preflight_write,
    ),
}

DEFAULT_WHITELIST = tuple(BUILTIN_TOOLS.keys())
_TEST_ONLY_TOOL_NAMES = frozenset({"system.echo"})


def product_tool_definitions() -> tuple[ToolDef, ...]:
    """Return the live built-in registration set excluding test-only helpers."""

    from src.tools.document_tools import DOCUMENT_TOOL_DEF
    from src.tools.search_tools import SEARCH_TOOL_DEF

    static = tuple(
        registered.definition
        for name, registered in BUILTIN_TOOLS.items()
        if name not in _TEST_ONLY_TOOL_NAMES
    )
    return (*static, DOCUMENT_TOOL_DEF, SEARCH_TOOL_DEF)
