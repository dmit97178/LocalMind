from __future__ import annotations

import sys
from dataclasses import replace

import pytest

from src.core.schemas import LocalMindError
from src.tools.provider_declarations import (
    EXTERNAL_CAPABILITIES,
    EXTERNAL_PROVIDERS,
    EXTERNAL_TOOL_ADMISSIONS,
    external_tool_defs,
    validate_provider_configuration,
    validate_provider_declarations,
)


def test_builtin_external_declarations_are_valid_and_locally_authoritative() -> None:
    tools = validate_provider_declarations(
        EXTERNAL_PROVIDERS,
        EXTERNAL_TOOL_ADMISSIONS,
        EXTERNAL_CAPABILITIES,
        builtin_names={"file.read"},
    )
    assert [tool.name for tool in tools] == ["demo.json_format"]
    assert tools[0].egress is True
    assert tools[0].audit_redact_all_params is True
    assert tools[0].description == "格式化用户提供的 JSON 文本"


def test_provider_config_rejects_unknown_keys_and_unknown_provider() -> None:
    with pytest.raises(LocalMindError) as exc_info:
        validate_provider_configuration(
            {"demo": {"enabled": True, "command": [sys.executable]}},
            capability_routing_enabled=True,
        )
    assert exc_info.value.details["reason"] == "tool_provider_invalid"

    with pytest.raises(LocalMindError) as exc_info:
        validate_provider_configuration(
            {"unknown": {"enabled": True}}, capability_routing_enabled=True,
        )
    assert exc_info.value.details["reason"] == "tool_provider_unknown"


def test_enabled_provider_requires_capability_routing_and_valid_timeouts() -> None:
    with pytest.raises(LocalMindError) as exc_info:
        validate_provider_configuration(
            {"demo": {"enabled": True}}, capability_routing_enabled=False,
        )
    assert exc_info.value.details["reason"] == "tool_providers_require_capability_routing"

    with pytest.raises(LocalMindError) as exc_info:
        validate_provider_configuration(
            {"demo": {"enabled": True, "call_timeout_ms": True}},
            capability_routing_enabled=True,
        )
    assert exc_info.value.details["reason"] == "tool_provider_invalid"


def test_external_tool_declaration_rejects_side_effect_and_bad_schema() -> None:
    unsafe = replace(EXTERNAL_TOOL_ADMISSIONS[0], side_effect_class="local_side_effect")
    with pytest.raises(LocalMindError) as exc_info:
        external_tool_defs((unsafe,))
    assert exc_info.value.details["reason"] == "external_side_effect_not_supported"

    bad_schema = replace(
        EXTERNAL_TOOL_ADMISSIONS[0],
        parameters={
            "type": "object",
            "properties": {"text": {"type": "integer"}},
            "required": ["text"],
        },
    )
    with pytest.raises(LocalMindError) as exc_info:
        external_tool_defs((bad_schema,))
    assert exc_info.value.details["reason"] == "external_tool_declaration_invalid"
