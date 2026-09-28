from __future__ import annotations

from pathlib import Path

from scripts.run_p6_scenarios import _parser
from src.evaluation.config import config_snapshot, render_instance_config, snapshots_are_fair
from src.evaluation.scenarios import load_scenario, variants_for


def test_s19_loads_with_both_mcp_variants() -> None:
    path = Path(__file__).parents[1] / "scenarios" / "S19_external_tool_unavailable.toml"
    scenario = load_scenario(path)
    assert variants_for(scenario) == ("mcp_on", "mcp_off")
    assert _parser().parse_args(["--variant", "mcp_on"]).variant == "mcp_on"


def test_eval_renderer_and_snapshot_track_provider_enablement(tmp_path: Path) -> None:
    template = Path(__file__).parents[1] / "config" / "eval.example.toml"
    on = render_instance_config(template, tmp_path / "on", "mcp_on")
    off = render_instance_config(template, tmp_path / "off", "mcp_off")
    on_snapshot = config_snapshot(on)
    off_snapshot = config_snapshot(off)
    assert on_snapshot["tool_providers"] == ("demo",)
    assert off_snapshot["tool_providers"] == ()
    assert not snapshots_are_fair(on_snapshot, off_snapshot)
