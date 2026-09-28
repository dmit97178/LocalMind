"""Production configuration routes weather through an injectable provider."""

import tomllib
from pathlib import Path

import pytest

from src.core.schemas import LocalMindError
from src.main import create_tool_backend


def test_default_configuration_bootstraps_with_weather_capability() -> None:
    from src.main import bootstrap
    from src.models.mock_backend import MockModelBackend

    config = Path(__file__).parents[1] / "config" / "default.toml"
    app = bootstrap(str(config), model_backend_override=MockModelBackend())

    names = [item.capability_id for item in app.executor.tool_backend.list_capabilities()]
    assert names == [
        "weather.current", "files.read", "files.info", "files.write", "files.search", "system.time",
        "text.format",
    ]
    assert "system.echo" not in [tool.name for tool in app.executor.tool_backend.list_tools()]


def test_delivery_configs_exclude_test_only_echo_tool() -> None:
    root = Path(__file__).parents[1] / "config"
    test_only = {"p6_legacy.example.toml"}
    for path in root.glob("*.toml"):
        if path.name in test_only:
            continue
        with path.open("rb") as stream:
            config = tomllib.load(stream)
        whitelist = config.get("tool_backend", {}).get("config", {}).get("whitelist", [])
        assert "system.echo" not in whitelist


class FixedWeatherProvider:
    def current_weather(self, location: str) -> dict:
        return {"location": location, "source": "test"}


def test_factory_exposes_weather_only_when_provider_is_configured() -> None:
    config = {
        "tool_backend": {"type": "builtin_only", "config": {"whitelist": ["weather.current"]}},
        "capability_routing": {"enabled": True},
        "tools": {"weather": {"provider": "open_meteo"}},
    }
    backend = create_tool_backend(config, weather_provider_override=FixedWeatherProvider())

    assert [tool.name for tool in backend.list_tools()] == ["weather.current"]
    assert [item.capability_id for item in backend.list_capabilities()] == [
        "weather.current", "files.read", "files.info", "files.write", "files.search", "system.time",
        "text.format",
    ]
    assert backend.execute("weather.current", {"location": "南京"}).value == {
        "location": "南京", "source": "test"
    }


def test_weather_declaration_remains_visible_when_provider_is_disabled() -> None:
    config = {
        "tool_backend": {"type": "builtin_only", "config": {"whitelist": ["weather.current"]}},
        "capability_routing": {"enabled": True},
        "tools": {"weather": {"provider": "none"}},
    }

    backend = create_tool_backend(config)

    assert backend.list_tools() == []
    assert [item.capability_id for item in backend.list_capabilities()] == [
        "weather.current", "files.read", "files.info", "files.write", "files.search", "system.time",
        "text.format",
    ]


def test_factory_rejects_unknown_weather_provider() -> None:
    config = {
        "tool_backend": {"type": "builtin_only", "config": {"whitelist": []}},
        "capability_routing": {"enabled": True},
        "tools": {"weather": {"provider": "untrusted"}},
    }
    with pytest.raises(LocalMindError) as error:
        create_tool_backend(config)
    assert error.value.code == "CONFIG_ERROR"


def test_factory_rejects_non_table_weather_connection_as_config_error() -> None:
    config = {
        "tool_backend": {"type": "builtin_only", "config": {"whitelist": []}},
        "capability_routing": {"enabled": True},
        "tools": {"weather": {"provider": "open_meteo", "connection": "bad"}},
    }
    with pytest.raises(LocalMindError) as error:
        create_tool_backend(config)
    assert error.value.code == "CONFIG_ERROR"


def test_factory_rejects_non_string_weather_provider_as_config_error() -> None:
    config = {
        "tool_backend": {"type": "builtin_only", "config": {"whitelist": []}},
        "capability_routing": {"enabled": True},
        "tools": {"weather": {"provider": ["open_meteo"]}},
    }
    with pytest.raises(LocalMindError) as error:
        create_tool_backend(config)
    assert error.value.code == "CONFIG_ERROR"
