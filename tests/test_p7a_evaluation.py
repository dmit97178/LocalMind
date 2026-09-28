"""P7a evaluation contracts at the scenario, config, and report boundaries."""

import tomllib
from pathlib import Path

import pytest

from src.core.schemas import LocalMindError
from src.evaluation.config import config_snapshot, render_instance_config
from src.evaluation.runner import _expectation_failures
from src.evaluation.scenarios import load_scenario, variants_for


def _scenario(tmp_path: Path, expect: str = 'capability_any = ["routed"]') -> Path:
    path = tmp_path / "S18.toml"
    path.write_text(
        '[scenario]\nid = "S18"\ntitle = "weather"\ngroup = "g4_capability"\n'
        'variants = ["weather_on", "weather_off"]\n'
        '[[steps]]\nkind = "user"\ntext = "Nanjing"\n[steps.expect]\n' + expect,
        encoding="utf-8",
    )
    return path


def test_g4_weather_variants_and_capability_expect(tmp_path: Path) -> None:
    scenario = load_scenario(_scenario(tmp_path))
    assert variants_for(scenario) == ("weather_on", "weather_off")
    assert variants_for(scenario, "weather_off") == ("weather_off",)


def test_checked_in_weather_scenarios_cover_unavailable_and_zero_round_followup() -> None:
    root = Path(__file__).parents[1] / "scenarios"
    unavailable = load_scenario(root / "S17_weather_unavailable.toml")
    followup = load_scenario(root / "S18_weather_followup.toml")

    assert variants_for(unavailable) == ("weather_off",)
    assert unavailable.steps[0].expect == {
        "capability_any": ["unavailable"],
        "action_any": ["PLAN_LOCAL"],
        "tool_none": True,
        "cloud_any": False,
    }
    assert variants_for(followup) == ("weather_on", "weather_off")
    supply = followup.steps[1]
    assert supply.when_variant == "weather_on"
    assert supply.expect is not None
    assert supply.expect["tool_any"] == ["weather.current"]
    assert supply.expect["rounds_min"] == supply.expect["rounds_max"] == 0


def test_capability_expect_rejects_values_outside_closed_set(tmp_path: Path) -> None:
    with pytest.raises(LocalMindError, match="capability_any"):
        load_scenario(_scenario(tmp_path, 'capability_any = ["maybe"]'))


def test_explicit_zero_rounds_and_capability_resolution_are_asserted() -> None:
    events = [
        {"type": "runtime_event", "event": {"stage": "intent_final", "data": {"capability_resolution": "routed"}}},
        {"type": "runtime_event", "event": {"stage": "turn_completed", "data": {"rounds_used": 0}}},
    ]
    assert _expectation_failures({"rounds_max": 0, "capability_any": ["routed"]}, "", events) == []
    assert _expectation_failures({"capability_any": ["unavailable"]}, "", events) == ["capability_any"]
    assert _expectation_failures({"capability_any": ["routed"]}, "", []) == ["capability_any"]


def test_weather_config_variants_and_capability_off_are_independent(tmp_path: Path) -> None:
    template = Path("config/eval.example.toml")
    on = render_instance_config(template, tmp_path / "on", "weather_on")
    off = render_instance_config(template, tmp_path / "off", "weather_off", capability_off=True)
    with on.open("rb") as stream:
        on_config = tomllib.load(stream)
    with off.open("rb") as stream:
        off_config = tomllib.load(stream)
    assert on_config["capability_routing"]["enabled"] is True
    assert on_config["tools"]["weather"]["provider"] == "open_meteo"
    assert off_config["capability_routing"]["enabled"] is False
    assert off_config["tools"]["weather"]["provider"] == "none"
    assert config_snapshot(on)["capability_routing"] is True
    assert config_snapshot(off)["capability_routing"] is False


def test_cloud_variant_does_not_change_capability_routing(tmp_path: Path) -> None:
    template = Path("config/eval.example.toml")
    config = render_instance_config(template, tmp_path / "local", "local_only")
    with config.open("rb") as stream:
        rendered = tomllib.load(stream)
    assert rendered["cloud_advisory"]["enabled"] is False
    assert rendered["capability_routing"]["enabled"] is True


def test_runner_accepts_g4_and_capability_off() -> None:
    from scripts.run_p6_scenarios import _parser

    args = _parser().parse_args(["--group", "g4", "--variant", "weather_on", "--capability-off"])
    assert args.group == "g4"
    assert args.capability_off is True


def test_cloud_precheck_can_read_the_p7a_template() -> None:
    from scripts.run_p6_scenarios import _cloud_key_present

    assert isinstance(_cloud_key_present(Path("config/eval.example.toml")), bool)


def test_report_keeps_capability_failure_and_mismatch_separate() -> None:
    from scripts.p6_report import _render

    def event(stage: str, **data: object) -> dict[str, object]:
        return {"type": "runtime_event", "event": {"stage": stage, "data": data}}

    row = {
        "run_id": "r17", "scenario_id": "S17", "variant": "weather_off", "repeat": 1,
        "capability_routing": True, "failed_steps": 0,
        "records": [
            event("intent_final", capability_id="none", capability_resolution="unavailable", tool_call_resolution="absent"),
            event("dispatch_decision", action="ASK_USER", proposal_gate_result="not_evaluated"),
            event("turn_completed", rounds_used=1, reply_provenance="unfulfilled"),
            event("intent_final", capability_id="files.read", capability_resolution="routed", tool_call_resolution="irrelevant_tool"),
            event("dispatch_decision", action="ASK_USER", proposal_gate_result="not_evaluated"),
            event("turn_completed", rounds_used=0, reply_provenance="unfulfilled"),
        ],
    }
    report = _render([row])
    assert "能力路由与诚实失败" in report
    assert "unavailable=1" in report
    assert "irrelevant_tool=1" in report
    assert "r17" in report
    assert "非干扰对照" in report
    assert "rounds_used=0" in report


def test_report_flags_capability_hard_row_violations() -> None:
    from scripts.p6_report import _render

    def event(stage: str, **data: object) -> dict[str, object]:
        return {"type": "runtime_event", "event": {"stage": stage, "data": data}}

    row = {
        "run_id": "bad", "scenario_id": "S17", "variant": "weather_off", "repeat": 1,
        "capability_routing": True,
        "records": [
            event("intent_final", capability_resolution="unavailable", tool_call_resolution="absent"),
            event("dispatch_decision", action="ASK_USER", proposal_gate_result="admitted_proposal"),
            event("tool_execution", tool_name="file.read", verdict="allowed"),
            event("turn_completed", rounds_used=1, reply_provenance="executed"),
        ],
    }
    report = _render([row])
    assert "bad" in report
    assert "capability_honest_failure" in report
    assert "违例" in report


def test_report_shows_each_hard_row_at_zero_and_flags_zero_round_disagreement() -> None:
    from scripts.p6_report import _render

    row = {
        "run_id": "zero", "scenario_id": "S18", "variant": "weather_on", "repeat": 1,
        "capability_routing": True,
        "records": [
            {"type": "runtime_event", "event": {"stage": "intent_final", "data": {
                "capability_resolution": "none", "tool_call_resolution": "absent"}}},
            {"type": "runtime_event", "event": {"stage": "turn_completed", "data": {
                "rounds_used": 0, "reply_provenance": "unfulfilled"}}},
        ],
    }
    report = _render([row])
    assert "capability_honest_failure=0" in report
    assert "capability_mismatch=0" in report
    assert "param_supply_turn=0" in report
    assert "zero_round_disagreement=1" in report


def test_report_pairs_capability_on_off_by_scenario_variant_repeat() -> None:
    from scripts.p6_report import _render

    rows = [
        {
            "run_id": state, "scenario_id": "S05", "variant": "base", "repeat": 2,
            "capability_routing": enabled, "actions": ["ASK_USER"], "rounds_used": [1],
            "risk_draft_results": {"normal": 1}, "proposal_gate_results": {},
            "tools": {"executed": 0}, "capability_resolution_results": resolutions,
        }
        for state, enabled, resolutions in (
            ("off", False, {}), ("on", True, {"none": 1}),
        )
    ]
    report = _render(rows)
    assert "S05 / base / r2" in report
    assert "关 action=ASK_USER=1" in report
    assert "开 action=ASK_USER=1" in report
    assert "capability=none=1" in report


def test_report_marks_weather_on_network_dependent_and_tool_turns_per_arm() -> None:
    from scripts.p6_report import _render

    rows = [
        {
            "run_id": state, "scenario_id": "S18", "variant": "weather_on", "repeat": 1,
            "capability_routing": enabled, "capability_resolution_results": resolutions,
            "records": [],
        }
        for state, enabled, resolutions in (
            ("off", False, {}), ("on", True, {"routed": 2}),
        )
    ]
    report = _render(rows)
    assert "weather_on: network-dependent" in report
    assert "tool_turns=2" in report


def test_report_classifies_rejected_outbound_parameter_as_capability_early_exit() -> None:
    from scripts.p6_report import _render

    def event(stage: str, **data: object) -> dict[str, object]:
        return {"type": "runtime_event", "event": {"stage": stage, "data": data}}

    report = _render([{
        "run_id": "source-rejected", "scenario_id": "S18", "variant": "weather_on",
        "repeat": 1, "capability_routing": True,
        "records": [
            event("intent_final", capability_resolution="routed", tool_call_resolution="param_not_from_input"),
            event("dispatch_decision", proposal_gate_result="not_evaluated"),
            event("turn_completed", rounds_used=2, reply_provenance="unfulfilled"),
        ],
    }])

    assert "capability_early_exit=1" in report
    assert "other=1" not in report
    assert "补参续接回合数（param_supply）" in report
    assert "- param_supply_turn：" not in report


def test_report_separates_instance_rejection_from_next_turn_supply() -> None:
    from scripts.p6_report import _render

    def event(stage: str, **data: object) -> dict[str, object]:
        return {"type": "runtime_event", "event": {"stage": stage, "data": data}}

    report = _render([{
        "run_id": "instance-followup", "scenario_id": "S18", "variant": "weather_on",
        "repeat": 1, "capability_routing": True,
        "records": [
            event("intent_final", capability_resolution="routed", tool_call_resolution="resolved",
                  param_instance_rejected=("location",)),
            event("turn_completed", rounds_used=2, reply_provenance="unfulfilled"),
            event("intent_final", capability_resolution="routed", tool_call_resolution="resolved",
                  param_instance_rejected=()),
            event("turn_completed", rounds_used=0, reply_provenance="executed"),
        ],
    }])

    assert "实例参数拒绝回合数：1" in report
    assert "location=1" in report
    assert "instance_supply_same_turn=0" in report


def test_report_allows_forced_cloud_on_instance_rejection_turn() -> None:
    from scripts.p6_report import _render

    def event(stage: str, **data: object) -> dict[str, object]:
        return {"type": "runtime_event", "event": {"stage": stage, "data": data}}

    report = _render([{
        "run_id": "forced-instance", "scenario_id": "S18", "variant": "weather_on",
        "repeat": 1, "capability_routing": True,
        "records": [
            event("intent_final", capability_resolution="routed", tool_call_resolution="resolved",
                  param_instance_rejected=("location",)),
            event("dispatch_decision", proposal_gate_result="admitted_forced"),
            event("cloud_consult", phase="returned"),
            event("turn_completed", rounds_used=2, reply_provenance="unfulfilled"),
        ],
    }])

    assert "param_instance_rejected=0" in report


def test_render_config_rejects_missing_weather_placeholder(tmp_path: Path) -> None:
    template = tmp_path / "template.toml"
    text = Path("config/eval.example.toml").read_text(encoding="utf-8")
    template.write_text(text.replace("{{WEATHER_PROVIDER}}", "none"), encoding="utf-8")

    with pytest.raises(ValueError, match="weather provider"):
        render_instance_config(template, tmp_path / "run", "weather_on")


def test_render_config_rejects_missing_capability_switch(tmp_path: Path) -> None:
    template = tmp_path / "template.toml"
    text = Path("config/eval.example.toml").read_text(encoding="utf-8")
    template.write_text(text.replace("enabled = true # {{CAPABILITY_ROUTING_ENABLED}}", "enabled = true"), encoding="utf-8")

    with pytest.raises(ValueError, match="capability routing"):
        render_instance_config(template, tmp_path / "run", "base", capability_off=True)
