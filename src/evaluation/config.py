"""Derive isolated P6b configurations from the versioned evaluation template."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def render_instance_config(
    template_path: str | Path,
    instance_dir: str | Path,
    variant: str,
    *,
    cloud_fault: str = "",
    cloud_enabled: bool | None = None,
    capability_off: bool = False,
) -> Path:
    """Render one absolute-path configuration for an isolated scenario instance."""

    template = Path(template_path)
    instance = Path(instance_dir).resolve()
    text = template.read_text(encoding="utf-8")
    source = tomllib.loads(text)
    has_routing = isinstance(source.get("capability_routing"), dict)
    has_weather = isinstance(_section(source.get("tools"), "").get("weather"), dict)
    if (has_routing or capability_off) and "enabled = true # {{CAPABILITY_ROUTING_ENABLED}}" not in text:
        raise ValueError("evaluation template is missing the capability routing switch")
    if (has_weather or variant in {"weather_on", "weather_off"}) and "{{WEATHER_PROVIDER}}" not in text:
        raise ValueError("evaluation template is missing the weather provider placeholder")
    if variant in {"docs_on", "docs_off"} and "{{DOC_TOOLS}}" not in text:
        raise ValueError("evaluation template is missing the doc tools placeholder")
    text = text.replace("{{INSTANCE_DIR}}", instance.as_posix())
    text = text.replace("{{EMBEDDING_TYPE}}", "none" if variant == "embedding_none" else "ollama")
    text = text.replace(
        "enabled = true # {{CAPABILITY_ROUTING_ENABLED}}",
        f"enabled = {'false' if capability_off else 'true'}",
    )
    text = text.replace("{{WEATHER_PROVIDER}}", "open_meteo" if variant == "weather_on" else "none")
    text = text.replace(
        '] # {{DOC_TOOLS}}',
        ', "document.read", "file.search"]' if variant == "docs_on" else "]",
    )
    if variant == "mcp_on":
        text += (
            "\n[tool_providers.demo]\n"
            "enabled = true\n"
            "handshake_timeout_ms = 5000\n"
            "call_timeout_ms = 10000\n"
        )
    if variant == "round1":
        text = text.replace("intent_max_rounds = 4", "intent_max_rounds = 1")
    desired_cloud = cloud_enabled
    if desired_cloud is None and variant == "local_only":
        desired_cloud = False
    elif desired_cloud is None and variant == "cloud_assisted":
        desired_cloud = True
    if desired_cloud is not None:
        text = re.sub(
            r"(?m)(^\[cloud_advisory\]\r?\n(?:[^\[]*?\r?\n)?enabled\s*=\s*)(?:true|false)",
            lambda match: match.group(1) + str(desired_cloud).lower(),
            text,
            count=1,
        )
    if cloud_fault == "timeout":
        text = text.replace("request_timeout_seconds = 60", "request_timeout_seconds = 0.001")
    if "{{" in text:
        raise ValueError("evaluation template has unresolved placeholders")
    config = tomllib.loads(text)
    expected_provider = "open_meteo" if variant == "weather_on" else "none"
    if has_routing and _section(config.get("capability_routing"), "").get("enabled") is not (not capability_off):
        raise ValueError("rendered capability routing state does not match the requested variant")
    if has_weather and _section(_section(config.get("tools"), "").get("weather"), "").get("provider") != expected_provider:
        raise ValueError("rendered weather provider does not match the requested variant")
    if variant in {"docs_on", "docs_off"}:
        whitelist = _section(config.get("tool_backend"), "config").get("whitelist", ())
        docs = {"document.read", "file.search"}
        actual = docs.intersection(whitelist if isinstance(whitelist, list) else ())
        expected = docs if variant == "docs_on" else set()
        if actual != expected:
            raise ValueError("rendered doc tool whitelist does not match the requested variant")
    instance.mkdir(parents=True, exist_ok=True)
    config_path = instance / "config.toml"
    config_path.write_text(text, encoding="utf-8", newline="\n")
    return config_path


def config_snapshot(path: str | Path) -> dict[str, object]:
    """Return an allowlisted, credential-free record of evaluation settings."""

    with Path(path).open("rb") as stream:
        config = tomllib.load(stream)
    model = _section(config, "model_backend")
    memory = _section(config, "memory_backend")
    cloud = _section(config, "cloud_advisory")
    capability = _section(config, "capability_routing")
    tools = _section(config, "tools")
    execution = _section(config, "execution")
    embedding = _section(memory.get("config", {}), "embedding")
    cloud_provider = cloud.get("provider", cloud.get("backend", "noop"))
    providers = _section(config, "tool_providers")
    enabled_providers = tuple(sorted(
        provider_id
        for provider_id, settings in providers.items()
        if isinstance(settings, dict) and settings.get("enabled") is True
    ))
    return {
        "model_backend": {
            "type": model.get("type"),
            "model": _section(model.get("config", {}), "").get("model"),
        },
        "memory_backend": {"type": memory.get("type"), "embedding_type": embedding.get("type")},
        "cloud_advisory": {"enabled": cloud.get("enabled")},
        "cloud_provider": cloud_provider,
        "capability_routing": capability.get("enabled"),
        "weather_provider": _section(tools, "weather").get("provider"),
        "tool_providers": enabled_providers,
        "execution": {"intent_max_rounds": execution.get("intent_max_rounds")},
    }


def snapshots_are_fair(left: dict[str, object], right: dict[str, object]) -> bool:
    """Check that two run snapshots differ only in declared variant controls."""

    left_normalized = _without_variant_controls(left)
    right_normalized = _without_variant_controls(right)
    return left_normalized == right_normalized


def _without_variant_controls(snapshot: dict[str, object]) -> dict[str, object]:
    normalized = {
        key: dict(value) if isinstance(value, dict) else value for key, value in snapshot.items()
    }
    cloud = normalized.get("cloud_advisory")
    if isinstance(cloud, dict):
        cloud.pop("enabled", None)
    execution = normalized.get("execution")
    if isinstance(execution, dict):
        execution.pop("intent_max_rounds", None)
    memory = normalized.get("memory_backend")
    if isinstance(memory, dict):
        memory.pop("embedding_type", None)
    normalized.pop("weather_provider", None)
    return normalized


def _section(value: object, key: str) -> dict:
    if key == "":
        return dict(value) if isinstance(value, dict) else {}
    if isinstance(value, dict) and isinstance(value.get(key), dict):
        return dict(value[key])
    return {}
