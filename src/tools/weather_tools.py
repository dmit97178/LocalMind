"""Registered weather tool factory and outbound location checks."""

from __future__ import annotations

import unicodedata

from src.adapters.weather_provider import WeatherProvider
from src.core.schemas import ParamInstanceCheck, ToolContext, ToolDef, ToolError
from src.safety.guarded_executor import contains_bare_secret, contains_sensitive_value
from src.tools.registry import RegisteredTool

_NON_LOCATION_VALUES = frozenset({
    "今天", "今日", "现在", "此刻", "目前", "明天", "后天", "昨天", "今晚",
    "早上", "上午", "中午", "下午", "晚上",
    "天气", "怎么样", "如何", "什么", "哪里", "哪儿", "多少", "是否", "吗", "呢",
    "这里", "那里", "这儿", "那儿", "这个", "那个", "上述", "前述", "它",
})


def _is_location_instance(value: str) -> bool:
    normalized = unicodedata.normalize("NFC", value).strip()
    return bool(normalized) and normalized not in _NON_LOCATION_VALUES and not any(
        marker in normalized for marker in ("?", "？")
    )


_LOCATION_INSTANCE = ParamInstanceCheck(
    predicate=_is_location_instance,
    reject_whole_input=True,
)

WEATHER_TOOL_DEF = ToolDef(
    name="weather.current",
    description="查询指定地点的当前天气与当日预报（需联网）",
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
    },
    risk_level="normal",
    approval_profile="standard",
    supply_by_echo=("location",),
    audit_redact_all_params=True,
    param_instance_checks={"location": _LOCATION_INSTANCE},
    egress=True,
)

_FORBIDDEN = frozenset("/?&#=:@%")


def make_weather_tool(provider: WeatherProvider) -> RegisteredTool:
    """Bind a provider without leaking it into the handler's call contract."""
    def handler(params: dict, context: ToolContext) -> dict:
        location = params.get("location")
        if not isinstance(location, str):
            raise _location_error()
        location = unicodedata.normalize("NFC", location)
        if (
            not 1 <= len(location) <= 64
            or any(unicodedata.category(char) == "Cc" or char in _FORBIDDEN for char in location)
            or contains_sensitive_value(location)
            or contains_bare_secret(location)
        ):
            raise _location_error()
        return provider.current_weather(location)

    return RegisteredTool(definition=WEATHER_TOOL_DEF, handler=handler)


def _location_error() -> ToolError:
    return ToolError(
        code="TOOL_EXEC_ERROR", message="Weather location rejected before egress",
        user_message="地点表述无法作为查询发出。", recoverable=True,
        details={"reason": "location_rejected"},
    )
