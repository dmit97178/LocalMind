"""End-to-end coverage for P5 project and conversation memory wiring."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.core.interfaces import ToolBackend
from src.core.schemas import Result, ToolDef, ToolError
from src.memory.in_memory_backend import InMemoryMemoryBackend
from src.models.mock_backend import MockModelBackend

_DEFAULT_CONFIG = Path(__file__).parents[1] / "config" / "p6_legacy.example.toml"


class PromptRecordingModel(MockModelBackend):
    def __init__(self) -> None:
        super().__init__(
            structured_response={
                "state": "READY",
                "intent_type": "echo_message",
                "entities": {"message": "P5"},
                "missing_info": [],
                "suggested_tools": ["system.echo"],
                "tool_intent": "local_action",
                "tool_call": {"tool_name": "system.echo", "arguments": {"message": "P5"}},
                "risk_draft": "normal",
                "model_confidence": 0.9,
            }
        )
        self.structured_prompts: list[str] = []
        self.text_prompts: list[str] = []

    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        if response_schema is not None:
            self.structured_prompts.append(prompt)
        else:
            self.text_prompts.append(prompt)
        return super().generate(prompt, response_schema)


def test_summary_prompts_forbid_promoting_inference_to_fact() -> None:
    from src.main import bootstrap

    model = PromptRecordingModel()
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.handle("记录项目事实", session_id="summary-session", project_id="summary-project")
    app._summarize_topic("", "summary-topic", 1, ["User: 尚未验证稳定性"])

    assert len(model.text_prompts) >= 2
    for prompt in model.text_prompts[-2:]:
        assert "Only restate content the user explicitly provided" in prompt
        assert "Do not infer conclusions" in prompt
        assert "record uncertainty as unresolved work" in prompt


class RecordingMemory(InMemoryMemoryBackend):
    def __init__(self) -> None:
        super().__init__()
        self.retrieve_calls: list[dict] = []

    def retrieve(self, query: str, top_k: int = 5, **kwargs):
        self.retrieve_calls.append({"query": query, "top_k": top_k, **kwargs})
        return super().retrieve(query, top_k, **kwargs)


class FailingEchoToolBackend(ToolBackend):
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

    def execute(self, tool_name: str, params: dict) -> Result[dict]:
        del tool_name, params
        return Result.err(
            ToolError(
                code="TOOL_EXEC_ERROR",
                message="synthetic tool failure",
                user_message="操作执行失败。",
                recoverable=True,
            )
        )


def test_app_normalizes_project_id_and_records_topic_routed_episode() -> None:
    from src.main import bootstrap

    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "echo_message",
            "entities": {"message": "P5"},
            "missing_info": [],
            "suggested_tools": ["system.echo"],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "system.echo", "arguments": {"message": "P5"}},
            "risk_draft": "normal",
            "model_confidence": 0.9,
        }
    )
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)

    reply = app.handle("记录项目进度", session_id="session-p5", project_id="Project Alpha!")

    assert reply == "[0] system.echo：message: P5"
    state = app.projects.load("project-alpha")
    assert state is not None
    assert state.topic_tags == ("记录项目进度",)
    assert "记录项目进度" in state.summary
    assert app.topics.current_topic("session-p5") == "记录项目进度"
    result = app.memory.retrieve("项目", top_k=1, project_id="project-alpha")
    assert result.is_ok and result.value is not None
    assert result.value[0].metadata["project_id"] == "project-alpha"
    assert result.value[0].metadata["topic"] == "记录项目进度"
    assert "message: P5" not in result.value[0].text


def test_app_does_not_inject_memory_from_the_previous_project() -> None:
    from src.main import bootstrap

    model = PromptRecordingModel()
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    app.handle("建立 alpha 项目", session_id="session-p5", project_id="alpha")
    app.memory.store_episode(
        "status previous-project-only-marker",
        {"topic": "alpha-status", "session_id": "session-p5", "project_id": "alpha"},
    )

    app.handle("检查 status", session_id="session-p5", project_id="beta")

    assert "previous-project-only-marker" not in model.structured_prompts[-1]
    assert "'project_id': 'beta'" in model.structured_prompts[-1]
    assert app.memory.get_summary("conversation", "session-p5") is not None


def test_end_session_writes_final_summary_and_clears_topic_state() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=MockModelBackend())
    app.handle("记录会话内容", session_id="session-p5")

    app.end_session("session-p5")

    summary = app.memory.get_summary("conversation", "session-p5")
    assert summary is not None
    assert app.topics.current_topic("session-p5") == ""


def test_shift_with_reference_retrieves_old_topic_and_records_reference_metadata() -> None:
    from src.main import bootstrap

    model = PromptRecordingModel()
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    memory = _replace_memory(app)
    app.handle("预算规划", session_id="session-p5")
    memory.store_episode(
        "legacy-evidence-marker",
        {"topic": "预算规划", "session_id": "session-p5"},
    )

    app.handle("刚才 legacy-evidence-marker", session_id="session-p5")

    assert "legacy-evidence-marker" in model.structured_prompts[-1]
    latest = memory._chunks[-1]
    assert latest.metadata["referenced_topic"] == "预算规划"


def test_ambiguous_turn_never_passes_old_topic_as_a_retrieval_hint() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=PromptRecordingModel())
    memory = _replace_memory(app)
    app.handle("alpha planning", session_id="session-p5")
    memory.retrieve_calls.clear()

    app.handle("look at this", session_id="session-p5")

    assert memory.retrieve_calls[-1]["topic_hints"] == ()
    assert app.topics.current_topic("session-p5") == "alpha-planning"
    assert memory._chunks[-1].metadata.get("referenced_topic") is None


def test_shift_with_reference_does_not_recall_another_sessions_topic() -> None:
    from src.main import bootstrap

    model = PromptRecordingModel()
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=model)
    memory = _replace_memory(app)
    app.handle("alpha plan", session_id="session-a")
    app.handle("alpha plan", session_id="session-b")
    memory.store_episode(
        "marker data from a",
        {"topic": "alpha-plan", "session_id": "session-a"},
    )
    memory.store_episode(
        "marker data from b", {"topic": "alpha-plan", "session_id": "session-b"}
    )

    app.handle("刚才 marker data", session_id="session-a")

    prompt = model.structured_prompts[-1]
    assert "marker data from a" in prompt
    assert "marker data from b" not in prompt


def test_zero_match_topic_hints_return_empty_without_falling_back_to_normal_scope() -> None:
    memory = InMemoryMemoryBackend()
    memory.store_episode("ordinary evidence", {"topic": "ordinary", "session_id": "session-p5"})

    hinted = memory.retrieve("ordinary", topic_hints=("missing-topic",))
    normal = memory.retrieve("ordinary")

    assert hinted.is_ok and hinted.value == []
    assert normal.is_ok and normal.value is not None
    assert [chunk.text for chunk in normal.value] == ["ordinary evidence"]


def test_confirmation_memory_excludes_passphrase_and_tool_result_values(tmp_path: Path) -> None:
    from src.main import bootstrap
    from src.safety.identity import IdentityVerifier

    secret = "p5-confirm-secret"
    target = tmp_path / "notes.txt"
    target.write_text("ordinary-tool-result", encoding="utf-8")
    config_path = tmp_path / "p5-sqlite.toml"
    config_path.write_text(
        _DEFAULT_CONFIG.read_text(encoding="utf-8")
        .replace('type = "in_memory"', 'type = "sqlite"', 1)
        .replace(
            "[memory_backend.config]\n",
            f'[memory_backend.config]\ndb_path = "{(tmp_path / "memory.db").as_posix()}"\n',
            1,
        ),
        encoding="utf-8",
    )
    model = MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "read_file",
            "entities": {"path": str(target)},
            "missing_info": [],
            "suggested_tools": ["file.read"],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "file.read", "arguments": {"path": target.name}},
            "risk_draft": "normal",
            "model_confidence": 0.9,
        }
    )
    app = bootstrap(str(config_path), model_backend_override=model)
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.id_verifier = IdentityVerifier({"hash_file": str(tmp_path / "passphrase")})
    app.id_verifier.set_passphrase(secret)

    app.handle(f"read {target}", session_id="session-p5", project_id="secure-project")
    app.handle(f"confirm {secret}", session_id="session-p5")

    rows = app.memory._conn.execute(
        """
        SELECT content AS value FROM episodes
        UNION ALL SELECT summary_json AS value FROM summaries
        UNION ALL SELECT state_json AS value FROM projects
        UNION ALL SELECT CAST(vector AS TEXT) AS value FROM episode_vectors
        """
    ).fetchall()
    stores = "\n".join(str(row["value"]) for row in rows)
    assert "User: [身份确认，原文不留存]" in stores
    assert "[tool] name=file.read" in stores
    assert secret not in stores
    assert "ordinary-tool-result" not in stores
    app.memory.close()


def test_failed_tool_execution_is_stored_as_a_structured_failure_record() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=PromptRecordingModel())
    app.executor.tool_backend = FailingEchoToolBackend()

    assert app.handle("run echo", session_id="session-p5") == "操作执行失败。"
    assert app.last_turn_report()["reply_provenance"] == "unfulfilled"

    stored = "\n".join(chunk.text for chunk in app.memory._chunks)
    assert "outcome=failure" in stored
    assert "error=TOOL_EXEC_ERROR" in stored
    assert "synthetic tool failure" not in stored


def test_p5_demo_script_runs_from_project_root() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_p5.py"],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "project=demo-project" in result.stdout
    assert "summary=" in result.stdout


def _replace_memory(app) -> RecordingMemory:
    memory = RecordingMemory()
    app.memory = memory
    app.assembler.memory = memory
    app.resolver.memory = memory
    return memory
