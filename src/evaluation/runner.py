"""Pure P6b step driving and metadata-only structural summaries."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from src.evaluation.scenarios import Scenario


class EvaluationApp(Protocol):
    def handle(self, text: str, session_id: str, project_id: str | None = None) -> str: ...
    def end_session(self, session_id: str) -> None: ...
    def last_turn_report(self) -> dict[str, object] | None: ...


def drive_steps(
    app: EvaluationApp,
    scenario: Scenario,
    variant: str,
    session_id: str,
    *,
    event_log_path: Path | None = None,
    on_step: Callable[[str, str, dict[str, object] | None], None] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Drive scenario steps through App and retain only structural evaluation data."""

    results: list[dict[str, object]] = []
    rounds_used: list[int] = []
    actions: list[str] = []
    for index, step in enumerate(scenario.steps):
        base = {
            "type": "step_result",
            "step_index": index,
            "kind": step.kind,
            "prelude": step.prelude,
            "when_variant": step.when_variant or None,
            "when_state": step.when_state or None,
            "on_unmet": step.on_unmet if step.when_state else None,
        }
        if step.when_variant and step.when_variant != variant:
            results.append({**base, "skipped_reason": "when_variant", "ok": True})
            continue
        prior_events = _read_event_lines(event_log_path)
        if step.when_state and not _state_is_active(step.when_state, prior_events):
            if step.on_unmet == "skip":
                results.append({**base, "skipped_reason": "when_state", "ok": True})
            else:
                results.append({**base, "ok": False, "fail_reason": "when_state_unmet"})
            continue

        text = _render_step_text(step.text, step.cloud_ask, variant)
        started = time.perf_counter()
        if step.kind == "slash" and text == "/quit":
            app.end_session(session_id)
            reply = "会话已结束，摘要已保存。"
            report: dict[str, object] | None = None
        else:
            reply = app.handle(text, session_id)
            report = app.last_turn_report()
        duration_ms = int((time.perf_counter() - started) * 1000)
        record: dict[str, object] = {
            **base,
            "input_chars": len(text),
            "reply_chars": len(reply),
            "ok": True,
            "duration_ms": duration_ms,
        }
        if report is not None:
            rounds = report.get("rounds_used")
            action = report.get("action")
            if isinstance(rounds, int):
                record["rounds_used"] = rounds
                if not step.prelude:
                    rounds_used.append(rounds)
            if isinstance(action, str) and action:
                record["action"] = action
                if not step.prelude:
                    actions.append(action)
            error_code = report.get("error_code")
            if isinstance(error_code, str) and error_code:
                record["error_code"] = error_code
                record["ok"] = False
        current_events = _read_event_lines(event_log_path)[len(prior_events) :]
        failures = _expectation_failures(step.expect, reply, current_events)
        if failures:
            record["ok"] = False
            record["fail_reason"] = failures[0]
        if on_step is not None:
            on_step(text, reply, report)
        results.append(record)
    return results, {
        "total_turns": sum(
            1 for result in results if not result["prelude"] and "skipped_reason" not in result
        ),
        "rounds_used": rounds_used,
        "actions": actions,
    }


def _render_step_text(text: str, cloud_ask: bool, variant: str) -> str:
    if cloud_ask and variant == "cloud_assisted":
        return f"/cloud ask {text}"
    return text


def _read_event_lines(path: Path | None) -> list[dict[str, object]]:
    if path is None or not path.exists():
        return []
    lines: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        try:
            parsed = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            lines.append(parsed)
    return lines


def _state_is_active(state: str, event_lines: list[dict[str, object]]) -> bool:
    if state != "awaiting_cloud_authorization":
        return False
    for line in reversed(event_lines):
        event = _runtime_event(line)
        if event is None:
            continue
        if event.get("stage") != "cloud_consult":
            continue
        data = event.get("data")
        if isinstance(data, dict):
            return data.get("phase") == "authorization_required"
    return False


def _expectation_failures(
    expect: dict[str, object] | None, reply: str, event_lines: list[dict[str, object]]
) -> list[str]:
    if expect is None:
        return []
    events = [event for line in event_lines if (event := _runtime_event(line)) is not None]
    failures: list[str] = []
    rounds: list[int] = []
    for event in events:
        data = event.get("data")
        if event.get("stage") != "turn_completed" or not isinstance(data, dict):
            continue
        value = data.get("rounds_used")
        if isinstance(value, int):
            rounds.append(value)
    latest_rounds = rounds[-1] if rounds else 0
    rounds_min = expect.get("rounds_min")
    if isinstance(rounds_min, int) and latest_rounds < rounds_min:
        failures.append("rounds_min")
    rounds_max = expect.get("rounds_max")
    if isinstance(rounds_max, int) and latest_rounds > rounds_max:
        failures.append("rounds_max")
    actions = {
        data.get("action")
        for event in events
        if event.get("stage") == "dispatch_decision"
        if isinstance(data := event.get("data"), dict) and isinstance(data.get("action"), str)
    }
    required_actions = expect.get("action_any")
    if isinstance(required_actions, list) and not actions.intersection(required_actions):
        failures.append("action_any")
    forbidden_actions = expect.get("action_none")
    if isinstance(forbidden_actions, list) and actions.intersection(forbidden_actions):
        failures.append("action_none")
    confirmations = any(
        isinstance(data := event.get("data"), dict)
        and data.get("requires_user_confirmation") is True
        for event in events
        if event.get("stage") == "dispatch_decision"
    )
    if "confirmation_required" in expect and confirmations is not expect["confirmation_required"]:
        failures.append("confirmation_required")
    tools = {
        data.get("tool_name")
        for event in events
        if event.get("stage") == "tool_execution"
        if isinstance(data := event.get("data"), dict) and isinstance(data.get("tool_name"), str)
    }
    required_tools = expect.get("tool_any")
    if isinstance(required_tools, list) and not tools.intersection(required_tools):
        failures.append("tool_any")
    if "tool_none" in expect:
        expect_none = expect["tool_none"]
        if expect_none is True and tools:
            failures.append("tool_none")
        if expect_none is False and not tools:
            failures.append("tool_none")
    required_delivery = expect.get("result_delivery_any")
    if isinstance(required_delivery, list):
        deliveries = {
            data.get("result_delivery")
            for event in events
            if event.get("stage") == "tool_execution"
            if isinstance(data := event.get("data"), dict)
            and isinstance(data.get("result_delivery"), str)
        }
        if not deliveries.intersection(required_delivery):
            failures.append("result_delivery_any")
    cloud_seen = any(event.get("stage") == "cloud_consult" for event in events)
    if "cloud_any" in expect and cloud_seen is not expect["cloud_any"]:
        failures.append("cloud_any")
    reintegrated = any(
        isinstance(data := event.get("data"), dict) and data.get("local_reintegrate") is True
        for event in events
        if event.get("stage") == "cloud_return"
    )
    if "local_reintegrate" in expect and reintegrated is not expect["local_reintegrate"]:
        failures.append("local_reintegrate")
    retrieval_hits = sum(
        data.get("hits", 0)
        for event in events
        if event.get("stage") == "memory_retrieval"
        if isinstance(data := event.get("data"), dict)
        and data.get("query_source") == "main"
        and isinstance(data.get("hits"), int)
    )
    required_hits = expect.get("retrieval_hits_min")
    if isinstance(required_hits, int) and retrieval_hits < required_hits:
        failures.append("retrieval_hits_min")
    degradation_seen = any(event.get("stage") == "degradation" for event in events)
    if "degradation_any" in expect and degradation_seen is not expect["degradation_any"]:
        failures.append("degradation_any")
    guard_results = [
        data["reference_guard_result"]
        for event in events
        if event.get("stage") == "dispatch_decision"
        if isinstance(data := event.get("data"), dict)
        and data.get("reference_guard_result")
        in {"not_evaluated", "not_triggered", "triggered"}
    ]
    if "reference_guard_any" in expect:
        evaluated = [value for value in guard_results if value != "not_evaluated"]
        triggered = "triggered" in evaluated
        if not evaluated or triggered is not expect["reference_guard_any"]:
            failures.append("reference_guard_any")
    required_capabilities = expect.get("capability_any")
    if isinstance(required_capabilities, list):
        resolutions = {
            data.get("capability_resolution")
            for event in events
            if event.get("stage") == "intent_final"
            if isinstance(data := event.get("data"), dict)
        }
        if not resolutions.intersection(required_capabilities):
            failures.append("capability_any")
    output_contains = expect.get("output_contains")
    if isinstance(output_contains, str) and output_contains not in reply:
        failures.append("output_contains")
    output_not_contains = expect.get("output_not_contains")
    if isinstance(output_not_contains, list) and any(
        value in reply for value in output_not_contains
    ):
        failures.append("output_not_contains")
    return failures


def _runtime_event(line: dict[str, object]) -> dict[str, object] | None:
    event = line.get("event") if line.get("type") == "runtime_event" else None
    return event if isinstance(event, dict) else None


def summarize_run(
    event_lines: list[dict[str, object]],
    step_results: list[dict[str, object]],
    *,
    duration_ms_total: int,
) -> dict[str, object]:
    """Build the P6b run summary from already privacy-projected event envelopes."""

    rounds_used: list[int] = []
    actions: list[str] = []
    confirmations = 0
    cloud_upgrades = 0
    cloud_denials = 0
    cloud_outbound_bytes = 0
    categories: set[str] = set()
    tools = {"executed": 0, "denied": 0}
    result_deliveries: dict[str, int] = {}
    degradations: list[str] = []
    proposal_gate_results: dict[str, int] = {}
    proposal_denied_reasons: dict[str, int] = {}
    cloud_denied_reasons: dict[str, int] = {}
    reference_guard_results: dict[str, int] = {}
    should_consult_results = {"true": 0, "false": 0}
    risk_draft_results: dict[str, int] = {}
    risk_draft_resolution_results: dict[str, int] = {}
    reply_provenance_results: dict[str, int] = {}
    tool_call_resolution_results: dict[str, int] = {}
    capability_resolution_results: dict[str, int] = {}
    capability_id_results: dict[str, int] = {}
    suggested_tools_count_results: dict[str, int] = {}
    tool_signal_comparison = {
        "both": 0,
        "tool_call_only": 0,
        "suggested_tools_only": 0,
        "neither": 0,
    }
    latest_final_state = ""
    latest_missing_info_count = 0
    latest_action = ""
    latest_guard_result = "not_evaluated"
    latest_risk_draft = ""
    sensitive_proposal_admitted = 0
    no_progress_detected = 0
    stopped_early = 0
    resolution_exhausted = 0
    resolution_exhausted_actions: dict[str, dict[str, int]] = {}
    pending_resolution_exhausted = False
    cloud_authorization_required = 0
    unauthorized_outbound = 0
    authorization_seen = False
    for line in event_lines:
        event = line.get("event") if line.get("type") == "runtime_event" else None
        if not isinstance(event, dict):
            continue
        stage = event.get("stage")
        data = event.get("data")
        if not isinstance(stage, str) or not isinstance(data, dict):
            continue
        if stage == "turn_completed":
            rounds = data.get("rounds_used")
            if isinstance(rounds, int):
                rounds_used.append(rounds)
            if data.get("had_confirmation") is True:
                confirmations += 1
            provenance = data.get("reply_provenance")
            if isinstance(provenance, str):
                reply_provenance_results[provenance] = (
                    reply_provenance_results.get(provenance, 0) + 1
                )
        elif stage == "dispatch_decision":
            action = data.get("action")
            if isinstance(action, str):
                actions.append(action)
                latest_action = action
            gate_result = data.get("proposal_gate_result")
            if isinstance(gate_result, str):
                proposal_gate_results[gate_result] = proposal_gate_results.get(gate_result, 0) + 1
                if gate_result == "admitted_proposal" and latest_risk_draft == "sensitive":
                    sensitive_proposal_admitted += 1
            if pending_resolution_exhausted and isinstance(action, str):
                gate_key = gate_result if isinstance(gate_result, str) else "unknown"
                action_counts = resolution_exhausted_actions.setdefault(gate_key, {})
                action_counts[action] = action_counts.get(action, 0) + 1
                pending_resolution_exhausted = False
            denied_reason = data.get("proposal_denied_reason")
            if isinstance(denied_reason, str) and denied_reason != "none":
                proposal_denied_reasons[denied_reason] = (
                    proposal_denied_reasons.get(denied_reason, 0) + 1
                )
            guard_result = data.get("reference_guard_result")
            if isinstance(guard_result, str):
                reference_guard_results[guard_result] = (
                    reference_guard_results.get(guard_result, 0) + 1
                )
                latest_guard_result = guard_result
        elif stage == "intent_final":
            capability_resolution = data.get("capability_resolution")
            if isinstance(capability_resolution, str):
                capability_resolution_results[capability_resolution] = (
                    capability_resolution_results.get(capability_resolution, 0) + 1
                )
            capability_id = data.get("capability_id")
            if isinstance(capability_id, str):
                capability_id_results[capability_id] = capability_id_results.get(capability_id, 0) + 1
            final_state = data.get("final_state")
            if isinstance(final_state, str):
                latest_final_state = final_state
            missing_count = data.get("missing_info_count")
            if isinstance(missing_count, int):
                latest_missing_info_count = missing_count
            should_consult = data.get("should_consult")
            if isinstance(should_consult, bool):
                key = "true" if should_consult else "false"
                should_consult_results[key] += 1
            if data.get("no_progress_detected") is True:
                no_progress_detected += 1
            if data.get("stopped_early") is True:
                stopped_early += 1
            pending_resolution_exhausted = data.get("resolution_exhausted") is True
            if pending_resolution_exhausted:
                resolution_exhausted += 1
            risk_draft = data.get("risk_draft")
            if isinstance(risk_draft, str):
                latest_risk_draft = risk_draft
                risk_draft_results[risk_draft] = risk_draft_results.get(risk_draft, 0) + 1
            resolution = data.get("risk_draft_resolution")
            if isinstance(resolution, str):
                risk_draft_resolution_results[resolution] = (
                    risk_draft_resolution_results.get(resolution, 0) + 1
                )
            tool_resolution = data.get("tool_call_resolution")
            suggested_count = data.get("suggested_tools_count")
            if isinstance(tool_resolution, str):
                tool_call_resolution_results[tool_resolution] = (
                    tool_call_resolution_results.get(tool_resolution, 0) + 1
                )
            if isinstance(suggested_count, int) and suggested_count >= 0:
                key = str(suggested_count)
                suggested_tools_count_results[key] = (
                    suggested_tools_count_results.get(key, 0) + 1
                )
            if isinstance(tool_resolution, str) and isinstance(suggested_count, int):
                tool_call_present = tool_resolution == "resolved"
                suggested_present = suggested_count > 0
                comparison = (
                    "both" if tool_call_present and suggested_present
                    else "tool_call_only" if tool_call_present
                    else "suggested_tools_only" if suggested_present
                    else "neither"
                )
                tool_signal_comparison[comparison] += 1
        elif stage == "cloud_consult":
            phase = data.get("phase")
            if phase == "authorization_required":
                cloud_authorization_required += 1
                authorization_seen = True
            elif phase == "outbound":
                cloud_upgrades += 1
                if not authorization_seen:
                    unauthorized_outbound += 1
                authorization_seen = False
                outbound_bytes = data.get("outbound_bytes")
                if isinstance(outbound_bytes, int):
                    cloud_outbound_bytes += outbound_bytes
                outbound_categories = data.get("outbound_categories")
                if isinstance(outbound_categories, (list, tuple)):
                    categories.update(item for item in outbound_categories if isinstance(item, str))
            elif phase == "denied":
                cloud_denials += 1
                denied_reason = data.get("denied_reason")
                if isinstance(denied_reason, str):
                    cloud_denied_reasons[denied_reason] = (
                        cloud_denied_reasons.get(denied_reason, 0) + 1
                    )
                authorization_seen = False
        elif stage == "tool_execution":
            if data.get("verdict") == "denied":
                tools["denied"] += 1
            elif data.get("verdict") == "allowed":
                tools["executed"] += 1
            delivery = data.get("result_delivery")
            if isinstance(delivery, str):
                result_deliveries[delivery] = result_deliveries.get(delivery, 0) + 1
        elif stage == "degradation":
            component = data.get("component")
            if isinstance(component, str) and component not in degradations:
                degradations.append(component)
    cloud: dict[str, object] = {
        "upgrades": cloud_upgrades,
        "denials": cloud_denials,
        "cooldowns": 0,
        "outbound_bytes": cloud_outbound_bytes,
        "outbound_categories": sorted(categories),
    }
    attribution = classify_s02_attribution(
        action=latest_action,
        final_state=latest_final_state,
        missing_info_count=latest_missing_info_count,
        reference_guard_result=latest_guard_result,
    )
    model_clarification_detected = (
        latest_final_state in {"VAGUE", "PARTIAL"} and latest_missing_info_count > 0
    )
    return {
        "type": "run_summary",
        "total_turns": sum(
            1
            for result in step_results
            if result.get("prelude") is False and "skipped_reason" not in result
        ),
        "rounds_used": rounds_used,
        "actions": actions,
        "questions_asked": actions.count("ASK_USER"),
        "confirmations": confirmations,
        "cloud": cloud,
        "tools": tools,
        "result_delivery_results": result_deliveries,
        "degradations": degradations,
        "capability_resolution_results": capability_resolution_results,
        "capability_id_results": capability_id_results,
        "proposal_gate_results": proposal_gate_results,
        "proposal_denied_reasons": proposal_denied_reasons,
        "cloud_denied_reasons": cloud_denied_reasons,
        "reference_guard_results": reference_guard_results,
        "s02_attribution": attribution,
        "model_asked_but_not_ask_user": (
            model_clarification_detected and latest_action != "ASK_USER"
        ),
        "should_consult_results": should_consult_results,
        "risk_draft_results": risk_draft_results,
        "risk_draft_resolution_results": risk_draft_resolution_results,
        "reply_provenance_results": reply_provenance_results,
        "tool_call_resolution_results": tool_call_resolution_results,
        "suggested_tools_count_results": suggested_tools_count_results,
        "tool_signal_comparison": tool_signal_comparison,
        "sensitive_proposal_admitted": sensitive_proposal_admitted,
        "no_progress_detected": no_progress_detected,
        "stopped_early": stopped_early,
        "resolution_exhausted": resolution_exhausted,
        "resolution_exhausted_actions": resolution_exhausted_actions,
        "cloud_authorization_required": cloud_authorization_required,
        "unauthorized_outbound": unauthorized_outbound,
        "duration_ms_total": duration_ms_total,
        "completed_steps": sum(result.get("ok") is True for result in step_results),
        "failed_steps": sum(result.get("ok") is False for result in step_results),
    }


def classify_s02_attribution(
    *,
    action: str,
    final_state: str,
    missing_info_count: int,
    reference_guard_result: str,
) -> str:
    """Classify model behavior separately from deterministic guard rescue."""

    model_asked = (
        action == "ASK_USER"
        and final_state in {"VAGUE", "PARTIAL"}
        and missing_info_count > 0
    )
    if model_asked:
        return "model_asked"
    if action == "ASK_USER" and reference_guard_result == "triggered":
        return "guard_rescued"
    if action == "ASK_USER":
        return "unattributed_ask"
    return "failed"
