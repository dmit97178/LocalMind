"""Run isolated P6b scenario instances through the production bootstrap path."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIRST_ROUND_IDS = frozenset({"S02", "S04", "S05", "S06", "S08", "S09", "S10", "S11"})
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    args = _parser().parse_args()
    if args.child:
        return _run_child(args)
    if args.first_round and not args.all:
        raise SystemExit("--first-round requires --all")
    if not args.all and not args.scenario:
        raise SystemExit("provide --scenario <id> or --all")
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")

    from src.evaluation.config import render_instance_config
    from src.evaluation.parent import finalize_run
    from src.evaluation.records import append_record
    from src.evaluation.scenarios import load_scenario, variants_for

    scenario_paths = _select_scenarios(Path(args.scenarios_dir), args.scenario, args.all)
    if args.group:
        from src.evaluation.scenarios import load_scenario

        selected_group = "g4_capability" if args.group == "g4" else args.group
        scenario_paths = [path for path in scenario_paths if load_scenario(path).group == selected_group]
    if args.first_round:
        scenario_paths = [path for path in scenario_paths if path.stem[:3] in _FIRST_ROUND_IDS]
    if not scenario_paths:
        raise SystemExit("no scenarios matched the requested selection")
    any_failed = False
    for scenario_path in scenario_paths:
        scenario = load_scenario(scenario_path)
        requested_variant = "auto" if args.variant == "both" else args.variant
        for variant in variants_for(scenario, requested_variant):
            cloud_enabled = _cloud_enabled_for_scenario(scenario, variant)
            if cloud_enabled and not _cloud_key_present(args.config):
                print(f"{scenario.id} {variant}: skipped cloud_credentials_missing")
                continue
            for repeat in range(1, args.repeats + 1):
                temp_root = Path(tempfile.mkdtemp(prefix="localmind-eval-"))
                instance = temp_root / f"{scenario.id}__{variant}__r{repeat}"
                config_path = render_instance_config(
                    args.config,
                    instance,
                    variant,
                    cloud_fault=scenario.cloud_fault,
                    cloud_enabled=cloud_enabled,
                    capability_off=args.capability_off,
                )
                segments = scenario.runs or (None,)
                for number, segment in enumerate(segments):
                    run_id = uuid4().hex[:12]
                    event_path = instance / "runs" / f"{run_id}.jsonl"
                    append_record(event_path, _run_meta(run_id, scenario.id, scenario.group, variant, repeat, segment, config_path))
                    command = [
                        sys.executable, str(Path(__file__).resolve()), "--child",
                        "--scenario-file", str(scenario_path.resolve()), "--config", str(config_path),
                        "--variant", variant, "--run-id", run_id,
                        "--session-id", f"sess_eval_{run_id}", "--events-path", str(event_path),
                    ]
                    if segment is not None:
                        command.extend(("--segment", segment.id))
                    if number == 0:
                        command.append("--apply-setup")
                    if args.transcript:
                        command.extend(("--transcript-path", str(instance / "transcripts" / f"{run_id}.md")))
                    started = time.perf_counter()
                    failure: str | None = None
                    try:
                        timeout = args.run_timeout_seconds or scenario.step_timeout_seconds * len(
                            segment.steps if segment is not None else scenario.steps
                        ) * 2
                        subprocess.run(command, cwd=instance, check=True, timeout=timeout)
                    except subprocess.TimeoutExpired:
                        failure = "timeout"
                    except subprocess.CalledProcessError:
                        failure = "child_failed"
                    archived = finalize_run(
                        instance, run_id, PROJECT_ROOT / "data" / "evals",
                        duration_ms_total=int((time.perf_counter() - started) * 1000),
                        transcript=args.transcript, group=scenario.group, failure_reason=failure,
                        remove_instance=number == len(segments) - 1 and not args.keep_instances,
                    )
                    result_failure = failure or _archived_run_failure_reason(archived)
                    if archived is None:
                        result_failure = result_failure or "no_artifact"
                    any_failed = any_failed or result_failure is not None
                    print(
                        f"{scenario.id} {variant} r{repeat}: "
                        f"{result_failure or 'ok'} {archived or 'no_artifact'}"
                    )
    return 1 if any_failed else 0


def _run_child(args: argparse.Namespace) -> int:
    from src.evaluation.child import execute_segment
    from src.evaluation.records import append_record
    from src.evaluation.scenarios import load_scenario
    from src.main import bootstrap
    from src.observability.sinks import JsonlEventSink

    scenario = load_scenario(args.scenario_file)
    segment = next((item for item in scenario.runs if item.id == args.segment), None)
    if scenario.runs and segment is None:
        raise SystemExit("multi-run scenario requires a valid --segment")
    app = bootstrap(args.config, event_sink_override=JsonlEventSink(args.events_path), run_id_override=args.run_id)
    try:
        append_record(Path(args.events_path), _tool_catalog_snapshot(app))
        execute_segment(
            app, scenario, segment, args.variant, args.session_id, Path(args.events_path),
            setup=scenario.setup if args.apply_setup else (),
            transcript_path=Path(args.transcript_path) if args.transcript_path else None,
        )
    finally:
        app.shutdown()
    return 0


def _tool_catalog_snapshot(app: object) -> dict[str, object]:
    import json

    from src.core.tool_validation import render_tool_catalog

    backend = app.executor.tool_backend  # type: ignore[attr-defined]
    tools = backend.list_tools()
    capabilities = backend.list_capabilities()
    capability_payload = [
        {"capability_id": item.capability_id, "summary": item.summary}
        for item in capabilities
    ]
    capability_bytes = len(json.dumps(
        capability_payload, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8"))
    return {
        "type": "tool_catalog_snapshot",
        "tool_count": len(tools),
        "tool_catalog_bytes": len(render_tool_catalog(tools).encode("utf-8")),
        "capability_count": len(capabilities),
        "capability_catalog_bytes": capability_bytes,
    }


def _select_scenarios(directory: Path, scenario_id: str | None, all_scenarios: bool) -> list[Path]:
    paths = sorted(directory.glob("*.toml"))
    if all_scenarios:
        return paths
    selected = [path for path in paths if path.stem == scenario_id]
    if not selected:
        raise SystemExit(f"scenario not found: {scenario_id}")
    return selected


def _requires_cloud(scenario: object, variant: str) -> bool:
    if variant in {"cloud_assisted", "cloud_auto"}:
        return True
    steps = getattr(scenario, "steps", ())
    runs = getattr(scenario, "runs", ())
    all_steps = [*steps, *(step for run in runs for step in run.steps)]
    return any(getattr(step, "text", "").strip().startswith("/cloud ask ") for step in all_steps)


def _cloud_enabled_for_scenario(scenario: object, variant: str) -> bool:
    """Return whether a scenario requires a cloud-capable evaluation instance."""

    if variant in {"local_only", "round1", "round4", "embedding_none"}:
        return False
    if _requires_cloud(scenario, variant):
        return True
    return getattr(scenario, "group", "") == "g3_autonomy"


def _cloud_key_present(config_path: str | Path) -> bool:
    text = Path(config_path).read_text(encoding="utf-8")
    config = tomllib.loads(text.replace("{{CAPABILITY_ROUTING_ENABLED}}", "true"))
    cloud = config.get("cloud_advisory", {})
    if not isinstance(cloud, dict):
        return False
    provider = cloud.get("provider", cloud.get("backend", "noop"))
    if not isinstance(provider, str):
        return False
    credential_env = {
        "deepseek": "LOCALMIND_DEEPSEEK_API_KEY",
        "glm": "LOCALMIND_GLM_API_KEY",
        "custom_openai": "LOCALMIND_CUSTOM_OPENAI_API_KEY",
    }.get(provider)
    if credential_env is None:
        return False
    if os.environ.get(credential_env, "").strip():
        return True
    return provider == "deepseek" and bool(
        os.environ.get("LOCALMIND_CLOUD_API_KEY", "").strip()
    )


def _archived_run_failure_reason(path: Path | None) -> str | None:
    """Read the metadata-only summary and report structural run failure."""

    if path is None:
        return None
    from src.evaluation.records import read_records

    summary = next(
        (record for record in reversed(read_records(path)) if record.get("type") == "run_summary"),
        None,
    )
    if summary is None:
        return "missing_summary"
    failure_reason = summary.get("failure_reason")
    if isinstance(failure_reason, str) and failure_reason:
        return failure_reason
    failed_steps = summary.get("failed_steps")
    if isinstance(failed_steps, int) and failed_steps > 0:
        return "expectation_failed"
    return None


def _run_meta(run_id: str, scenario_id: str, group: str, variant: str, repeat: int, segment: object, config_path: Path) -> dict[str, object]:
    from src.evaluation.config import config_snapshot

    snapshot = config_snapshot(config_path)
    return {"type": "run_meta", "run_id": run_id, "scenario_id": scenario_id, "group": group, "variant": variant, "repeat": repeat, "segment": getattr(segment, "id", None), "started_at": time.time(), "capability_routing": snapshot.get("capability_routing"), "config_snapshot": snapshot}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--first-round", action="store_true")
    parser.add_argument("--group", choices=("g0_basic", "g1_progressive", "g2_value", "g3_autonomy", "g4_capability", "g4"))
    parser.add_argument("--capability-off", action="store_true")
    parser.add_argument("--scenarios-dir", default=str(PROJECT_ROOT / "scenarios"))
    parser.add_argument("--scenario-file")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "eval.example.toml"))
    parser.add_argument(
        "--variant",
        default="auto",
        choices=(
            "auto",
            "both",
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
        ),
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--run-timeout-seconds", type=int, default=None)
    parser.add_argument("--run-id")
    parser.add_argument("--session-id")
    parser.add_argument("--events-path")
    parser.add_argument("--segment", default=None)
    parser.add_argument("--apply-setup", action="store_true")
    parser.add_argument("--transcript", action="store_true")
    parser.add_argument("--transcript-path")
    parser.add_argument("--keep-instances", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
