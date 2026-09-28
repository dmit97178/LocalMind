"""Locally authoritative declarations for external tool providers."""

from __future__ import annotations

import re
import shutil
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from src.core.capabilities import validate_active_capabilities, validate_capability_declarations
from src.core.risk_vocabulary import APPROVAL_PROFILES, RISK_LEVELS
from src.core.schemas import (
    ExternalToolAdmission,
    LocalMindError,
    ParamInstanceCheck,
    ToolCapability,
    ToolDef,
)

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_PROVIDER_KEYS = frozenset({"enabled", "handshake_timeout_ms", "call_timeout_ms"})
_REPO_ROOT = Path(__file__).parents[2]


@dataclass(frozen=True)
class ProviderDeclaration:
    """Code-signed process identity for one provider."""

    provider_id: str
    argv: tuple[str, ...]
    cwd_from_repo_root: bool = True


def _external_text_instance(value: str) -> bool:
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > 8192:
        return False
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in normalized):
        return False
    if normalized.startswith(("/", "\\", "~")) or _DRIVE_PATH.match(normalized):
        return False
    parsed = urlsplit(normalized)
    return not (parsed.scheme and (parsed.netloc or parsed.scheme in {"file", "data"}))


_EXTERNAL_TEXT_CHECK = ParamInstanceCheck(_external_text_instance)

EXTERNAL_PROVIDERS = (
    ProviderDeclaration("demo", (sys.executable, "scripts/mcp_demo_server.py")),
)

EXTERNAL_TOOL_ADMISSIONS = (
    ExternalToolAdmission(
        provider_id="demo",
        raw_name="json_format",
        alias="json_format",
        description="格式化用户提供的 JSON 文本",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        risk_level="normal",
        side_effect_class="read_only",
        approval_profile="standard",
        supply_by_echo=("text",),
        param_instance_checks={"text": _EXTERNAL_TEXT_CHECK},
    ),
)

EXTERNAL_CAPABILITIES = (
    ToolCapability("text.format", "格式化用户提供的结构化文本", ("demo.json_format",)),
)


def validate_provider_configuration(
    config: object,
    *,
    capability_routing_enabled: bool,
    declarations: tuple[ProviderDeclaration, ...] = EXTERNAL_PROVIDERS,
) -> dict[str, dict[str, object]]:
    """Validate the configuration-only provider controls without starting processes."""

    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise _config_error("tool_provider_invalid")
    known = {item.provider_id for item in declarations}
    normalized: dict[str, dict[str, object]] = {}
    enabled_any = False
    for provider_id, raw in config.items():
        if provider_id not in known:
            raise _config_error("tool_provider_unknown", provider_id=provider_id)
        if not isinstance(raw, dict) or set(raw) - _PROVIDER_KEYS:
            raise _config_error("tool_provider_invalid", provider_id=provider_id)
        enabled = raw.get("enabled", False)
        if not isinstance(enabled, bool):
            raise _config_error("tool_provider_invalid", provider_id=provider_id)
        values: dict[str, object] = {"enabled": enabled}
        for key, default in (("handshake_timeout_ms", 5000), ("call_timeout_ms", 10000)):
            value = raw.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 60000:
                raise _config_error("tool_provider_invalid", provider_id=provider_id)
            values[key] = value
        normalized[provider_id] = values
        enabled_any = enabled_any or enabled
    if enabled_any and not capability_routing_enabled:
        raise _config_error("tool_providers_require_capability_routing")
    return normalized


def resolve_provider_declarations(
    declarations: tuple[ProviderDeclaration, ...] = EXTERNAL_PROVIDERS,
) -> tuple[ProviderDeclaration, ...]:
    """Validate all code declarations and resolve argv[0] to an absolute executable."""

    resolved: list[ProviderDeclaration] = []
    ids: set[str] = set()
    for declaration in declarations:
        if not _NAME.fullmatch(declaration.provider_id) or declaration.provider_id in ids:
            raise _config_error("tool_provider_invalid", provider_id=declaration.provider_id)
        ids.add(declaration.provider_id)
        if not isinstance(declaration.argv, tuple) or not declaration.argv or any(
            not isinstance(item, str) or not item or any(char in item for char in "\x00\r\n")
            for item in declaration.argv
        ) or not isinstance(declaration.cwd_from_repo_root, bool):
            raise _config_error("tool_provider_invalid", provider_id=declaration.provider_id)
        command = declaration.argv[0]
        if any(separator in command for separator in ("/", "\\")):
            path = Path(command)
            if not path.is_absolute():
                path = _REPO_ROOT / path
            executable = path.resolve()
            if not executable.is_file():
                raise _config_error("tool_provider_command_missing", provider_id=declaration.provider_id)
            executable_text = str(executable)
        else:
            found = shutil.which(command)
            if found is None:
                raise _config_error("tool_provider_command_missing", provider_id=declaration.provider_id)
            executable_text = str(Path(found).resolve())
        resolved.append(ProviderDeclaration(
            declaration.provider_id,
            (executable_text, *declaration.argv[1:]),
            declaration.cwd_from_repo_root,
        ))
    return tuple(resolved)


def external_tool_defs(
    admissions: tuple[ExternalToolAdmission, ...] = EXTERNAL_TOOL_ADMISSIONS,
) -> tuple[ToolDef, ...]:
    """Validate admissions and convert them to ordinary local ToolDef records."""

    result: list[ToolDef] = []
    canonical_names: set[str] = set()
    raw_names: set[tuple[str, str]] = set()
    for item in admissions:
        canonical = f"{item.provider_id}.{item.alias}"
        if not _NAME.fullmatch(item.provider_id) or not _NAME.fullmatch(item.alias):
            raise _config_error("external_tool_declaration_invalid")
        if canonical in canonical_names:
            raise _config_error("external_tool_name_conflict")
        canonical_names.add(canonical)
        raw_key = (item.provider_id, item.raw_name)
        if (
            raw_key in raw_names
            or not item.raw_name
            or len(item.raw_name) > 128
            or any(unicodedata.category(char).startswith("C") for char in item.raw_name)
        ):
            raise _config_error("external_tool_declaration_invalid")
        raw_names.add(raw_key)
        if item.risk_level not in RISK_LEVELS or not item.risk_level:
            raise _config_error("external_tool_declaration_invalid")
        if (
            not isinstance(item.description, str)
            or not item.description.strip()
            or any(unicodedata.category(char).startswith("C") for char in item.description)
        ):
            raise _config_error("external_tool_declaration_invalid")
        if item.side_effect_class != "read_only":
            reason = (
                "external_side_effect_not_supported"
                if item.side_effect_class
                else "external_tool_declaration_invalid"
            )
            raise _config_error(reason)
        if item.approval_profile not in APPROVAL_PROFILES:
            raise _config_error("external_tool_declaration_invalid")
        properties = _valid_external_schema(item.parameters)
        required = item.parameters.get("required")
        property_names = set(properties)
        supplied = set(item.supply_by_echo)
        if (
            not item.supply_by_echo
            or not supplied.issubset(property_names)
            or not property_names.issubset(set(required) if isinstance(required, list) else set())
            or not property_names.issubset(supplied)
            or not supplied.issubset(set(item.param_instance_checks))
        ):
            raise _config_error("external_tool_declaration_invalid")
        result.append(ToolDef(
            name=canonical,
            description=item.description,
            parameters={
                "type": "object",
                "properties": {
                    name: dict(value)
                    for name, value in properties.items()
                    if isinstance(name, str) and isinstance(value, Mapping)
                },
                "required": list(required) if isinstance(required, list) else [],
            },
            risk_level=item.risk_level,
            approval_profile=item.approval_profile,
            supply_by_echo=item.supply_by_echo,
            audit_redact_all_params=True,
            param_instance_checks=item.param_instance_checks,
            egress=True,
        ))
    return tuple(result)


def validate_provider_declarations(
    providers: tuple[ProviderDeclaration, ...],
    admissions: tuple[ExternalToolAdmission, ...],
    capabilities: tuple[ToolCapability, ...],
    *,
    builtin_names: set[str],
) -> tuple[ToolDef, ...]:
    resolved = resolve_provider_declarations(providers)
    provider_ids = {item.provider_id for item in resolved}
    if any(item.provider_id not in provider_ids for item in admissions):
        raise _config_error("external_tool_declaration_invalid")
    tools = external_tool_defs(admissions)
    names = {tool.name for tool in tools}
    if names & builtin_names:
        raise _config_error("external_tool_name_conflict")
    validate_capability_declarations(capabilities, tools)
    validate_active_capabilities(capabilities, tools)
    return tools


def _valid_external_schema(schema: object) -> Mapping[str, object]:
    if not isinstance(schema, Mapping) or set(schema) != {"type", "properties", "required"}:
        raise _config_error("external_tool_declaration_invalid")
    properties = schema.get("properties")
    required = schema.get("required")
    if schema.get("type") != "object" or not isinstance(properties, Mapping) or not isinstance(required, list):
        raise _config_error("external_tool_declaration_invalid")
    if (
        len(required) != len(set(required))
        or any(not isinstance(name, str) for name in required)
        or set(required) != set(properties)
    ):
        raise _config_error("external_tool_declaration_invalid")
    for name, value in properties.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(value, Mapping)
            or dict(value) != {"type": "string"}
        ):
            raise _config_error("external_tool_declaration_invalid")
    return properties


def _config_error(reason: str, **details: object) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=f"Invalid external tool provider configuration: {reason}",
        user_message="工具来源配置有误。",
        details={"reason": reason, **details},
    )
