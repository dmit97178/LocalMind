"""Builtin capability declarations and registration checks."""

from collections.abc import Sequence

from src.core.capabilities import validate_active_capabilities, validate_capability_declarations
from src.core.schemas import LocalMindError, ToolCapability, ToolDef

LOCAL_SIDE_EFFECT_TOOLS = frozenset({"file.write"})
BUILTIN_CAPABILITIES = (
    ToolCapability("weather.current", "查询指定地点的当前天气与当日预报（需联网）", ("weather.current",)),
    ToolCapability(
        "files.read",
        "读取或列出工作区内的本地文件",
        ("file.read", "file.list_dir", "document.read"),
    ),
    ToolCapability("files.info", "查看工作区内文件或目录的属性", ("file.stat",)),
    ToolCapability("files.write", "在工作区内新建或覆盖一个文本文件", ("file.write",)),
    ToolCapability("files.search", "在工作区内按文件名或内容搜索", ("file.search",)),
    ToolCapability("system.time", "获取当前本地时间", ("system.get_time",)),
)


def _invalid(reason: str, **details: object) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=f"Invalid capability catalog: {reason}",
        user_message="工具能力配置有误。",
        details={"reason": reason, **details},
    )


def validate_capabilities(
    declarations: Sequence[ToolCapability],
    active_tools: Sequence[ToolDef],
    *,
    enabled: bool,
    registered_tools: Sequence[ToolDef] | None = None,
) -> tuple[ToolCapability, ...]:
    registered = {tool.name: tool for tool in registered_tools or active_tools}
    declarations = validate_capability_declarations(declarations, tuple(registered.values()))
    for capability in declarations:
        if any(name in LOCAL_SIDE_EFFECT_TOOLS for name in capability.tools) and len(capability.tools) != 1:
            raise _invalid("capability_declaration_invalid")
    for tool in registered.values():
        if tool.result_delivery not in {"deterministic", "model_summary"}:
            raise _invalid("result_delivery_invalid")
        if tool.result_delivery == "model_summary" and (
            tool.name in LOCAL_SIDE_EFFECT_TOOLS or tool.egress
        ):
            raise _invalid("result_delivery_invalid")
        required = tool.parameters.get("required", [])
        properties = tool.parameters.get("properties", {})
        if any(name not in required or name not in properties for name in tool.supply_by_echo):
            raise _invalid("capability_declaration_invalid")
        if tool.name in LOCAL_SIDE_EFFECT_TOOLS and tool.supply_by_echo:
            raise _invalid("capability_declaration_invalid")
        if tool.egress:
            property_names = set(properties)
            supplied = set(tool.supply_by_echo)
            checked = set(tool.param_instance_checks)
            if (
                not property_names.issubset(supplied)
                or not supplied.issubset(checked)
                or not tool.audit_redact_all_params
            ):
                raise _invalid("egress_contract_invalid")
    if not enabled:
        return ()
    return validate_active_capabilities(declarations, active_tools)
