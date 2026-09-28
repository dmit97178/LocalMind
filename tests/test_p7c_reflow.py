"""P7c read-only tool result reflow contracts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.schemas import ExecutionPlan, ExecutionStep, ModelError, ToolDef, ToolError
from src.models.mock_backend import MockModelBackend
from src.safety.identity import IdentityVerifier


def _tool(name: str = "document.read", *, delivery: str = "model_summary") -> ToolDef:
    return ToolDef(
        name=name,
        description="Read a document.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        result_delivery=delivery,
    )


def _plan(*names: str) -> ExecutionPlan:
    return ExecutionPlan(
        [ExecutionStep(name, "read", {"path": f"{index}.md"}) for index, name in enumerate(names)]
    )


class FailingModel(MockModelBackend):
    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        raise ModelError("MODEL_TIMEOUT", "timeout", "timeout", recoverable=True)


def test_reflow_uses_one_model_call_for_all_successful_steps() -> None:
    from src.core.result_reflow import ResultReflow

    model = MockModelBackend(text_response="\x1b[31m摘要\x1b[0m\u200b")
    model.load()
    calls: list[str] = []
    original = model.generate

    def capture(prompt: str, response_schema: dict | None = None) -> dict:
        calls.append(prompt)
        return original(prompt, response_schema)

    model.generate = capture  # type: ignore[method-assign]
    plan = _plan("document.read", "document.read")
    result = ResultReflow(model, (_tool(),), enabled=True, max_chars=4000)(
        plan,
        {
            1: {"segments": [{"text": "second"}], "truncated": False},
            0: {"segments": [{"text": "first"}], "truncated": False},
        },
        "总结两份文档",
        "fallback",
    )

    assert "\x1b" not in result.display and "\u200b" not in result.display
    assert "摘要" in result.display
    assert result.deliveries == {0: "model_summary", 1: "model_summary"}
    assert len(calls) == 1
    assert calls[0].index("step_index: 0") < calls[0].index("step_index: 1")
    assert "总结两份文档" in calls[0]


def test_reflow_failure_returns_deterministic_display() -> None:
    from src.core.result_reflow import ResultReflow

    model = FailingModel()
    model.load()
    outcome = ResultReflow(model, (_tool(),), enabled=True, max_chars=4000)(
        _plan("document.read"),
        {0: {"segments": [{"text": "content"}]}},
        "总结",
        "deterministic",
    )

    assert outcome.display == "deterministic"
    assert outcome.deliveries == {0: "model_summary_failed"}


def test_reflow_is_noop_without_model_summary_steps() -> None:
    from src.core.result_reflow import ResultReflow

    model = MockModelBackend(text_response="must not be called")
    model.load()
    outcome = ResultReflow(
        model, (_tool("file.read", delivery="deterministic"),), enabled=True, max_chars=4000
    )(
        _plan("file.read"),
        {0: {"content": "hello"}},
        "读取",
        "unchanged",
    )

    assert outcome.display == "unchanged"
    assert outcome.deliveries == {}


@pytest.mark.parametrize(
    "tool",
    [
        replace(_tool(), result_delivery="invalid"),
        replace(_tool(), name="file.write"),
        replace(_tool(), egress=True),
    ],
)
def test_result_delivery_registration_is_fail_loud(tool: ToolDef) -> None:
    from src.tools.capabilities import validate_capabilities

    with pytest.raises(Exception) as caught:
        validate_capabilities((), (tool,), enabled=True, registered_tools=(tool,))

    assert getattr(caught.value, "code", None) == "CONFIG_ERROR"
    assert getattr(caught.value, "details", {}).get("reason") == "result_delivery_invalid"


def test_confirmation_reflow_uses_original_request_not_passphrase(tmp_path) -> None:
    from src.main import bootstrap

    (tmp_path / "notes.md").write_text("important document fact", encoding="utf-8")
    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "read_document",
            "entities": {"path": "notes.md"},
            "missing_info": [],
            "suggested_tools": ["document.read"],
            "tool_intent": "local_action",
            "tool_call": {
                "tool_name": "document.read",
                "arguments": {"path": "notes.md"},
            },
            "risk_draft": "normal",
            "model_confidence": 0.95,
            "reasoning": "read the requested document",
            "capability_id": "files.read",
        },
        text_response="文档摘要",
    )
    reflow_prompts: list[str] = []
    original_generate = model.generate

    def capture(prompt: str, response_schema: dict | None = None) -> dict:
        if response_schema is None:
            reflow_prompts.append(prompt)
        return original_generate(prompt, response_schema)

    model.generate = capture  # type: ignore[method-assign]
    app = bootstrap("config/default.toml", model_backend_override=model)
    tool_backend = app.executor.tool_backend
    builtin = getattr(tool_backend, "_builtin", tool_backend)
    builtin._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.id_verifier = IdentityVerifier({"hash_file": str(tmp_path / "passphrase")})
    app.id_verifier.set_passphrase("demo-secret")
    request = "读取 notes.md 并总结关键事实"

    pending = app.handle(request, "session")
    reply = app.handle("确认 demo-secret", "session")

    assert "document.read" in pending
    assert reply == "文档摘要"
    assert len(reflow_prompts) == 1
    reflow_prompt = reflow_prompts[0]
    assert request in reflow_prompt
    assert "demo-secret" not in reflow_prompt
    assert app._pending_user_request is None
    assert any(
        "result_delivery=model_summary" in episode
        for episodes in app._topic_records.values()
        for episode in episodes
    )


def test_confirmation_execution_error_does_not_call_reflow_model(tmp_path) -> None:
    from src.main import bootstrap
    from src.tools.registry import RegisteredTool

    (tmp_path / "notes.md").write_text("content", encoding="utf-8")
    model = MockModelBackend(
        structured_response={
            "state": "READY", "intent_type": "read_document",
            "entities": {"path": "notes.md"}, "missing_info": [],
            "suggested_tools": ["document.read"], "tool_intent": "local_action",
            "tool_call": {"tool_name": "document.read", "arguments": {"path": "notes.md"}},
            "risk_draft": "normal", "model_confidence": 0.95,
            "reasoning": "read it", "capability_id": "files.read",
        },
        text_response="must not be returned",
    )
    text_calls = 0
    original_generate = model.generate

    def capture(prompt: str, response_schema: dict | None = None) -> dict:
        nonlocal text_calls
        if response_schema is None:
            text_calls += 1
        return original_generate(prompt, response_schema)

    model.generate = capture  # type: ignore[method-assign]
    app = bootstrap("config/default.toml", model_backend_override=model)
    backend = getattr(app.executor.tool_backend, "_builtin", app.executor.tool_backend)
    backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.id_verifier = IdentityVerifier({"hash_file": str(tmp_path / "passphrase")})
    app.id_verifier.set_passphrase("demo-secret")
    app.handle("读取 notes.md", "session")
    registered = backend._active["document.read"]  # type: ignore[attr-defined]

    def fail(_params, _context):
        raise ToolError("TOOL_EXEC_ERROR", "failed", "读取失败。", recoverable=True)

    backend._active["document.read"] = RegisteredTool(  # type: ignore[attr-defined]
        registered.definition, fail, registered.preflight
    )
    reply = app.handle("确认 demo-secret", "session")

    assert reply == "读取失败。"
    assert text_calls == 0
    assert app._latest_execution_records[0].result_delivery is None


def test_execution_records_join_delivery_by_step_index_without_shifting() -> None:
    from src.main import _execution_records

    records = _execution_records(
        _plan("document.read", "document.read"),
        {0: {"segments": []}, 1: {"segments": []}, 99: {"segments": []}},
        {1: "model_summary", 99: "must_not_shift"},
    )

    assert [record.result_delivery for record in records] == [None, "model_summary"]


def test_execution_record_episode_text_carries_delivery_status_only() -> None:
    from src.core.schemas import ExecutionRecord
    from src.main import _format_execution_record

    text = _format_execution_record(ExecutionRecord(
        tool_name="document.read", verdict="allowed", risk_level="sensitive",
        outcome="success", sanitized_summary="returned fields: segments",
        result_delivery="model_summary",
    ))

    assert "result_delivery=model_summary" in text
    assert "document body" not in text
