"""Runtime-event sink implementations."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from src.core.interfaces import RuntimeEventSink
from src.core.schemas import RuntimeEvent

_PERSISTED_KEYS: dict[str, frozenset[str]] = {
    "turn_started": frozenset({"input_chars", "project_id", "explicit_directives"}),
    "topic_decision": frozenset(
        {"relation", "topic_label", "referenced_topic", "project_id", "project_switched"}
    ),
    "memory_retrieval": frozenset(
        {"query_source", "hits", "kw_enabled", "vec_enabled", "degraded"}
    ),
    "intent_round": frozenset(
        {"round", "state", "confidence", "missing_info", "continue_retrieval", "new_memories"}
    ),
    "intent_final": frozenset(
        {
            "rounds_used", "final_state", "confidence", "intent_type", "missing_info",
            "proposal_present", "should_consult", "expected_benefit", "escalation_reason",
            "no_progress_detected", "stopped_early", "resolution_exhausted", "risk_draft",
            "risk_draft_resolution",
            "tool_intent", "tool_call_resolution", "tool_intent_conflict",
            "suggested_tools_count",
            "capability_id", "capability_resolution", "param_instance_rejected",
        }
    ),
    "dispatch_decision": frozenset(
        {
            "action", "reason", "requires_user_confirmation", "proposal_gate_result",
            "proposal_denied_reason", "reference_guard_result",
        }
    ),
    "cloud_consult": frozenset(
        {
            "phase",
            "escalation_reason",
            "authorization",
            "outbound_categories",
            "outbound_bytes",
            "sub_turn",
            "denied_reason",
        }
    ),
    "cloud_return": frozenset(
        {"inbound_ok", "needs_more_info", "followup_flag", "local_reintegrate"}
    ),
    "tool_execution": frozenset(
        {"tool_name", "risk_level", "verdict", "outcome", "error_code", "result_delivery"}
    ),
    "degradation": frozenset({"component", "fallback"}),
    "turn_completed": frozenset(
        {
            "completion",
            "final_action",
            "rounds_used",
            "duration_ms",
            "had_confirmation",
            "had_cloud",
            "error_code",
            "reply_provenance",
        }
    ),
    "session_ended": frozenset({"summary_written"}),
}


class NoopEventSink(RuntimeEventSink):
    """Discard all events."""

    def emit(self, event: RuntimeEvent) -> None:
        return None


@dataclass
class JsonlEventSink(RuntimeEventSink):
    """Append privacy-reduced runtime events to a JSONL file."""

    path: str | Path
    _project_aliases: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _topic_aliases: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def emit(self, event: RuntimeEvent) -> None:
        try:
            projected = asdict(event)
            projected["data"] = self._project_data(event.stage, event.data)
            envelope = {"v": 1, "type": "runtime_event", "event": projected}
            path = Path(self.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
                stream.write("\n")
        except Exception:
            return None

    def _project_data(self, stage: str, data: object) -> dict[str, object]:
        if stage not in _PERSISTED_KEYS or not isinstance(data, Mapping):
            return {}
        source = dict(data)
        projected = {key: source[key] for key in _PERSISTED_KEYS[stage] if key in source}

        if stage == "turn_started":
            projected["project_id"] = self._alias(projected.get("project_id"), "project")
        elif stage == "topic_decision":
            projected["topic_label"] = self._alias(projected.get("topic_label"), "topic")
            projected["referenced_topic"] = self._alias(
                projected.get("referenced_topic"), "topic"
            )
            projected["project_id"] = self._alias(projected.get("project_id"), "project")
        elif stage == "intent_round":
            projected["missing_info_count"] = _count(projected.pop("missing_info", ()))
        elif stage == "intent_final":
            projected.pop("intent_type", None)
            projected["missing_info_count"] = _count(projected.pop("missing_info", ()))
        elif stage == "dispatch_decision":
            projected.pop("reason", None)
        return projected

    def _alias(self, value: object, kind: str) -> object:
        if value is None:
            return None
        raw = str(value)
        aliases = self._project_aliases if kind == "project" else self._topic_aliases
        prefix = "p_" if kind == "project" else "t_"
        return aliases.setdefault(raw, f"{prefix}{uuid4().hex[:6]}")


@dataclass
class CompositeEventSink(RuntimeEventSink):
    """Fan events out while isolating failures between members."""

    sinks: Iterable[RuntimeEventSink]

    def emit(self, event: RuntimeEvent) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception:
                continue


def _count(value: object) -> int:
    if isinstance(value, (str, bytes)):
        return 1
    try:
        return len(value)  # type: ignore[arg-type]
    except TypeError:
        return 0
