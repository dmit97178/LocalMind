"""Shared data structures for core flows and adapter boundaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


class LocalMindError(Exception):
    """Base error for all LocalMind failures."""

    def __init__(
        self,
        code: str,
        message: str,
        user_message: str,
        recoverable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.user_message = user_message
        self.recoverable = recoverable
        self.details = details


class ModelError(LocalMindError):
    """Model backend failure."""


class SafetyDenied(LocalMindError):
    """Safety policy denied an operation."""


class ToolError(LocalMindError):
    """Tool execution failure."""


@dataclass(frozen=True)
class Result(Generic[T]):
    """Recoverable operation result."""

    value: T | None = None
    error: LocalMindError | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.error is None):
            raise ValueError("Result requires exactly one of value or error")

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_err(self) -> bool:
        return self.error is not None

    @staticmethod
    def ok(value: T) -> Result[T]:
        return Result(value=value)

    @staticmethod
    def err(error: LocalMindError) -> Result[T]:
        return Result(error=error)


@dataclass(frozen=True)
class ModelCapabilities:
    """Capability declaration provided by a loaded model adapter."""

    supports_structured_output: bool
    max_context_tokens: int
    local_only: bool


@dataclass(frozen=True)
class MemoryChunk:
    """A retrieved memory fragment."""

    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    similarity_score: float = 0.0
    vector_score: float | None = None
    match_source: str = "keyword"


@dataclass(frozen=True)
class ParamInstanceCheck:
    """Tool-owned predicate for deciding whether a value is a valid parameter instance."""

    predicate: Callable[[str], bool]
    reject_whole_input: bool = False


@dataclass(frozen=True)
class ToolDef:
    """Tool definition exposed by a tool backend."""

    name: str
    description: str
    parameters: dict = field(hash=False)
    risk_level: str = "normal"
    approval_profile: str = "standard"
    supply_by_echo: tuple[str, ...] = ()
    audit_redact_all_params: bool = False
    param_instance_checks: Mapping[str, ParamInstanceCheck] = field(
        default_factory=dict,
        hash=False,
    )
    egress: bool = False
    result_delivery: str = "deterministic"


@dataclass(frozen=True)
class ToolCandidate:
    """Minimal external tool self-report used only for compatibility checks."""

    raw_name: str
    input_schema: Mapping[str, object] = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class ProviderSnapshot:
    """One provider handshake result; external text is deliberately excluded."""

    provider_id: str
    healthy: bool
    candidates: tuple[ToolCandidate, ...] = ()
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.healthy and self.candidates:
            raise ValueError("an unhealthy provider snapshot cannot expose candidates")


@dataclass(frozen=True)
class ExternalToolAdmission:
    """Local, authoritative admission record for one external tool."""

    provider_id: str
    raw_name: str
    alias: str
    description: str
    parameters: Mapping[str, object]
    risk_level: str = ""
    side_effect_class: str = ""
    approval_profile: str = "standard"
    supply_by_echo: tuple[str, ...] = ()
    param_instance_checks: Mapping[str, ParamInstanceCheck] = field(
        default_factory=dict,
        hash=False,
    )


@dataclass(frozen=True)
class ToolCapability:
    """One user-facing capability backed by registered tool names."""

    capability_id: str
    summary: str
    tools: tuple[str, ...]


@dataclass(frozen=True)
class ToolCallDraft:
    """One model-proposed local tool call before planning."""

    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolContext:
    """Runtime context supplied to a registered tool handler."""

    workspace_root: Path
    tool_def: ToolDef


@dataclass(frozen=True)
class PreflightReport:
    """Side-effect-free risk assessment for a tool call or plan."""

    effective_risk: str
    requires_confirmation: bool
    target_exists: bool | None = None
    target_key: str | None = None
    reason: str | None = None
    approval_profile: str = "standard"


@dataclass(frozen=True)
class RetrievalStats:
    """Metadata-only snapshot of one memory retrieval."""

    hits: int
    kw_enabled: bool
    vec_enabled: bool
    degraded: bool


@dataclass(frozen=True)
class RoundTrace:
    """Metadata-only snapshot of one progressive intent round."""

    round: int
    state: str
    model_confidence: float
    missing_info: tuple[str, ...]
    continue_retrieval: bool
    retrieval: RetrievalStats | None = None
    new_memories: int = 0


@dataclass(frozen=True)
class RuntimeEvent:
    """Sanitized runtime event emitted by the application orchestrator."""

    run_id: str
    turn_id: str | None
    session_id: str
    seq: int
    ts: str
    stage: str
    level: str
    data: Mapping[str, object]


@dataclass(frozen=True)
class SafetyVerdict:
    """Safety backend decision for one operation."""

    allowed: bool
    risk_level: str
    reason: str


@dataclass(frozen=True)
class PreparedContextItem:
    """Locally redacted context item eligible for a bounded cloud grant."""

    category: str
    label: str
    value: str | int | float | bool
    redacted: bool
    fingerprint: str


@dataclass(frozen=True)
class PrivacyDenial:
    """Minimal record of a rejected context candidate, without its raw value."""

    category: str
    label: str
    reason: str


@dataclass(frozen=True)
class PrivacyPreparation:
    """Reduced and redacted candidates awaiting a bounded authorization grant."""

    candidates: list[PreparedContextItem]
    denied: list[PrivacyDenial]
    required_categories: frozenset[str]
    prepared_context_bytes: int


@dataclass(frozen=True)
class TaskBrief:
    """Locally assembled, field-redacted minimum task context for cloud reasoning."""

    goal: str
    constraints: str
    known_facts: str
    evidence: str
    attempts: str
    question: str
    unknowns: tuple[str, ...] = ()
    project_note: str = ""


@dataclass(frozen=True)
class CloudRequestPackage:
    """Locally authorized package. Boundary fields must never be serialized by adapters."""

    task_id: str
    session_id: str
    provider: str
    purpose: str
    grant_id: str
    context_items: list[PreparedContextItem]
    allowed_scope: str
    turn: int

    @property
    def context_bytes(self) -> int:
        """Return the canonical UTF-8 JSON size of outbound context items."""

        import json

        payload = [
            {
                "category": item.category,
                "label": item.label,
                "value": item.value,
                "redacted": item.redacted,
            }
            for item in self.context_items
        ]
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


@dataclass(frozen=True)
class AdvisoryResult:
    """Cloud advisory response. It is always advisory, never executable."""

    analysis: str
    suggested_tools: list | None = None
    risks: list = field(default_factory=list)
    requires_local_validation: bool = True
    needs_more_info: bool = False
    requested_context_categories: tuple[str, ...] = ()
    followup_question: str = ""


@dataclass(frozen=True)
class ConsultOutcome:
    """Completion or authorization suspension from one cloud consultation."""

    status: str
    result: AdvisoryResult | None = None
    requested_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class Experience:
    """Candidate experience extracted from a completed task."""

    id: str
    task_type: str
    content: str
    confidence: float
    status: str = "draft"


@dataclass(frozen=True)
class Skill:
    """Reusable skill metadata managed by the evolution backend."""

    id: str
    name: str
    trigger_condition: str
    steps: list = field(default_factory=list)
    status: str = "draft"
    maturity: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InputEvent:
    """Normalized user input entering the core loop."""

    text: str
    session_id: str
    timestamp: str
    source: str = "cli"
    project_id: str | None = None


@dataclass(frozen=True)
class IntentCandidate:
    """Model-produced intent candidate consumed by ControlPolicy."""

    state: str = "VAGUE"
    intent_type: str = "unknown"
    entities: dict = field(default_factory=dict)
    missing_info: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    risk_draft: str = "normal"
    model_confidence: float = 0.0
    reasoning: str = ""
    consultation_proposal: ConsultationProposal | None = None
    risk_draft_resolution: str = "declared"
    tool_intent: str = "none"
    tool_call: ToolCallDraft | None = None
    tool_call_resolution: str = "absent"
    tool_intent_conflict: bool = False
    capability_id: str | None = None
    capability_resolution: str = "absent"
    param_instance_rejected: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextCandidate:
    """Untrusted model-proposed context for a possible cloud consultation."""

    category: str
    label: str
    value: object
    source: str = "model_proposed"


@dataclass(frozen=True)
class ConsultationProposal:
    """Local model suggestion only; it cannot authorize or invoke cloud access."""

    should_consult: bool
    escalation_reason: str
    expected_benefit: float
    proposed_question: str = ""
    local_attempts_summary: str = ""
    candidate_context: list[ContextCandidate] = field(default_factory=list)
    reasoning: str = ""


@dataclass(frozen=True)
class MinimalContext:
    """Minimal context assembled for one model call."""

    system_prompt: str
    current_input: str = ""
    relevant_history: list[str] = field(default_factory=list)
    project_state: dict | None = None
    tool_defs: tuple[ToolDef, ...] = ()
    project_id: str | None = None
    capabilities: tuple[ToolCapability, ...] | None = None


@dataclass(frozen=True)
class ProjectState:
    """Validated project-level memory state."""

    project_id: str
    title: str
    goal: str
    constraints: tuple[str, ...]
    status: str
    summary: str
    topic_tags: tuple[str, ...]
    manual_overrides: frozenset[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TopicDecision:
    """Topic and project routing outcome for one normalized input."""

    session_id: str
    relation: str
    topic_label: str
    referenced_topic: str | None
    project_id: str | None
    project_switched: bool


@dataclass(frozen=True)
class NextAction:
    """Deterministic ControlPolicy decision."""

    action: str
    reason: str
    requires_user_confirmation: bool = False


@dataclass(frozen=True)
class ExecutionStep:
    """One local tool step in an execution plan."""

    tool_name: str
    action: str
    params: dict = field(default_factory=dict)
    risk_level: str = "normal"
    intent_type: str = "unknown"
    entities: dict = field(default_factory=dict)
    user_input: str = ""
    gate23_passed: bool = False
    approval_profile: str = "standard"


@dataclass(frozen=True)
class ExecutionPlan:
    """Local-only execution plan generated after policy approval."""

    steps: list[ExecutionStep] = field(default_factory=list)


@dataclass(frozen=True)
class ResponseOutput:
    """Separate display text from the memory-safe narrative of a tool response."""

    display: str
    narrative_reply: str


@dataclass(frozen=True)
class ExecutionRecord:
    """The only tool-result representation permitted in P5 memory."""

    tool_name: str
    verdict: str
    risk_level: str
    outcome: str
    sanitized_summary: str
    error_code: str | None = None
    result_delivery: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    """Audit record for guarded side-effect operations."""

    audit_id: str
    task_id: str
    intent_id: str
    tool_name: str
    params_redacted: dict
    risk_level: str
    verdict: str
    reason: str
    timestamp: str


@dataclass(frozen=True)
class CloudAuditEvent:
    """Auditable record for one protected cloud advisory turn."""

    audit_id: str
    task_id: str
    session_id: str
    intent_id: str
    turn: int
    provider: str
    purpose: str
    grant_id: str
    issued_by: str
    authorized_categories: list[str]
    context_items: list[dict]
    package_context_items: int
    package_context_bytes: int
    consumed_turns: int
    cooldown_until: float | None
    verdict: str
    reason: str
    requested_context_categories: tuple[str, ...] = ()
    has_followup: bool = False
    timestamp: str = ""
