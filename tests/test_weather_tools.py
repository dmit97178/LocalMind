from pathlib import Path

import pytest

from src.core.schemas import ToolContext, ToolError
from src.tools.weather_tools import make_weather_tool


class Provider:
    def __init__(self):
        self.locations = []

    def current_weather(self, location):
        self.locations.append(location)
        return {"location": location}


def test_factory_declares_only_location_and_no_preflight():
    provider = Provider()
    tool = make_weather_tool(provider)
    assert tool.definition.name == "weather.current"
    assert tool.definition.parameters == {
        "type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]
    }
    assert tool.definition.risk_level == "normal"
    assert tool.definition.approval_profile == "standard"
    assert tool.definition.audit_redact_all_params is True
    assert tool.definition.supply_by_echo == ("location",)
    assert tuple(tool.definition.param_instance_checks) == ("location",)
    assert tool.definition.param_instance_checks["location"].reject_whole_input is True
    assert tool.preflight is None
    assert tool.handler({"location": "南京"}, ToolContext(Path.cwd(), tool.definition)) == {"location": "南京"}
    assert provider.locations == ["南京"]


def test_core_and_safety_do_not_import_weather_provider():
    root = Path(__file__).parents[1] / "src"
    for layer in ("core", "safety"):
        for path in (root / layer).glob("*.py"):
            assert "src.adapters.weather_provider" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("location", ["", "x" * 65, "Nanjing\n", "a/b", "a?b", "a&b", "a#b", "a=b", "a:b", "a@b", "a%b", "sk-abcdefghijklmnopqrstuvwxyz1234"])
def test_invalid_location_is_rejected_before_provider_call(location):
    provider = Provider()
    tool = make_weather_tool(provider)
    with pytest.raises(ToolError) as caught:
        tool.handler({"location": location}, ToolContext(Path.cwd(), tool.definition))
    assert caught.value.code == "TOOL_EXEC_ERROR"
    assert caught.value.details["reason"] == "location_rejected"
    assert caught.value.recoverable
    assert provider.locations == []
