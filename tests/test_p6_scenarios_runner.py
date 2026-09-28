"""P6b scenario-definition and isolated-config tests."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from src.core.schemas import LocalMindError


def test_load_scenario_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    from src.evaluation.scenarios import load_scenario

    scenario_path = tmp_path / "bad.toml"
    scenario_path.write_text(
        """
[scenario]
id = "S01_bad"
title = "bad"
group = "g0_basic"
unexpected = true

[[steps]]
kind = "user"
text = "hello"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(LocalMindError, match="unknown scenario keys"):
        load_scenario(scenario_path)


def test_load_scenario_rejects_invalid_id_and_conflicting_experiment_flags(tmp_path: Path) -> None:
    from src.evaluation.scenarios import load_scenario

    path = tmp_path / "bad.toml"
    path.write_text(
        """
[scenario]
id = "not-a-scenario"
title = "bad"
group = "g1_progressive"
value_ab = true
rounds_ab = true

[[steps]]
kind = "user"
text = "hello"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(LocalMindError, match="scenario id"):
        load_scenario(path)


def test_variants_follow_the_declared_ab_flags(tmp_path: Path) -> None:
    from src.evaluation.scenarios import load_scenario, variants_for

    scenario_path = tmp_path / "ab.toml"
    scenario_path.write_text(
        """
[scenario]
id = "S06_ab"
title = "comparison"
group = "g2_value"
value_ab = true
rounds_ab = false

[[steps]]
kind = "user"
text = "compare options"
cloud_ask = true
""".strip(),
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_path)

    assert variants_for(scenario, "auto") == ("local_only", "cloud_assisted")


def test_value_ab_may_declare_cloud_auto_as_an_observation_arm(tmp_path: Path) -> None:
    from src.evaluation.scenarios import load_scenario, variants_for

    scenario_path = tmp_path / "cloud_auto.toml"
    scenario_path.write_text(
        """
[scenario]
id = "S06_cloud_auto"
title = "cloud auto"
group = "g2_value"
value_ab = true
variants = ["local_only", "cloud_assisted", "cloud_auto"]

[[steps]]
kind = "user"
text = "analyze"
""".strip(),
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_path)

    assert variants_for(scenario) == (
        "local_only",
        "cloud_assisted",
        "cloud_auto",
    )


def test_rounds_ab_still_rejects_explicit_variants(tmp_path: Path) -> None:
    from src.evaluation.scenarios import load_scenario

    scenario_path = tmp_path / "rounds_explicit.toml"
    scenario_path.write_text(
        """
[scenario]
id = "S02_rounds"
title = "rounds"
group = "g1_progressive"
rounds_ab = true
variants = ["round1", "round4"]

[[steps]]
kind = "user"
text = "analyze"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(LocalMindError, match="rounds_ab"):
        load_scenario(scenario_path)


def test_load_scenario_supports_multiple_runs_but_rejects_mixed_steps(tmp_path: Path) -> None:
    from src.evaluation.scenarios import load_scenario

    multi_run = tmp_path / "multi.toml"
    multi_run.write_text(
        """
[scenario]
id = "S16_restart"
title = "restart"
group = "g0_basic"

[[run]]
id = "first"
[[run.steps]]
kind = "user"
text = "remember this"

[[run]]
id = "second"
[[run.steps]]
kind = "slash"
text = "/quit"
""".strip(),
        encoding="utf-8",
    )
    scenario = load_scenario(multi_run)

    assert [run.id for run in scenario.runs] == ["first", "second"]
    assert scenario.steps == ()

    mixed = tmp_path / "mixed.toml"
    mixed.write_text(
        multi_run.read_text(encoding="utf-8") + '\n[[steps]]\nkind = "user"\ntext = "bad"\n',
        encoding="utf-8",
    )
    with pytest.raises(LocalMindError, match="cannot mix"):
        load_scenario(mixed)


@pytest.mark.parametrize(
    ("field", "value"),
    [("when_variant", "not_a_variant"), ("when_state", "not_a_state")],
)
def test_load_scenario_rejects_unknown_conditional_gate(
    tmp_path: Path, field: str, value: str
) -> None:
    from src.evaluation.scenarios import load_scenario

    scenario_path = tmp_path / "bad_gate.toml"
    scenario_path.write_text(
        f"""
[scenario]
id = "S01_gate"
title = "gate"
group = "g0_basic"

[[steps]]
kind = "user"
text = "hello"
{field} = "{value}"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(LocalMindError, match=field):
        load_scenario(scenario_path)


def test_render_instance_config_injects_absolute_isolated_paths_and_variant(tmp_path: Path) -> None:
    from src.evaluation.config import render_instance_config

    template = tmp_path / "eval.example.toml"
    template.write_text(
        """
[memory_backend]
type = "sqlite"
[memory_backend.config]
db_path = "{{INSTANCE_DIR}}/memory.sqlite3"
[memory_backend.config.embedding]
type = "{{EMBEDDING_TYPE}}"
[tools]
workspace_root = "{{INSTANCE_DIR}}/workspace"
[observability]
event_jsonl_path = ""
[safety.passphrase]
hash_file = "{{INSTANCE_DIR}}/.passphrase"
[cloud_advisory]
enabled = false
[execution]
intent_max_rounds = 4
""".strip(),
        encoding="utf-8",
    )
    instance = tmp_path / "instance"

    config_path = render_instance_config(template, instance, "round1")
    text = config_path.read_text(encoding="utf-8")

    assert "{{" not in text
    assert str(instance.resolve()).replace("\\", "/") in text
    assert 'type = "sqlite"' in text
    assert 'type = "ollama"' in text
    assert "intent_max_rounds = 1" in text
    assert "enabled = false" in text


def test_render_instance_config_injects_cloud_timeout_fault(tmp_path: Path) -> None:
    from src.evaluation.config import render_instance_config

    template = tmp_path / "eval.toml"
    template.write_text(
        """
[cloud_advisory]
enabled = true
[cloud_advisory.config]
request_timeout_seconds = 60
""".strip(),
        encoding="utf-8",
    )

    config = render_instance_config(template, tmp_path / "instance", "base", cloud_fault="timeout")

    assert "request_timeout_seconds = 0.001" in config.read_text(encoding="utf-8")


def test_render_instance_config_disables_cloud_for_a_local_scenario(tmp_path: Path) -> None:
    from src.evaluation.config import render_instance_config

    template = tmp_path / "eval.toml"
    template.write_text(
        """
[cloud_advisory]
enabled = true
""".strip(),
        encoding="utf-8",
    )

    config = render_instance_config(
        template,
        tmp_path / "instance",
        "round4",
        cloud_enabled=False,
    )

    assert "enabled = false" in config.read_text(encoding="utf-8")


def test_cloud_availability_follows_scenario_semantics() -> None:
    from scripts.run_p6_scenarios import _cloud_enabled_for_scenario

    class ScenarioStub:
        def __init__(self, group: str, steps: tuple[object, ...] = ()) -> None:
            self.group = group
            self.steps = steps
            self.runs = ()

    assert _cloud_enabled_for_scenario(ScenarioStub("g1_progressive"), "round1") is False
    assert _cloud_enabled_for_scenario(ScenarioStub("g0_basic"), "base") is False
    assert _cloud_enabled_for_scenario(ScenarioStub("g3_autonomy"), "base") is True
    assert _cloud_enabled_for_scenario(ScenarioStub("g2_value"), "cloud_assisted") is True


def test_config_snapshot_is_allowlisted_and_excludes_credentials(tmp_path: Path) -> None:
    from src.evaluation.config import config_snapshot

    path = tmp_path / "config.toml"
    path.write_text(
        """
[model_backend]
type = "ollama"
[model_backend.config]
model = "qwen3:4b"
[memory_backend]
type = "sqlite"
[memory_backend.config.embedding]
type = "none"
[cloud_advisory]
enabled = true
provider = "glm"
api_key = "must-not-appear"
[execution]
intent_max_rounds = 4
""".strip(),
        encoding="utf-8",
    )

    snapshot = config_snapshot(path)

    assert snapshot["cloud_advisory"] == {"enabled": True}
    assert snapshot["cloud_provider"] == "glm"
    assert "must-not-appear" not in str(snapshot)


def test_fairness_ignores_only_declared_variant_controls() -> None:
    from src.evaluation.config import snapshots_are_fair

    left = {
        "model_backend": {"type": "ollama", "model": "qwen3:4b"},
        "memory_backend": {"type": "sqlite", "embedding_type": "ollama"},
        "cloud_advisory": {"enabled": False},
        "cloud_provider": "glm",
        "execution": {"intent_max_rounds": 1},
    }
    right = {
        "model_backend": {"type": "ollama", "model": "qwen3:4b"},
        "memory_backend": {"type": "sqlite", "embedding_type": "none"},
        "cloud_advisory": {"enabled": True},
        "cloud_provider": "glm",
        "execution": {"intent_max_rounds": 4},
    }

    assert snapshots_are_fair(left, right)
    right["model_backend"] = {"type": "ollama", "model": "different"}
    assert not snapshots_are_fair(left, right)


def test_evaluation_template_keeps_a_real_cloud_backend_available_for_assisted_runs(tmp_path: Path) -> None:
    from src.evaluation.config import render_instance_config

    template_path = Path(__file__).parents[1] / "config" / "eval.example.toml"
    config_path = render_instance_config(template_path, tmp_path / "instance", "cloud_assisted")

    with config_path.open("rb") as stream:
        config = tomllib.load(stream)

    assert config["cloud_advisory"]["provider"] == "deepseek"
    assert config["cloud_advisory"]["connection"]["model"] == "deepseek-v4-flash"
    assert config["cloud_advisory"]["enabled"] is True


def test_cloud_key_precheck_uses_active_provider_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.run_p6_scenarios import _cloud_key_present

    config_path = tmp_path / "config.toml"
    config_path.write_text('[cloud_advisory]\nenabled = true\nprovider = "glm"\n', encoding="utf-8")
    monkeypatch.setenv("LOCALMIND_CLOUD_API_KEY", "legacy-deepseek-only")
    monkeypatch.delenv("LOCALMIND_GLM_API_KEY", raising=False)
    assert _cloud_key_present(config_path) is False
    monkeypatch.setenv("LOCALMIND_GLM_API_KEY", "glm-key")
    assert _cloud_key_present(config_path) is True


def test_cloud_auto_requires_credentials_and_is_a_cli_variant() -> None:
    from scripts.run_p6_scenarios import _parser, _requires_cloud

    assert _requires_cloud(object(), "cloud_auto") is True
    assert _parser().parse_args(["--variant", "cloud_auto"]).variant == "cloud_auto"


def test_document_tool_variants_are_valid_child_cli_values() -> None:
    from scripts.run_p6_scenarios import _parser

    parser = _parser()
    assert parser.parse_args(["--variant", "docs_on"]).variant == "docs_on"
    assert parser.parse_args(["--variant", "docs_off"]).variant == "docs_off"


def test_drive_steps_renders_cloud_ask_and_excludes_prelude_from_summary() -> None:
    from src.evaluation.runner import drive_steps
    from src.evaluation.scenarios import Scenario, ScenarioStep

    class FakeApp:
        def __init__(self) -> None:
            self.inputs: list[str] = []
            self.ended: list[str] = []

        def handle(self, text: str, session_id: str, project_id: str | None = None) -> str:
            del session_id, project_id
            self.inputs.append(text)
            return "reply"

        def end_session(self, session_id: str) -> None:
            self.ended.append(session_id)

        def last_turn_report(self) -> dict[str, object]:
            return {"rounds_used": 2, "action": "PLAN_LOCAL", "error_code": None}

    scenario = Scenario(
        "S06_toy",
        "toy",
        "g2_value",
        True,
        False,
        30,
        (
            ScenarioStep("user", "setup", prelude=True),
            ScenarioStep("user", "analyze this", cloud_ask=True),
            ScenarioStep("user", "skip", when_variant="local_only"),
        ),
    )
    app = FakeApp()

    results, summary = drive_steps(app, scenario, "cloud_assisted", "sess_eval_run")

    assert app.inputs == ["setup", "/cloud ask analyze this"]
    assert results[0]["prelude"] is True
    assert results[2]["skipped_reason"] == "when_variant"
    assert summary["total_turns"] == 1
    assert summary["rounds_used"] == [2]
    assert summary["actions"] == ["PLAN_LOCAL"]


def test_drive_steps_honors_state_gate_and_records_non_fatal_expect_failure(tmp_path: Path) -> None:
    from src.evaluation.runner import drive_steps
    from src.evaluation.scenarios import Scenario, ScenarioStep

    class FakeApp:
        def handle(self, text: str, session_id: str, project_id: str | None = None) -> str:
            del text, session_id, project_id
            return "reply"

        def end_session(self, session_id: str) -> None:
            del session_id

        def last_turn_report(self) -> dict[str, object]:
            return {"rounds_used": 1, "action": "ASK_USER", "error_code": None}

    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"v":1,"type":"runtime_event","event":{"stage":"cloud_consult","data":{"phase":"authorization_required"}}}\n',
        encoding="utf-8",
    )
    scenario = Scenario(
        "S06_gate",
        "gate",
        "g2_value",
        True,
        False,
        30,
        (
            ScenarioStep("user", "/cloud allow", when_state="awaiting_cloud_authorization"),
            ScenarioStep("user", "continue", expect={"action_any": ["REQUEST_CLOUD"]}),
        ),
    )

    results, _ = drive_steps(FakeApp(), scenario, "cloud_assisted", "sess", event_log_path=events)

    assert "skipped_reason" not in results[0]
    assert results[1]["ok"] is False
    assert results[1]["fail_reason"] == "action_any"


def test_when_state_unmet_fails_but_non_target_variant_skips() -> None:
    from src.evaluation.runner import drive_steps
    from src.evaluation.scenarios import Scenario, ScenarioStep

    class FakeApp:
        def handle(self, text: str, session_id: str, project_id: str | None = None) -> str:
            del text, session_id, project_id
            return "reply"

        def end_session(self, session_id: str) -> None:
            del session_id

        def last_turn_report(self) -> dict[str, object]:
            return {"rounds_used": 1, "action": "PLAN_LOCAL", "error_code": None}

    step = ScenarioStep(
        "slash",
        "/cloud allow",
        when_variant="cloud_assisted",
        when_state="awaiting_cloud_authorization",
    )
    scenario = Scenario("S06_gate", "gate", "g2_value", True, False, 30, (step,))

    assisted, _ = drive_steps(FakeApp(), scenario, "cloud_assisted", "sess")
    local, _ = drive_steps(FakeApp(), scenario, "local_only", "sess")

    assert assisted[0]["ok"] is False
    assert assisted[0]["fail_reason"] == "when_state_unmet"
    assert local[0]["ok"] is True
    assert local[0]["skipped_reason"] == "when_variant"


def test_cloud_assisted_missing_authorization_cannot_pass_as_a_skip() -> None:
    from src.evaluation.runner import drive_steps
    from src.evaluation.scenarios import Scenario, ScenarioStep

    class FakeApp:
        def handle(self, text: str, session_id: str, project_id: str | None = None) -> str:
            del text, session_id, project_id
            return "reply"

        def end_session(self, session_id: str) -> None:
            del session_id

        def last_turn_report(self) -> dict[str, object]:
            return {"rounds_used": 1, "action": "PLAN_LOCAL", "error_code": None}

    scenario = Scenario(
        "S06_false_positive",
        "g2",
        "g2_value",
        True,
        False,
        30,
        (
            ScenarioStep("user", "complex task", cloud_ask=True),
            ScenarioStep(
                "slash",
                "/cloud allow",
                when_variant="cloud_assisted",
                when_state="awaiting_cloud_authorization",
            ),
        ),
    )
    results, _ = drive_steps(FakeApp(), scenario, "cloud_assisted", "sess")

    assert results[-1]["ok"] is False
    assert results[-1]["fail_reason"] == "when_state_unmet"


def test_summarize_run_counts_only_structural_runtime_events() -> None:
    from src.evaluation.runner import summarize_run

    events = [
        {
            "type": "runtime_event",
            "event": {
                "stage": "turn_completed",
                "data": {"rounds_used": 2, "had_confirmation": True},
            },
        },
        {
            "type": "runtime_event",
            "event": {"stage": "dispatch_decision", "data": {"action": "REQUEST_CLOUD"}},
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "intent_final",
                "data": {
                    "risk_draft": "sensitive",
                    "risk_draft_resolution": "mapped_legacy",
                },
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "cloud_consult",
                "data": {
                    "phase": "outbound",
                    "outbound_bytes": 120,
                    "outbound_categories": ["free_text"],
                },
            },
        },
        {
            "type": "runtime_event",
            "event": {"stage": "tool_execution", "data": {"verdict": "denied"}},
        },
        {
            "type": "runtime_event",
            "event": {"stage": "degradation", "data": {"component": "embedding"}},
        },
    ]
    steps = [{"type": "step_result", "prelude": False, "ok": True}]

    summary = summarize_run(events, steps, duration_ms_total=42)

    assert summary["rounds_used"] == [2]
    assert summary["actions"] == ["REQUEST_CLOUD"]
    assert summary["confirmations"] == 1
    assert summary["cloud"] == {
        "upgrades": 1,
        "denials": 0,
        "cooldowns": 0,
        "outbound_bytes": 120,
        "outbound_categories": ["free_text"],
    }
    assert summary["tools"] == {"executed": 0, "denied": 1}
    assert summary["degradations"] == ["embedding"]
    assert summary["risk_draft_results"] == {"sensitive": 1}
    assert summary["risk_draft_resolution_results"] == {"mapped_legacy": 1}


def test_summarize_run_counts_sensitive_admission_and_policy_grant_wiring_defects() -> None:
    from src.evaluation.runner import summarize_run

    events = [
        {
            "type": "runtime_event",
            "event": {
                "stage": "intent_final",
                "data": {"risk_draft": "sensitive"},
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "dispatch_decision",
                "data": {
                    "action": "REQUEST_CLOUD",
                    "proposal_gate_result": "admitted_proposal",
                    "proposal_denied_reason": "none",
                },
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "cloud_consult",
                "data": {
                    "phase": "denied",
                    "denied_reason": "sensitive_policy_grant_forbidden",
                },
            },
        },
    ]

    summary = summarize_run(events, [], duration_ms_total=1)

    assert summary["sensitive_proposal_admitted"] == 1
    assert summary["cloud_denied_reasons"] == {
        "sensitive_policy_grant_forbidden": 1
    }


def test_summarize_run_pairs_resolution_exhaustion_with_dispatch_outcome() -> None:
    """Exhaustion must stay distinct from no-progress and retain its cloud gate outcome."""

    from src.evaluation.runner import summarize_run

    events = [
        {
            "type": "runtime_event",
            "event": {
                "stage": "intent_final",
                "data": {"resolution_exhausted": True},
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "dispatch_decision",
                "data": {
                    "action": "REQUEST_CLOUD",
                    "proposal_gate_result": "admitted_proposal",
                },
            },
        },
    ]

    summary = summarize_run(events, [], duration_ms_total=1)

    assert summary["resolution_exhausted"] == 1
    assert summary["resolution_exhausted_actions"] == {
        "admitted_proposal": {"REQUEST_CLOUD": 1}
    }


def test_summarize_run_does_not_pair_a_stale_exhaustion_with_the_next_turn() -> None:
    """An interrupted exhausted turn must not contaminate the following dispatch."""

    from src.evaluation.runner import summarize_run

    events = [
        {
            "type": "runtime_event",
            "event": {
                "stage": "intent_final",
                "data": {"resolution_exhausted": True},
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "intent_final",
                "data": {"resolution_exhausted": False},
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "dispatch_decision",
                "data": {"action": "PLAN_LOCAL", "proposal_gate_result": "absent"},
            },
        },
    ]

    summary = summarize_run(events, [], duration_ms_total=1)

    assert summary["resolution_exhausted"] == 1
    assert summary["resolution_exhausted_actions"] == {}


def test_reference_guard_expectation_is_boolean_and_unknown_keys_remain_closed(
    tmp_path: Path,
) -> None:
    from src.evaluation.scenarios import load_scenario

    valid = tmp_path / "valid.toml"
    valid.write_text(
        """
[scenario]
id = "S02_guard"
title = "guard"
group = "g1_progressive"

[[steps]]
kind = "user"
text = "ambiguous target"
expect = { reference_guard_any = true }
""".strip(),
        encoding="utf-8",
    )
    assert load_scenario(valid).steps[0].expect == {"reference_guard_any": True}

    invalid = tmp_path / "invalid.toml"
    invalid.write_text(
        valid.read_text(encoding="utf-8").replace(
            "reference_guard_any = true", 'reference_guard_any = "yes"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(LocalMindError, match="reference_guard_any"):
        load_scenario(invalid)


def test_reference_guard_expectation_treats_not_evaluated_as_structural_failure() -> None:
    from src.evaluation.runner import _expectation_failures

    events = [
        {
            "type": "runtime_event",
            "event": {
                "stage": "dispatch_decision",
                "data": {"reference_guard_result": "not_evaluated"},
            },
        }
    ]

    assert _expectation_failures({"reference_guard_any": False}, "", events) == [
        "reference_guard_any"
    ]
    assert _expectation_failures({"reference_guard_any": True}, "", events) == [
        "reference_guard_any"
    ]


def test_s02_attribution_requires_triggered_for_guard_rescued() -> None:
    from src.evaluation.runner import classify_s02_attribution

    assert classify_s02_attribution(
        action="ASK_USER",
        final_state="READY",
        missing_info_count=0,
        reference_guard_result="not_triggered",
    ) == "unattributed_ask"
    assert classify_s02_attribution(
        action="ASK_USER",
        final_state="READY",
        missing_info_count=0,
        reference_guard_result="triggered",
    ) == "guard_rescued"
    assert classify_s02_attribution(
        action="ASK_USER",
        final_state="VAGUE",
        missing_info_count=1,
        reference_guard_result="triggered",
    ) == "model_asked"
    assert classify_s02_attribution(
        action="PLAN_LOCAL",
        final_state="VAGUE",
        missing_info_count=1,
        reference_guard_result="triggered",
    ) == "failed"


def test_execute_segment_appends_only_step_metadata(tmp_path: Path) -> None:
    from src.evaluation.child import execute_segment
    from src.evaluation.records import read_records
    from src.evaluation.scenarios import Scenario, ScenarioStep

    class FakeApp:
        def handle(self, text: str, session_id: str, project_id: str | None = None) -> str:
            del text, session_id, project_id
            return "reply with secret=definitely-not-for-jsonl"

        def end_session(self, session_id: str) -> None:
            del session_id

        def last_turn_report(self) -> dict[str, object]:
            return {"rounds_used": 1, "action": "PLAN_LOCAL", "error_code": None}

    scenario = Scenario(
        "S01_child",
        "child",
        "g0_basic",
        False,
        False,
        30,
        (ScenarioStep("user", "input with secret=definitely-not-for-jsonl"),),
    )
    path = tmp_path / "events.jsonl"

    execute_segment(FakeApp(), scenario, None, "base", "sess", path)

    records = read_records(path)
    assert records[0]["type"] == "step_result"
    assert "input with secret" not in path.read_text(encoding="utf-8")
    assert "reply with secret" not in path.read_text(encoding="utf-8")


def test_archive_run_moves_projected_artifacts_and_removes_instance(tmp_path: Path) -> None:
    from src.evaluation.artifacts import archive_run

    instance = tmp_path / "instance"
    run_id = "run123"
    events = instance / "runs" / f"{run_id}.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text('{"type":"run_meta"}\nnot-json\n', encoding="utf-8")
    transcript = instance / "transcripts" / f"{run_id}.md"
    transcript.parent.mkdir()
    transcript.write_text("sanitized transcript", encoding="utf-8")
    (instance / "memory.sqlite3").write_text("private", encoding="utf-8")
    destination = tmp_path / "evals"

    archived = archive_run(instance, run_id, destination, transcript=True)

    assert archived == destination / f"run_{run_id}.jsonl"
    assert archived.read_text(encoding="utf-8") == '{"type":"run_meta"}\n'
    assert (destination / "transcripts" / f"run_{run_id}.md").read_text(
        encoding="utf-8"
    ) == "sanitized transcript"
    assert not instance.exists()


def test_finalize_run_appends_summary_before_archiving(tmp_path: Path) -> None:
    from src.evaluation.parent import finalize_run
    from src.evaluation.records import append_record, read_records

    instance = tmp_path / "instance"
    event_path = instance / "runs" / "run456.jsonl"
    append_record(event_path, {"type": "run_meta", "run_id": "run456"})
    append_record(
        event_path,
        {
            "v": 1,
            "type": "runtime_event",
            "event": {"stage": "turn_completed", "data": {"rounds_used": 1}},
        },
    )
    append_record(event_path, {"type": "step_result", "prelude": False, "ok": True})

    archived = finalize_run(
        instance,
        "run456",
        tmp_path / "evals",
        duration_ms_total=8,
        transcript=False,
        group="g0_basic",
    )

    records = read_records(archived)
    assert records[-2]["type"] == "run_summary"
    assert records[-2]["total_turns"] == 1
    assert records[-1]["type"] == "human_score"
    assert not instance.exists()


def test_archived_run_failure_reason_reports_failed_expectations(tmp_path: Path) -> None:
    from scripts.run_p6_scenarios import _archived_run_failure_reason
    from src.evaluation.records import append_record

    run_path = tmp_path / "run_failed.jsonl"
    append_record(run_path, {"type": "run_meta", "run_id": "failed"})
    append_record(run_path, {"type": "run_summary", "failed_steps": 2})

    assert _archived_run_failure_reason(run_path) == "expectation_failed"


def test_episode_setup_normalizes_blank_project_id_to_unscoped() -> None:
    from src.evaluation.child import _apply_setup
    from src.evaluation.scenarios import ScenarioSetup

    class RecordingMemory:
        def __init__(self) -> None:
            self.metadata: dict[str, object] | None = None

        def store_episode(self, content: str, metadata: dict[str, object]) -> str:
            del content
            self.metadata = metadata
            return "episode"

    class FakeApp:
        def __init__(self) -> None:
            self.memory = RecordingMemory()

    app = FakeApp()
    setup = ScenarioSetup(
        "episode",
        {
            "session_id": "preset",
            "text": "apollo release window",
            "metadata": {"topic": "apollo", "project_id": ""},
        },
    )

    _apply_setup(app, (setup,))  # type: ignore[arg-type]

    assert app.memory.metadata == {
        "topic": "apollo",
        "project_id": None,
        "session_id": "preset",
    }


def test_generate_pair_reviews_keeps_variants_out_of_the_review_sheet(tmp_path: Path) -> None:
    from src.evaluation.records import read_records
    from src.evaluation.review import generate_pair_reviews

    evals = tmp_path / "evals"
    transcripts = evals / "transcripts"
    transcripts.mkdir(parents=True)
    for run_id in ("r1", "r2"):
        (transcripts / f"run_{run_id}.md").write_text(f"answer {run_id}", encoding="utf-8")
    runs = [
        {"scenario_id": "S06_value", "variant": "local_only", "repeat": 1, "run_id": "r1"},
        {"scenario_id": "S06_value", "variant": "cloud_assisted", "repeat": 1, "run_id": "r2"},
    ]

    sheets = generate_pair_reviews(runs, evals)

    sheet = sheets[0]
    text = sheet.read_text(encoding="utf-8")
    assert "local_only" not in text and "cloud_assisted" not in text
    key = next((evals / "review").glob("*.key.json")).read_text(encoding="utf-8")
    assert "local_only" in key and "cloud_assisted" in key
    score = read_records(next((evals / "review").glob("*.scores.jsonl")))[0]
    assert set(score["scores"]) == {
        "completeness",
        "reasoning_quality",
        "constraint_compliance",
        "cloud_worth_it",
    }


def test_generate_pair_reviews_never_pairs_different_cloud_providers(tmp_path: Path) -> None:
    from src.evaluation.review import generate_pair_reviews

    evals = tmp_path / "evals"
    transcripts = evals / "transcripts"
    transcripts.mkdir(parents=True)
    runs = [
        {
            "scenario_id": "S06_value",
            "variant": "local_only",
            "repeat": 1,
            "run_id": "deepseek-local",
            "config_snapshot": {"cloud_provider": "deepseek"},
        },
        {
            "scenario_id": "S06_value",
            "variant": "cloud_assisted",
            "repeat": 1,
            "run_id": "glm-cloud",
            "config_snapshot": {"cloud_provider": "glm"},
        },
    ]
    for run in runs:
        (transcripts / f"run_{run['run_id']}.md").write_text("answer", encoding="utf-8")

    assert generate_pair_reviews(runs, evals) == []


def test_report_separates_provider_generations_and_fairness() -> None:
    from scripts.p6_report import _fairness_by_run, _render

    rows = [
        {
            "scenario_id": "S06_value",
            "group": "g2_value",
            "variant": "local_only",
            "repeat": 1,
            "run_id": "deepseek-local",
            "config_snapshot": {
                "cloud_provider": "deepseek",
                "cloud_advisory": {"enabled": False},
            },
        },
        {
            "scenario_id": "S06_value",
            "group": "g2_value",
            "variant": "cloud_assisted",
            "repeat": 1,
            "run_id": "glm-cloud",
            "config_snapshot": {
                "cloud_provider": "glm",
                "cloud_advisory": {"enabled": True},
            },
        },
    ]

    assert _fairness_by_run(rows) == {}
    report = _render(rows)
    assert "| Provider |" in report
    assert "deepseek" in report
    assert "glm" in report


def test_report_aggregates_autonomous_cloud_gate_and_no_progress_signals() -> None:
    from scripts.p6_report import _render

    rows = [
        {
            "scenario_id": "S09_autonomous_escalation",
            "group": "g3_autonomy",
            "variant": "base",
            "run_id": "proposal-run",
            "summary": {
                "proposal_gate_results": {"admitted_proposal": 1},
                "proposal_denied_reasons": {},
                "cloud_denied_reasons": {},
                "no_progress_detected": 0,
                "stopped_early": 0,
            },
        },
        {
            "scenario_id": "S06_value_reasoning",
            "group": "g2_value",
            "variant": "cloud_auto",
            "run_id": "auto-run",
            "summary": {
                "proposal_gate_results": {"admitted_proposal": 1},
                "proposal_denied_reasons": {},
                "no_progress_detected": 0,
                "stopped_early": 0,
                "resolution_exhausted": 1,
                "resolution_exhausted_actions": {
                    "admitted_proposal": {"REQUEST_CLOUD": 1}
                },
                "cloud_authorization_required": 1,
                "unauthorized_outbound": 0,
                "risk_draft_results": {"normal": 1},
                "risk_draft_resolution_results": {"declared": 1},
                "sensitive_proposal_admitted": 0,
            },
        },
        {
            "scenario_id": "S05_simple_task_no_cloud",
            "group": "g0_basic",
            "variant": "base",
            "run_id": "simple-run",
            "summary": {
                "proposal_gate_results": {"absent": 1},
                "proposal_denied_reasons": {},
                "no_progress_detected": 0,
                "stopped_early": 0,
                "cloud_authorization_required": 0,
                "unauthorized_outbound": 0,
            },
        },
        {
            "scenario_id": "S11_cloud_forbidden",
            "group": "g3_autonomy",
            "variant": "base",
            "run_id": "veto-run",
            "summary": {
                "proposal_gate_results": {"vetoed": 1},
                "proposal_denied_reasons": {"deny_cloud": 1},
                "no_progress_detected": 1,
                "stopped_early": 1,
            },
        },
    ]

    report = _render(rows)

    assert "admitted_proposal" in report
    assert "vetoed" in report
    assert "deny_cloud" in report
    assert "No-progress" in report
    assert "Resolution exhausted：1；admitted_proposal: REQUEST_CLOUD=1" in report
    assert "S09 自主建议率：1/1" in report
    assert "S06 cloud_auto 自主建议率：1/1" in report
    assert "S05 简单任务误升级率：0/1" in report
    assert "未授权外发违规：0" in report
    assert "Policy grant 接线缺陷：0（必须为 0）" in report
    assert "Risk draft：normal=1" in report
    assert "Risk resolution：declared=1" in report
    assert "Sensitive proposal admitted：0" in report
    assert "non_normal_risk 接线缺陷：0（必须为 0）" in report


def test_report_separates_reference_guard_distribution_and_s02_attribution() -> None:
    from scripts.p6_report import _render

    rows = [
        {
            "scenario_id": "S02_ask_user_when_insufficient",
            "group": "g1_progressive",
            "variant": "round1",
            "repeat": 1,
            "run_id": "s02-model",
            "summary": {
                "reference_guard_results": {"triggered": 1},
                "s02_attribution": "model_asked",
                "should_consult_results": {"true": 0, "false": 1},
            },
        },
        {
            "scenario_id": "S02_ask_user_when_insufficient",
            "group": "g1_progressive",
            "variant": "round4",
            "repeat": 1,
            "run_id": "s02-guard",
            "summary": {
                "reference_guard_results": {"triggered": 1},
                "s02_attribution": "guard_rescued",
                "should_consult_results": {"true": 1, "false": 0},
            },
        },
        {
            "scenario_id": "S05_simple_task_no_cloud",
            "group": "g0_basic",
            "variant": "base",
            "repeat": 1,
            "run_id": "s05",
            "summary": {
                "reference_guard_results": {"not_triggered": 1},
                "s02_attribution": "failed",
            },
        },
    ]

    report = _render(rows)

    assert "S02_ask_user_when_insufficient：triggered=2" in report
    assert "S05_simple_task_no_cloud：not_triggered=1" in report
    assert "model_asked：1" in report
    assert "guard_rescued：1" in report
    assert "unattributed_ask：0" in report
    assert "failed：0" in report
    assert "四态合计：2/2" in report
    assert "model_asked_but_not_ask_user：0" in report
    assert "Should consult：true=1，false=1" in report


def test_summarize_run_detects_outbound_before_authorization() -> None:
    from src.evaluation.runner import summarize_run

    events = [
        {
            "type": "runtime_event",
            "event": {
                "stage": "cloud_consult",
                "data": {"phase": "outbound", "outbound_bytes": 10},
            },
        },
        {
            "type": "runtime_event",
            "event": {
                "stage": "cloud_consult",
                "data": {"phase": "authorization_required"},
            },
        },
    ]

    summary = summarize_run(events, [], duration_ms_total=1)

    assert summary["cloud_authorization_required"] == 1
    assert summary["unauthorized_outbound"] == 1
