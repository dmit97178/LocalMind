"""Parent-owned finalization for isolated P6b child-process runs."""

from __future__ import annotations

from pathlib import Path

from src.evaluation.artifacts import archive_run
from src.evaluation.records import append_record, read_records
from src.evaluation.runner import summarize_run


def finalize_run(
    instance_dir: Path,
    run_id: str,
    evals_dir: Path,
    *,
    duration_ms_total: int,
    transcript: bool,
    group: str | None = None,
    failure_reason: str | None = None,
    remove_instance: bool = True,
) -> Path | None:
    """Append the parent-owned summary, then archive this run's projection."""

    event_path = instance_dir / "runs" / f"{run_id}.jsonl"
    if not event_path.exists():
        return None
    records = read_records(event_path)
    step_results = [record for record in records if record.get("type") == "step_result"]
    summary = summarize_run(records, step_results, duration_ms_total=duration_ms_total)
    if failure_reason is not None:
        summary["failure_reason"] = failure_reason
        if summary["failed_steps"] == 0:
            summary["failed_steps"] = 1
    append_record(event_path, summary)
    if group in {"g0_basic", "g3_autonomy"}:
        append_record(event_path, _single_score_template(run_id))
    return archive_run(
        instance_dir,
        run_id,
        evals_dir,
        transcript=transcript,
        remove_instance=remove_instance,
    )


def _single_score_template(run_id: str) -> dict[str, object]:
    return {
        "type": "human_score",
        "kind": "single",
        "run_id": run_id,
        "scores": {
            "completeness": None,
            "question_quality": None,
            "topic_project_correctness": None,
            "retrieval_relevance": None,
            "escalation_necessity": None,
        },
        "notes": "",
        "scored_at": None,
    }
