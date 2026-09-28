"""End-to-end P3 confirmation flow tests."""

from __future__ import annotations

from pathlib import Path

from src.models.mock_backend import MockModelBackend
from src.safety.identity import IdentityVerifier

_DEFAULT_CONFIG = Path(__file__).parents[1] / "config" / "p6_legacy.example.toml"


def _file_read_model(path: Path) -> MockModelBackend:
    return MockModelBackend(
        structured_response={
            "state": "READY",
            "intent_type": "read_file",
            "entities": {"path": str(path)},
            "missing_info": [],
            "suggested_tools": ["file.read"],
            "tool_intent": "local_action",
            "tool_call": {"tool_name": "file.read", "arguments": {"path": path.name}},
            "risk_draft": "normal",
            "model_confidence": 0.9,
            "reasoning": "P3 confirmation test.",
        }
    )


def test_sensitive_request_requires_confirmation_then_executes(tmp_path: Path) -> None:
    from src.main import bootstrap

    target = tmp_path / "notes.txt"
    target.write_text("P3 confirmed", encoding="utf-8")
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_file_read_model(target))
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.id_verifier = IdentityVerifier({"hash_file": str(tmp_path / "passphrase")})
    app.id_verifier.set_passphrase("demo-secret")

    pending = app.handle(f"read {target}", session_id="same-session")
    reply = app.handle("confirm demo-secret", session_id="same-session")

    assert "file.read" in pending
    assert "P3 confirmed" in reply
    assert app._pending_plan is None
    assert app.executor.audit_log[-1].verdict == "allowed"
    assert app.last_turn_report()["reply_provenance"] == "executed"
    stored = app.memory.retrieve("身份确认", top_k=10)
    assert stored.is_ok and stored.value is not None
    text = "\n".join(chunk.text for chunk in stored.value)
    assert "User: [身份确认，原文不留存]" in text
    assert "demo-secret" not in text
    assert "P3 confirmed" not in text


def test_confirmation_from_another_session_cancels_pending_plan(tmp_path: Path) -> None:
    from src.main import bootstrap

    target = tmp_path / "notes.txt"
    target.write_text("never read", encoding="utf-8")
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_file_read_model(target))
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.id_verifier = IdentityVerifier({"hash_file": str(tmp_path / "passphrase")})
    app.id_verifier.set_passphrase("demo-secret")

    app.handle(f"read {target}", session_id="original")
    reply = app.handle("confirm demo-secret", session_id="other")

    assert reply == "待确认操作属于其他会话，已取消。"
    assert app._pending_plan is None
    assert app.executor.audit_log[-1].verdict == "denied"
    assert "session mismatch" in app.executor.audit_log[-1].reason


def test_confirmation_without_pending_plan_is_not_recorded() -> None:
    from src.main import bootstrap

    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=MockModelBackend())

    assert app.handle("confirm secret", session_id="session-1") == "没有待确认操作。"
    memory = app.memory.retrieve("secret", top_k=10)
    assert memory.is_ok is True
    assert memory.value == []


def test_locked_identity_reports_remaining_lockout_time(tmp_path: Path, monkeypatch) -> None:
    from src.main import bootstrap
    from src.safety import identity

    current_time = 1_000.0
    monkeypatch.setattr(identity.time, "time", lambda: current_time)
    target = tmp_path / "notes.txt"
    target.write_text("never read", encoding="utf-8")
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_file_read_model(target))
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    app.id_verifier = IdentityVerifier(
        {
            "hash_file": str(tmp_path / "passphrase"),
            "lockout_attempts": 1,
            "lockout_minutes": 2,
        }
    )
    app.id_verifier.set_passphrase("demo-secret")

    app.handle(f"read {target}", session_id="same-session")
    reply = app.handle("confirm wrong", session_id="same-session")

    assert "已锁定" in reply
    assert "2 分钟" in reply
    assert app.executor.audit_log[-1].verdict == "denied"
    assert "identity verification" in app.executor.audit_log[-1].reason
    assert app.executor.audit_log[-1].params_redacted == {"path": "***"}


def test_corrupt_passphrase_file_returns_a_reply_and_records_denial(tmp_path: Path) -> None:
    from src.main import bootstrap

    target = tmp_path / "notes.txt"
    target.write_text("never read", encoding="utf-8")
    app = bootstrap(str(_DEFAULT_CONFIG), model_backend_override=_file_read_model(target))
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]
    hash_file = tmp_path / "passphrase"
    app.id_verifier = IdentityVerifier({"hash_file": str(hash_file)})
    app.id_verifier.set_passphrase("demo-secret")
    hash_file.write_text("not-a-valid-hash", encoding="ascii")

    app.handle(f"read {target}", session_id="same-session")
    reply = app.handle("confirm demo-secret", session_id="same-session")

    assert reply == "系统配置有误，请检查。"
    assert app._pending_plan is None
    assert app.executor.audit_log[-1].verdict == "denied"
    assert "identity verification error" in app.executor.audit_log[-1].reason
