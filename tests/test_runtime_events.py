"""Runtime-event sink behavior and persistence privacy boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from src.core.schemas import ExecutionRecord, RuntimeEvent
from src.models.mock_backend import MockModelBackend
from src.observability.sinks import CompositeEventSink, JsonlEventSink, NoopEventSink


def _event(stage: str, data: dict[str, object], *, run_id: str = "run-a") -> RuntimeEvent:
    return RuntimeEvent(
        run_id=run_id,
        turn_id="turn-a",
        session_id="session-a",
        seq=1,
        ts="2026-09-11T00:00:00+00:00",
        stage=stage,
        level="detail",
        data=data,
    )


def test_jsonl_sink_writes_versioned_envelope_and_private_projection(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    sink = JsonlEventSink(path)

    sink.emit(
        _event(
            "topic_decision",
            {
                "relation": "new_topic",
                "topic_label": "C:/Users/alice/private-project",
                "referenced_topic": None,
                "project_id": "client-secret-project",
                "project_switched": True,
            },
        )
    )

    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["v"] == 1
    assert row["type"] == "runtime_event"
    assert row["event"]["stage"] == "topic_decision"
    assert row["event"]["data"]["relation"] == "new_topic"
    assert row["event"]["data"]["topic_label"].startswith("t_")
    assert row["event"]["data"]["project_id"].startswith("p_")
    assert "alice" not in path.read_text(encoding="utf-8")
    assert "client-secret-project" not in path.read_text(encoding="utf-8")


def test_jsonl_sink_counts_or_drops_model_derived_text(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    sink = JsonlEventSink(path)
    sink.emit(
        _event(
            "intent_final",
            {
                "rounds_used": 2,
                "final_state": "PARTIAL",
                "confidence": 0.6,
                "intent_type": "private custom request",
                "missing_info": ("secret one", "secret two"),
            },
        )
    )

    data = json.loads(path.read_text(encoding="utf-8"))["event"]["data"]
    assert data == {
        "rounds_used": 2,
        "final_state": "PARTIAL",
        "confidence": 0.6,
        "missing_info_count": 2,
    }


def test_jsonl_sink_persists_only_structured_p6d_observations(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    sink = JsonlEventSink(path)
    sink.emit(
        _event(
            "intent_final",
            {
                "rounds_used": 2,
                "final_state": "ALMOST",
                "confidence": 0.7,
                "intent_type": "private task",
                "missing_info": ("private missing fact",),
                "proposal_present": True,
                "should_consult": True,
                "expected_benefit": 0.8,
                "escalation_reason": "reasoning_complexity",
                "no_progress_detected": True,
                "stopped_early": True,
                "resolution_exhausted": False,
                "risk_draft": "sensitive",
                "risk_draft_resolution": "unrecognized",
                "risk_draft_raw": "private free-form risk text",
                "proposed_question": "must not persist",
            },
        )
    )
    sink.emit(
        _event(
            "dispatch_decision",
            {
                "action": "PLAN_LOCAL",
                "reason": "free text omitted",
                "requires_user_confirmation": False,
                "proposal_gate_result": "vetoed",
                "proposal_denied_reason": "cloud_disabled",
                "reference_guard_result": "triggered",
                "reference_guard_marker": "那个私密服务",
            },
        )
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["event"]["data"] == {
        "rounds_used": 2,
        "final_state": "ALMOST",
        "confidence": 0.7,
        "missing_info_count": 1,
        "proposal_present": True,
        "should_consult": True,
        "expected_benefit": 0.8,
        "escalation_reason": "reasoning_complexity",
        "no_progress_detected": True,
        "stopped_early": True,
        "resolution_exhausted": False,
        "risk_draft": "sensitive",
        "risk_draft_resolution": "unrecognized",
    }
    assert rows[1]["event"]["data"] == {
        "action": "PLAN_LOCAL",
        "requires_user_confirmation": False,
        "proposal_gate_result": "vetoed",
        "proposal_denied_reason": "cloud_disabled",
        "reference_guard_result": "triggered",
    }
    assert "private free-form risk text" not in path.read_text(encoding="utf-8")
    assert "那个私密服务" not in path.read_text(encoding="utf-8")


def test_jsonl_aliases_are_stable_within_sink_and_random_across_sinks(tmp_path: Path) -> None:
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"
    first = JsonlEventSink(first_path)
    second = JsonlEventSink(second_path)
    event = _event(
        "turn_started",
        {"input_chars": 4, "project_id": "project-a", "explicit_directives": ()},
    )

    first.emit(event)
    first.emit(event)
    second.emit(event)

    first_rows = [json.loads(line) for line in first_path.read_text(encoding="utf-8").splitlines()]
    second_row = json.loads(second_path.read_text(encoding="utf-8"))
    alias = first_rows[0]["event"]["data"]["project_id"]
    assert first_rows[1]["event"]["data"]["project_id"] == alias
    assert second_row["event"]["data"]["project_id"] != alias


def test_composite_continues_after_a_member_raises() -> None:
    received: list[RuntimeEvent] = []

    class BrokenSink:
        def emit(self, event: RuntimeEvent) -> None:
            raise OSError("disk unavailable")

    class RecordingSink:
        def emit(self, event: RuntimeEvent) -> None:
            received.append(event)

    event = _event("memory_retrieval", {"query_source": "main", "hits": 0,
                                        "kw_enabled": True, "vec_enabled": False,
                                        "degraded": False})
    CompositeEventSink((BrokenSink(), RecordingSink())).emit(event)
    NoopEventSink().emit(event)

    assert received == [event]


def test_app_tool_event_persists_delivery_only_when_present(tmp_path: Path) -> None:
    from src.main import bootstrap

    path = tmp_path / "events.jsonl"
    app = bootstrap("config/default.toml", model_backend_override=MockModelBackend())
    app.event_sink = JsonlEventSink(path)
    app._record_tool_events([
        ExecutionRecord(
            tool_name="document.read", verdict="allowed", risk_level="sensitive",
            outcome="success", sanitized_summary="returned fields: segments",
            result_delivery="model_summary",
        ),
        ExecutionRecord(
            tool_name="file.read", verdict="allowed", risk_level="sensitive",
            outcome="success", sanitized_summary="returned fields: content",
        ),
    ])

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["event"]["data"]["result_delivery"] == "model_summary"
    assert "result_delivery" not in rows[1]["event"]["data"]
