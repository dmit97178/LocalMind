"""P0 built-in ToolBackend implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.interfaces import ToolBackend
from src.core.schemas import (
    LocalMindError,
    PreflightReport,
    Result,
    ToolCallDraft,
    ToolCapability,
    ToolContext,
    ToolDef,
    ToolError,
)
from src.core.tool_validation import validate_tool_call, validate_tool_catalog
from src.tools.capabilities import BUILTIN_CAPABILITIES, validate_capabilities
from src.tools.registry import BUILTIN_TOOLS, DEFAULT_WHITELIST, RegisteredTool
from src.tools.weather_tools import WEATHER_TOOL_DEF

if TYPE_CHECKING:
    from src.adapters.weather_provider import WeatherProvider


@dataclass
class BuiltinToolBackend(ToolBackend):
    """Local read-only/basic tool backend used by P0a."""

    config: dict | None = None
    capabilities_enabled: bool = False
    weather_provider: WeatherProvider | None = None
    weather_settings: dict | None = None
    document_settings: dict | None = None
    search_settings: dict | None = None
    _whitelist: tuple[str, ...] = field(init=False)
    _workspace_root: Path = field(init=False)
    _active: dict[str, RegisteredTool] = field(init=False)
    _capabilities: tuple[ToolCapability, ...] = field(init=False)

    def __post_init__(self) -> None:
        config = self.config or {}
        weather = self.weather_settings or {}
        if weather.get("provider", "none") == "open_meteo" and self.weather_provider is None:
            from src.adapters.weather_provider import OpenMeteoProvider, WeatherConnectionConfig

            connection = weather.get("connection", {})
            self.weather_provider = OpenMeteoProvider(WeatherConnectionConfig(
                connect_timeout_seconds=connection.get("connect_timeout_seconds", 5),
                read_timeout_seconds=connection.get("read_timeout_seconds", 10),
            ))
        self._whitelist = tuple(_extract_whitelist(config))
        self._workspace_root = Path(_extract_workspace_root(config)).resolve()
        registered = dict(BUILTIN_TOOLS)
        from src.tools.document_tools import make_document_tool
        from src.tools.search_tools import make_search_tool

        document_tool = make_document_tool(self.document_settings or {})
        search_tool = make_search_tool(self.search_settings or {})
        registered[document_tool.definition.name] = document_tool
        registered[search_tool.definition.name] = search_tool
        if self.weather_provider is not None:
            from src.tools.weather_tools import make_weather_tool

            registered["weather.current"] = make_weather_tool(self.weather_provider)
        self._active = {
            name: registered[name] for name in self._whitelist if name in registered
        }
        validate_tool_catalog([tool.definition for tool in registered.values()])
        known_tools = {tool.definition.name: tool.definition for tool in registered.values()}
        known_tools[WEATHER_TOOL_DEF.name] = WEATHER_TOOL_DEF
        self._capabilities = validate_capabilities(
            BUILTIN_CAPABILITIES,
            self.list_tools(),
            enabled=self.capabilities_enabled,
            registered_tools=list(known_tools.values()),
        )

    def list_tools(self) -> list[ToolDef]:
        return [tool.definition for tool in self._active.values()]

    def list_capabilities(self) -> list[ToolCapability]:
        return list(self._capabilities)

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        if tool_name not in self._active:
            return Result.err(
                ToolError(
                    code="TOOL_NOT_FOUND",
                    message=f"Builtin tool is not available: {tool_name}",
                    user_message="所需工具不可用。",
                    recoverable=True,
                    details={"tool_name": tool_name},
                )
            )

        tool = self._active[tool_name]
        validation = validate_tool_call(
            ToolCallDraft(tool_name, dict(params)),
            [tool.definition],
        )
        if not validation.ok:
            return Result.err(
                ToolError(
                    code="TOOL_PARAM_ERROR",
                    message=f"Tool {tool_name} parameters rejected: {validation.reason}",
                    user_message="操作参数不正确。",
                    recoverable=True,
                    details={
                        "tool_name": tool_name,
                        "reason": validation.reason,
                        "missing": validation.missing,
                        "offending": validation.offending,
                    },
                )
            )

        try:
            context = ToolContext(self._workspace_root, tool.definition)
            return Result.ok(tool.handler(dict(params), context))
        except LocalMindError as exc:
            return Result.err(exc)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            return Result.err(
                ToolError(
                    code="TOOL_EXEC_ERROR",
                    message=f"Tool {tool_name} failed: {exc}",
                    user_message="操作执行失败。",
                    recoverable=True,
                    details={"tool_name": tool_name, "error": str(exc)},
                )
            )

    def preflight(self, tool_name: str, params: dict) -> PreflightReport:
        if tool_name not in self._active:
            return super().preflight(tool_name, params)
        tool = self._active[tool_name]
        if tool.preflight is None:
            return super().preflight(tool_name, params)
        return tool.preflight(
            dict(params),
            ToolContext(self._workspace_root, tool.definition),
        )


def _extract_whitelist(config: dict) -> list[str]:
    if isinstance(config.get("config"), dict):
        nested = config["config"]
        if isinstance(nested.get("whitelist"), list):
            return [str(item) for item in nested["whitelist"]]
    if isinstance(config.get("whitelist"), list):
        return [str(item) for item in config["whitelist"]]
    return list(DEFAULT_WHITELIST)


def _extract_workspace_root(config: dict) -> str:
    nested_value = config.get("config")
    nested: dict = nested_value if isinstance(nested_value, dict) else {}
    value = nested.get("workspace_root", config.get("workspace_root", "./data/workspace"))
    return str(value)
