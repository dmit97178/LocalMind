"""Versioned P6b scenario definitions and deterministic variant selection."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from src.core.schemas import LocalMindError

_GROUPS = frozenset({"g0_basic", "g1_progressive", "g2_value", "g3_autonomy", "g4_capability"})
_STEP_KINDS = frozenset({"user", "slash"})
_SCENARIO_KEYS = frozenset(
    {
        "id",
        "title",
        "group",
        "value_ab",
        "rounds_ab",
        "variants",
        "cloud_fault",
        "step_timeout_seconds",
    }
)
_STEP_KEYS = frozenset(
    {"kind", "text", "prelude", "when_variant", "when_state", "on_unmet", "cloud_ask", "expect"}
)
_RUN_KEYS = frozenset({"id", "steps"})
_SETUP_KINDS = frozenset({"episode", "project", "workspace_file", "identity"})
_VARIANTS = frozenset(
    {
        "base",
        "round1",
        "round4",
        "local_only",
        "cloud_assisted",
        "cloud_auto",
        "embedding_none",
        "weather_on",
        "weather_off",
        "mcp_on",
        "mcp_off",
        "docs_on",
        "docs_off",
    }
)
_STATES = frozenset({"awaiting_cloud_authorization"})
_EXPECT_KEYS = frozenset(
    {
        "rounds_min",
        "rounds_max",
        "action_any",
        "action_none",
        "confirmation_required",
        "tool_any",
        "tool_none",
        "cloud_any",
        "local_reintegrate",
        "retrieval_hits_min",
        "degradation_any",
        "reference_guard_any",
        "capability_any",
        "output_contains",
        "output_not_contains",
        "result_delivery_any",
    }
)
_SCENARIO_ID_RE = re.compile(r"^S\d{2}[a-z_]*$")


@dataclass(frozen=True)
class ScenarioStep:
    kind: str
    text: str
    prelude: bool = False
    when_variant: str = ""
    when_state: str = ""
    on_unmet: str = "fail"
    cloud_ask: bool = False
    expect: dict[str, object] | None = None


@dataclass(frozen=True)
class ScenarioRun:
    id: str
    steps: tuple[ScenarioStep, ...]


@dataclass(frozen=True)
class ScenarioSetup:
    kind: str
    values: dict[str, object]


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    group: str
    value_ab: bool
    rounds_ab: bool
    step_timeout_seconds: int
    steps: tuple[ScenarioStep, ...]
    runs: tuple[ScenarioRun, ...] = ()
    setup: tuple[ScenarioSetup, ...] = ()
    variants: tuple[str, ...] = ()
    cloud_fault: str = ""


def load_scenario(path: str | Path) -> Scenario:
    """Load one versioned scenario and reject unknown or invalid structure."""

    try:
        with Path(path).open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise _config_error(f"unable to load scenario: {exc}") from exc
    scenario_data = raw.get("scenario")
    steps_data = raw.get("steps")
    runs_data = raw.get("run")
    if not isinstance(scenario_data, dict):
        raise _config_error("scenario requires a [scenario] table")
    unknown = set(scenario_data) - _SCENARIO_KEYS
    if unknown:
        raise _config_error(f"unknown scenario keys: {sorted(unknown)}")
    if set(raw) - {"scenario", "setup", "steps", "run"}:
        raise _config_error("unknown scenario document tables")
    scenario_id = scenario_data.get("id")
    title = scenario_data.get("title")
    group = scenario_data.get("group")
    if not all(isinstance(value, str) and value.strip() for value in (scenario_id, title, group)):
        raise _config_error("scenario id, title, and group are required strings")
    scenario_id = cast(str, scenario_id)
    title = cast(str, title)
    group = cast(str, group)
    if _SCENARIO_ID_RE.fullmatch(scenario_id) is None:
        raise _config_error("scenario id is invalid")
    if group not in _GROUPS:
        raise _config_error("scenario group is invalid")
    value_ab = _bool(scenario_data, "value_ab", False)
    rounds_ab = _bool(scenario_data, "rounds_ab", False)
    timeout = scenario_data.get("step_timeout_seconds", 240)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        raise _config_error("step_timeout_seconds must be a positive integer")
    if group == "g2_value" and not value_ab:
        raise _config_error("g2_value scenarios require value_ab=true")
    if value_ab and rounds_ab:
        raise _config_error("scenario cannot enable both value_ab and rounds_ab")
    setup = _parse_setup(raw.get("setup"))
    explicit_variants = _parse_variants(scenario_data.get("variants"), value_ab, rounds_ab)
    cloud_fault = _parse_cloud_fault(scenario_data.get("cloud_fault", ""), group)
    allowed_variants = (
        frozenset(explicit_variants)
        if explicit_variants
        else _variants_for_flags(value_ab, rounds_ab)
    )
    if steps_data is not None and runs_data is not None:
        raise _config_error("scenario cannot mix top-level [[steps]] with [[run]]")
    if isinstance(steps_data, list) and steps_data:
        steps = tuple(_parse_step(item, group, allowed_variants) for item in steps_data)
        return Scenario(
            scenario_id,
            title,
            group,
            value_ab,
            rounds_ab,
            timeout,
            steps,
            (),
            setup,
            explicit_variants,
            cloud_fault,
        )
    if isinstance(runs_data, list) and runs_data:
        runs = _parse_runs(runs_data, group, allowed_variants)
        return Scenario(
            scenario_id,
            title,
            group,
            value_ab,
            rounds_ab,
            timeout,
            (),
            runs,
            setup,
            explicit_variants,
            cloud_fault,
        )
    raise _config_error("scenario requires non-empty [[steps]] or [[run]]")


def variants_for(scenario: Scenario, requested: str = "auto") -> tuple[str, ...]:
    """Return only variants permitted by the scenario's declared experiment type."""

    if requested != "auto":
        allowed = scenario.variants or _variants_for_flags(scenario.value_ab, scenario.rounds_ab)
        if requested not in _VARIANTS or requested not in allowed:
            raise _config_error("requested variant is invalid for this scenario")
        return (requested,)
    if scenario.variants:
        return scenario.variants
    if scenario.value_ab:
        return ("local_only", "cloud_assisted")
    if scenario.rounds_ab:
        return ("round1", "round4")
    return ("base",)


def _parse_runs(
    raw_runs: list[object], group: str, allowed_variants: frozenset[str]
) -> tuple[ScenarioRun, ...]:
    runs: list[ScenarioRun] = []
    run_ids: set[str] = set()
    for raw_run in raw_runs:
        if not isinstance(raw_run, dict):
            raise _config_error("each [[run]] entry must be a table")
        unknown = set(raw_run) - _RUN_KEYS
        if unknown:
            raise _config_error(f"unknown run keys: {sorted(unknown)}")
        run_id = raw_run.get("id")
        steps_data = raw_run.get("steps")
        if not isinstance(run_id, str) or not run_id.strip() or run_id in run_ids:
            raise _config_error("each [[run]] requires a unique non-empty id")
        if not isinstance(steps_data, list) or not steps_data:
            raise _config_error("each [[run]] requires non-empty [[run.steps]]")
        run_ids.add(run_id)
        runs.append(
            ScenarioRun(
                run_id,
                tuple(_parse_step(item, group, allowed_variants) for item in steps_data),
            )
        )
    return tuple(runs)


def _parse_setup(raw_setup: object) -> tuple[ScenarioSetup, ...]:
    if raw_setup is None:
        return ()
    if not isinstance(raw_setup, list):
        raise _config_error("[[setup]] entries must be tables")
    setup: list[ScenarioSetup] = []
    for item in raw_setup:
        if not isinstance(item, dict):
            raise _config_error("each [[setup]] entry must be a table")
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in _SETUP_KINDS:
            raise _config_error("setup kind is invalid")
        _validate_setup(kind, item)
        setup.append(ScenarioSetup(kind, dict(item)))
    return tuple(setup)


def _parse_variants(raw: object, value_ab: bool, rounds_ab: bool) -> tuple[str, ...]:
    if raw is None:
        return ()
    if rounds_ab:
        raise _config_error("variants cannot be combined with rounds_ab")
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        raise _config_error("variants must be a non-empty string list")
    variants = tuple(raw)
    if len(set(variants)) != len(variants) or any(item not in _VARIANTS for item in variants):
        raise _config_error("variants contains an invalid value")
    derived = frozenset({"local_only", "cloud_assisted"}) if value_ab else frozenset()
    if derived and not derived.issubset(variants):
        raise _config_error("variants must include every variant implied by experiment flags")
    return variants


def _parse_cloud_fault(raw: object, group: str) -> str:
    if not isinstance(raw, str) or raw not in {"", "timeout"}:
        raise _config_error("cloud_fault is invalid")
    if raw and group != "g3_autonomy":
        raise _config_error("cloud_fault is only valid for g3_autonomy")
    return raw


def _validate_setup(kind: str, values: dict[str, object]) -> None:
    required: dict[str, tuple[str, ...]] = {
        "episode": ("session_id", "text", "metadata"),
        "project": ("project_id", "title", "goal"),
        "workspace_file": ("path", "content"),
        "identity": ("passphrase",),
    }
    if any(key not in values for key in required[kind]):
        raise _config_error(f"setup.{kind} is missing required fields")
    if kind == "episode":
        metadata = values["metadata"]
        if not isinstance(metadata, dict) or not isinstance(metadata.get("topic"), str):
            raise _config_error("episode setup requires metadata.topic")
    for key in required[kind]:
        if key == "metadata":
            continue
        value = values[key]
        if not isinstance(value, str) or not value.strip():
            raise _config_error(f"setup.{kind}.{key} must be a non-empty string")


def _parse_step(raw: object, group: str, allowed_variants: frozenset[str]) -> ScenarioStep:
    if not isinstance(raw, dict):
        raise _config_error("each [[steps]] entry must be a table")
    unknown = set(raw) - _STEP_KEYS
    if unknown:
        raise _config_error(f"unknown step keys: {sorted(unknown)}")
    kind = raw.get("kind")
    text = raw.get("text")
    if kind not in _STEP_KINDS or not isinstance(text, str) or not text.strip():
        raise _config_error("step requires kind=user|slash and non-empty text")
    cloud_ask = _bool(raw, "cloud_ask", False)
    if cloud_ask and (kind != "user" or group != "g2_value"):
        raise _config_error("cloud_ask is only valid for g2_value user steps")
    prelude = _bool(raw, "prelude", False)
    when_variant = _string(raw, "when_variant")
    when_state = _string(raw, "when_state")
    on_unmet = _string(raw, "on_unmet") or "fail"
    if when_variant and when_variant not in allowed_variants:
        raise _config_error("when_variant is invalid for this scenario")
    if when_state and when_state not in _STATES:
        raise _config_error("when_state is invalid")
    if on_unmet not in {"fail", "skip"} or ("on_unmet" in raw and not when_state):
        raise _config_error("on_unmet is only valid as fail|skip with when_state")
    expect = _parse_expect(raw.get("expect"), kind, prelude)
    return ScenarioStep(
        kind=kind,
        text=text,
        prelude=prelude,
        when_variant=when_variant,
        when_state=when_state,
        on_unmet=on_unmet,
        cloud_ask=cloud_ask,
        expect=expect,
    )


def _parse_expect(raw: object, kind: str, prelude: bool) -> dict[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _config_error("step expect must be a table")
    if prelude:
        raise _config_error("prelude steps cannot define expect")
    unknown = set(raw) - _EXPECT_KEYS
    if unknown:
        raise _config_error(f"unknown expect keys: {sorted(unknown)}")
    for key in ("rounds_min", "rounds_max", "retrieval_hits_min"):
        if key in raw and (
            not isinstance(raw[key], int) or isinstance(raw[key], bool) or raw[key] < 0
        ):
            raise _config_error(f"expect.{key} must be a non-negative integer")
    minimum = raw.get("rounds_min")
    maximum = raw.get("rounds_max")
    if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
        raise _config_error("expect.rounds_min cannot exceed rounds_max")
    for key in (
        "action_any", "action_none", "tool_any", "result_delivery_any",
        "output_not_contains",
    ):
        if key in raw and (
            not isinstance(raw[key], list)
            or not raw[key]
            or not all(isinstance(item, str) and item for item in raw[key])
        ):
            raise _config_error(f"expect.{key} must be a non-empty string list")
    if "capability_any" in raw and (
        not isinstance(raw["capability_any"], list)
        or not raw["capability_any"]
        or any(
            not isinstance(item, str)
            or item not in {"routed", "none", "unavailable", "unrecognized", "absent"}
            for item in raw["capability_any"]
        )
    ):
        raise _config_error("expect.capability_any contains an invalid value")
    for key in (
        "confirmation_required",
        "tool_none",
        "cloud_any",
        "local_reintegrate",
        "degradation_any",
        "reference_guard_any",
    ):
        if key in raw and not isinstance(raw[key], bool):
            raise _config_error(f"expect.{key} must be a boolean")
    if "output_contains" in raw:
        if kind != "slash" or not isinstance(raw["output_contains"], str):
            raise _config_error("expect.output_contains is only valid for slash steps")
    return dict(raw)


def _variants_for_flags(value_ab: bool, rounds_ab: bool) -> frozenset[str]:
    if value_ab:
        return frozenset({"local_only", "cloud_assisted"})
    if rounds_ab:
        return frozenset({"round1", "round4"})
    return frozenset({"base", "embedding_none"})


def _bool(mapping: dict[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise _config_error(f"{key} must be a boolean")
    return value


def _string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key, "")
    if not isinstance(value, str):
        raise _config_error(f"{key} must be a string")
    return value


def _config_error(message: str) -> LocalMindError:
    return LocalMindError("CONFIG_ERROR", message, "评估场景配置无效。", recoverable=False)
