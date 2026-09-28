"""Single-process P6b segment execution over the real application boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.core.memory_hygiene import sanitize_for_memory
from src.evaluation.records import append_record, read_records
from src.evaluation.runner import EvaluationApp, drive_steps
from src.evaluation.scenarios import Scenario, ScenarioRun, ScenarioSetup


def execute_segment(
    app: EvaluationApp,
    scenario: Scenario,
    segment: ScenarioRun | None,
    variant: str,
    session_id: str,
    event_path: Path,
    *,
    setup: tuple[ScenarioSetup, ...] = (),
    transcript_path: Path | None = None,
) -> dict[str, object]:
    """Drive one segment and append only its structural step records."""

    _apply_setup(app, setup)
    segment_scenario = scenario if segment is None else replace(scenario, steps=segment.steps)
    results, summary = drive_steps(
        app,
        segment_scenario,
        variant,
        session_id,
        event_log_path=event_path,
        on_step=_transcript_writer(transcript_path),
    )
    for result in results:
        append_record(event_path, result)
    return {
        **summary,
        "event_lines": read_records(event_path),
        "step_results": results,
    }


def _transcript_writer(path: Path | None):
    if path is None:
        return None

    def write(input_text: str, reply: str, report: dict[str, object] | None) -> None:
        reason = ""
        candidate_reason = report.get("reason") if isinstance(report, dict) else None
        if isinstance(candidate_reason, str):
            reason = candidate_reason
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("## 回合\n")
            stream.write(f"输入：{sanitize_for_memory(input_text)}\n\n")
            stream.write(f"回复：{sanitize_for_memory(reply)}\n\n")
            stream.write(f"决策理由：{sanitize_for_memory(reason)}\n\n")

    return write


def _apply_setup(app: EvaluationApp, setup: tuple[ScenarioSetup, ...]) -> None:
    """Use only assembled public collaborators to prepare an isolated instance."""

    for item in setup:
        values = item.values
        if item.kind == "episode":
            raw_metadata = values["metadata"]
            if not isinstance(raw_metadata, dict):
                raise RuntimeError("validated episode setup lost its metadata mapping")
            metadata = dict(raw_metadata)
            project_id = metadata.get("project_id")
            if isinstance(project_id, str) and not project_id.strip():
                metadata["project_id"] = None
            metadata.setdefault("session_id", values["session_id"])
            app.memory.store_episode(str(values["text"]), metadata)  # type: ignore[attr-defined]
        elif item.kind == "project":
            project_id = str(values["project_id"])
            app.projects.ensure(project_id)  # type: ignore[attr-defined]
            for field in ("title", "goal", "summary", "constraints", "status"):
                if field in values:
                    app.projects.set_manual(project_id, field, values[field])  # type: ignore[attr-defined]
        elif item.kind == "workspace_file":
            result = app.executor.tool_backend.execute(  # type: ignore[attr-defined]
                "file.write", {"path": values["path"], "content": values["content"]}
            )
            if result.is_err:
                raise result.error or RuntimeError("workspace setup failed")
        elif item.kind == "identity":
            app.id_verifier.set_passphrase(str(values["passphrase"]))  # type: ignore[attr-defined]
