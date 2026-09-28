"""Capability declarations and deterministic membership checks."""

import inspect

import pytest

from src.core.capabilities import capability_relevance, validate_active_capabilities
from src.core.intent_resolver import _build_prompt
from src.core.schemas import LocalMindError, MinimalContext, ToolCapability, ToolDef
from src.tools.capabilities import validate_capabilities


def _tool(name: str, *, echo: tuple[str, ...] = ()) -> ToolDef:
    return ToolDef(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        supply_by_echo=echo,
    )


def test_relevance_only_uses_selected_capability_membership() -> None:
    catalog = (ToolCapability("files.read", "Read files", ("file.read",)),)

    assert capability_relevance("files.read", "file.read", catalog) == "relevant"
    assert capability_relevance("files.read", "file.write", catalog) == "irrelevant"
    assert capability_relevance("unknown", "file.read", catalog) == "unrouted"
    assert capability_relevance(None, "file.read", catalog) == "unrouted"


def test_relevance_is_membership_only_and_does_not_read_model_claims() -> None:
    source = inspect.getsource(capability_relevance)
    assert "intent_type" not in source
    assert "tool_intent" not in source
    assert "reply" not in source
    catalog = (ToolCapability("files.read", "Read files", ("file.read",)),)
    for _intent_type in ("action", "question"):
        for _tool_intent in ("local_action", "none"):
            assert capability_relevance("files.read", "file.write", catalog) == "irrelevant"


def test_active_tool_without_capability_is_configuration_error() -> None:
    with pytest.raises(LocalMindError) as error:
        validate_capabilities((ToolCapability("files.read", "Read", ("file.read",)),),
                              (_tool("file.read"), _tool("file.list_dir")), enabled=True)

    assert error.value.code == "CONFIG_ERROR"
    assert error.value.details["reason"] == "capability_coverage_missing"


def test_side_effect_tool_cannot_share_capability_or_accept_echo_supply() -> None:
    merged = (ToolCapability("files.read", "Read", ("file.read", "file.write")),)
    with pytest.raises(LocalMindError) as error:
        validate_capabilities(merged, (_tool("file.read"), _tool("file.write")), enabled=True)
    assert error.value.details["reason"] == "capability_declaration_invalid"

    isolated = (ToolCapability("files.write", "Write", ("file.write",)),)
    with pytest.raises(LocalMindError) as error:
        validate_capabilities(isolated, (_tool("file.write", echo=("value",)),), enabled=True)
    assert error.value.details["reason"] == "capability_declaration_invalid"


def test_disabled_routing_does_not_require_active_coverage() -> None:
    assert validate_capabilities((), (_tool("file.read"),), enabled=False) == ()


def test_disabled_routing_still_rejects_invalid_declarations() -> None:
    duplicated = (
        ToolCapability("files.read", "Read", ("file.read",)),
        ToolCapability("files.read", "Read again", ("file.read",)),
    )
    with pytest.raises(LocalMindError) as error:
        validate_capabilities(duplicated, (_tool("file.read"),), enabled=False)
    assert error.value.details["reason"] == "capability_declaration_invalid"


def test_registered_but_inactive_tool_can_remain_in_declaration() -> None:
    declarations = (ToolCapability("files.read", "Read", ("file.read", "file.list_dir")),)
    active = (_tool("file.read"),)
    registered = (*active, _tool("file.list_dir"))

    assert validate_capabilities(
        declarations, active, enabled=True, registered_tools=registered,
    ) == declarations


def test_active_catalog_count_and_utf8_byte_boundaries() -> None:
    tools = tuple(_tool(f"tool.{index}") for index in range(8))
    base = tuple(
        ToolCapability(f"cap.{index}", "天" * 72, (f"tool.{index}",))
        for index in range(8)
    )
    below_limit = (ToolCapability("cap.0", "天" * 74, ("tool.0",)), *base[1:])
    assert validate_active_capabilities(below_limit, tools) == below_limit
    exact_limit = (ToolCapability("cap.0", "天" * 74 + "a", ("tool.0",)), *base[1:])
    assert validate_active_capabilities(exact_limit, tools) == exact_limit

    oversized = (ToolCapability("cap.0", "天" * 74 + "ab", ("tool.0",)), *base[1:])
    with pytest.raises(LocalMindError) as error:
        validate_active_capabilities(oversized, tools)
    assert error.value.details == {"reason": "capability_catalog_too_large", "catalog_bytes": 2049}

    ninth = (*base, ToolCapability("cap.8", "Extra", ("tool.8",)))
    with pytest.raises(LocalMindError) as error:
        validate_active_capabilities(ninth, (*tools, _tool("tool.8")))
    assert error.value.details == {"reason": "capability_catalog_too_large", "capability_count": 9}


def test_capability_prompt_preserves_declaration_order_without_set_iteration() -> None:
    capabilities = (
        ToolCapability("z.second", "Second", ("tool.z",)),
        ToolCapability("a.first", "First", ("tool.a",)),
    )
    context = MinimalContext("system", current_input="question", capabilities=capabilities)

    prompt = _build_prompt(context, [], None, 1, None)

    assert prompt.index("z.second: Second") < prompt.index("a.first: First")
    assert "set(" not in inspect.getsource(_build_prompt)
