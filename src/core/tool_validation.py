"""Pure validation helpers shared by tool catalog, policy, planner, and executor."""

from __future__ import annotations

import inspect
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.core.schemas import LocalMindError, ParamInstanceCheck, ToolCallDraft, ToolDef

MAX_TOOL_COUNT = 32
MAX_TOOL_CATALOG_BYTES = 8192
_ROOT_KEYS = {"type", "properties", "required"}
_PROPERTY_KEYS = {"type"}
_VALUE_TYPES = {"object", "string", "integer", "number", "boolean", "array"}


@dataclass(frozen=True)
class ToolCallValidation:
    """Deterministic validation result for one structured tool-call draft."""

    ok: bool
    reason: str
    tool_def: ToolDef | None = None
    missing: tuple[str, ...] = ()
    offending: tuple[str, ...] = ()
    instance_rejected: tuple[str, ...] = ()


def validate_tool_catalog(tool_defs: Sequence[ToolDef]) -> tuple[ToolDef, ...]:
    """Validate and freeze a bounded tool catalog, failing loudly on bad config."""

    tools = tuple(tool_defs)
    if len(tools) > MAX_TOOL_COUNT:
        raise _config_error("tool_catalog_too_large", tool_count=len(tools))
    names: set[str] = set()
    for tool in tools:
        if not isinstance(tool.name, str) or not tool.name.strip() or tool.name in names:
            raise _config_error("tool_catalog_duplicate", tool.name)
        names.add(tool.name)
        if not _valid_parameters_schema(tool.parameters):
            raise _config_error("tool_schema_invalid", tool.name)
        if not _valid_instance_checks(tool):
            invalid_names = sorted(
                str(name)
                for name in tool.param_instance_checks
                if name not in tool.parameters.get("properties", {})
            )
            raise _config_error(
                "param_instance_declaration_invalid",
                tool.name,
                invalid_params=invalid_names,
            )
    catalog_bytes = len(render_tool_catalog(tools).encode("utf-8"))
    if catalog_bytes > MAX_TOOL_CATALOG_BYTES:
        raise _config_error("tool_catalog_too_large", catalog_bytes=catalog_bytes)
    return tools


def render_tool_catalog(tool_defs: Sequence[ToolDef]) -> str:
    """Return the canonical prompt representation used for catalog byte accounting."""

    payload = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "risk_level": tool.risk_level,
        }
        for tool in tool_defs
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_tool_call(
    draft: ToolCallDraft,
    tool_defs: Sequence[ToolDef],
) -> ToolCallValidation:
    """Validate membership, required values, argument names, and shallow value types."""

    catalog = {tool.name: tool for tool in tool_defs}
    tool = catalog.get(draft.tool_name)
    if tool is None:
        return ToolCallValidation(False, "unknown_tool")
    if not _valid_parameters_schema(tool.parameters):
        return ToolCallValidation(False, "param_type", tool)
    properties = tool.parameters["properties"]
    required = tool.parameters["required"]
    unknown = tuple(sorted(str(key) for key in draft.arguments if key not in properties))
    if unknown:
        return ToolCallValidation(False, "param_unknown_key", tool, offending=unknown)
    instance_rejected = rejected_instance_params(draft.arguments, tool)
    required_missing = tuple(
        name
        for name in required
        if name not in draft.arguments or _empty_required_value(draft.arguments[name])
    )
    missing = tuple(dict.fromkeys(required_missing + instance_rejected))
    if missing:
        return ToolCallValidation(
            False,
            "param_missing",
            tool,
            missing=missing,
            instance_rejected=instance_rejected,
        )
    wrong_types = tuple(
        name
        for name, value in draft.arguments.items()
        if not _matches_type(value, properties[name]["type"])
    )
    if wrong_types:
        return ToolCallValidation(False, "param_type", tool, offending=wrong_types)
    return ToolCallValidation(True, "ok", tool)


def rejected_instance_params(
    arguments: Mapping[str, object],
    tool_def: ToolDef,
    current_input: str | None = None,
) -> tuple[str, ...]:
    """Return provided string parameters rejected by their tool-owned checks."""

    rejected: list[str] = []
    normalized_input = _normalized_instance_text(current_input) if current_input is not None else None
    for name in sorted(tool_def.param_instance_checks):
        value = arguments.get(name)
        if not isinstance(value, str):
            continue
        check = tool_def.param_instance_checks[name]
        normalized_value = _normalized_instance_text(value)
        whole_input = (
            check.reject_whole_input
            and normalized_input is not None
            and normalized_value == normalized_input
        )
        try:
            accepted = check.predicate(value)
        except Exception:
            accepted = False
        if whole_input or not accepted:
            rejected.append(name)
    return tuple(rejected)


def _valid_parameters_schema(schema: object) -> bool:
    if not isinstance(schema, dict) or set(schema) != _ROOT_KEYS:
        return False
    if schema.get("type") != "object":
        return False
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        return False
    if any(not isinstance(name, str) for name in required) or len(set(required)) != len(required):
        return False
    if any(name not in properties for name in required):
        return False
    for name, property_schema in properties.items():
        if not isinstance(name, str) or not name:
            return False
        if not isinstance(property_schema, dict) or set(property_schema) != _PROPERTY_KEYS:
            return False
        if property_schema.get("type") not in _VALUE_TYPES:
            return False
    return True


def _valid_instance_checks(tool: ToolDef) -> bool:
    checks = tool.param_instance_checks
    if not isinstance(checks, Mapping):
        return False
    properties = tool.parameters.get("properties", {})
    for name, check in checks.items():
        if (
            not isinstance(name, str)
            or name not in properties
            or not isinstance(check, ParamInstanceCheck)
            or not callable(check.predicate)
            or not _stable_predicate(check.predicate)
        ):
            return False
    return True


def _stable_predicate(predicate: object) -> bool:
    if inspect.isfunction(predicate):
        return predicate.__name__ != "<lambda>" and "<locals>" not in predicate.__qualname__
    return callable(predicate)


def _normalized_instance_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def _matches_type(value: object, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _empty_required_value(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _config_error(
    reason: str,
    tool_name: str | None = None,
    **diagnostics: object,
) -> LocalMindError:
    details: dict[str, object] = {"reason": reason, **diagnostics}
    if tool_name is not None:
        details["tool_name"] = tool_name
    return LocalMindError(
        code="CONFIG_ERROR",
        message=f"Invalid tool catalog: {reason}",
        user_message="系统配置有误，请检查工具目录。",
        recoverable=False,
        details=details,
    )
