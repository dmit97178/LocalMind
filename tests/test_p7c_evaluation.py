"""P7c scenario vocabulary and docs-on/off rendering."""

import tomllib
from pathlib import Path

import pytest

from src.core.schemas import LocalMindError
from src.evaluation.config import render_instance_config
from src.evaluation.runner import _expectation_failures
from src.evaluation.scenarios import _parse_expect, load_scenario, variants_for


def test_p7c_scenarios_load_with_declared_variants() -> None:
    for name in ("S20_document_read.toml", "S21_workspace_search.toml"):
        scenario = load_scenario(Path("scenarios") / name)
        assert variants_for(scenario) == ("docs_on", "docs_off")


def test_docs_variant_controls_only_the_two_new_tools(tmp_path: Path) -> None:
    template = Path("config/eval.example.toml")
    on = render_instance_config(template, tmp_path / "on", "docs_on")
    off = render_instance_config(template, tmp_path / "off", "docs_off")

    with on.open("rb") as stream:
        on_tools = tomllib.load(stream)["tool_backend"]["config"]["whitelist"]
    with off.open("rb") as stream:
        off_tools = tomllib.load(stream)["tool_backend"]["config"]["whitelist"]
    assert set(on_tools) - set(off_tools) == {"document.read", "file.search"}


def test_docs_variant_rejects_template_without_placeholder(tmp_path: Path) -> None:
    template = tmp_path / "missing.toml"
    template.write_text(
        Path("config/eval.example.toml").read_text(encoding="utf-8").replace(
            " # {{DOC_TOOLS}}", ""
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="doc tools placeholder"):
        render_instance_config(template, tmp_path / "rendered", "docs_on")


def test_p7c_expectations_observe_delivery_and_forbid_output_text() -> None:
    event = {
        "type": "runtime_event",
        "event": {
            "stage": "tool_execution",
            "data": {"tool_name": "document.read", "result_delivery": "model_summary"},
        },
    }
    expect = {
        "result_delivery_any": ["model_summary"],
        "output_not_contains": ["eval-pass-0000"],
    }

    assert _expectation_failures(expect, "安全摘要", [event]) == []
    assert _expectation_failures(expect, "泄漏 eval-pass-0000", [event]) == [
        "output_not_contains"
    ]


def test_p7c_expectation_lists_cannot_be_empty() -> None:
    with pytest.raises(LocalMindError):
        _parse_expect({"result_delivery_any": []}, "user", False)
