"""Tests for rule-only safety checks and SafetyPolicy."""

from pathlib import Path

from src.core.interfaces import SafetyBackend
from src.core.schemas import ExecutionStep, SafetyVerdict


def test_rule_only_backend_implements_safety_backend() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend()

    assert isinstance(backend, SafetyBackend)


def test_rule_only_backend_allows_normal_operation() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend()

    verdict = backend.check_dangerous(
        {
            "tool_name": "system.echo",
            "action": "echo",
            "params": {"message": "hello"},
            "risk_level": "normal",
        }
    )

    assert verdict == SafetyVerdict(
        allowed=True,
        risk_level="normal",
        reason="No L1 safety rule matched.",
    )


def test_rule_only_backend_denies_forbidden_command_pattern() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend()

    verdict = backend.check_dangerous(
        {
            "tool_name": "system.shell",
            "action": "run",
            "params": {"command": "rm -rf /"},
            "risk_level": "dangerous",
        }
    )

    assert verdict.allowed is False
    assert verdict.risk_level == "dangerous"
    assert "forbidden command" in verdict.reason


def test_rule_only_backend_denies_forbidden_path_pattern() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend()

    verdict = backend.check_dangerous(
        {
            "tool_name": "file.read",
            "action": "read",
            "params": {"path": "C:\\Windows\\System32\\drivers\\etc\\hosts"},
            "risk_level": "sensitive",
        }
    )

    assert verdict.allowed is False
    assert verdict.risk_level == "dangerous"
    assert "forbidden path" in verdict.reason


def test_rule_only_backend_denies_sensitive_pattern() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend()

    verdict = backend.check_dangerous(
        {
            "tool_name": "cloud.send",
            "action": "send",
            "params": {"content": "api_key=abc123"},
            "risk_level": "sensitive",
        }
    )

    assert verdict.allowed is False
    assert verdict.risk_level == "sensitive"
    assert "credential pattern" in verdict.reason


def test_builtin_credential_detection_remains_active_with_empty_config_patterns() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend({"l1_rules": {"sensitive_patterns": []}})

    verdict = backend.check_dangerous({"params": {"content": "我的账号密码是123456"}})

    assert verdict.allowed is False
    assert verdict.risk_level == "sensitive"


def test_rule_only_backend_uses_configured_l1_rules() -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend(
        {
            "l1_rules": {
                "forbidden_commands": ["drop database"],
                "forbidden_paths": ["D:\\private"],
                "sensitive_patterns": ["internal_secret"],
            }
        }
    )

    verdict = backend.check_dangerous(
        {
            "tool_name": "db.exec",
            "action": "sql",
            "params": {"query": "DROP DATABASE localmind"},
            "risk_level": "dangerous",
        }
    )

    assert verdict.allowed is False
    assert "drop database" in verdict.reason


def test_rule_only_backend_rejects_file_write_outside_workspace(tmp_path: Path) -> None:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    backend = RuleOnlySafetyBackend({"workspace_root": str(tmp_path)})
    verdict = backend.check_dangerous(
        {
            "tool_name": "file.write",
            "action": "write",
            "params": {"path": "../outside.txt", "content": "no"},
            "risk_level": "normal",
        }
    )

    assert verdict == SafetyVerdict(False, "dangerous", "workspace_escape")


class RecordingSafetyBackend(SafetyBackend):
    def __init__(self) -> None:
        self.operation: dict | None = None

    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        self.operation = operation
        return SafetyVerdict(allowed=True, risk_level="normal", reason="recorded")


def test_safety_policy_checks_execution_step_with_backend() -> None:
    from src.safety.policy import SafetyPolicy

    backend = RecordingSafetyBackend()
    policy = SafetyPolicy(backend=backend)
    step = ExecutionStep(
        tool_name="system.echo",
        action="echo",
        params={"message": "hello"},
        risk_level="normal",
    )

    verdict = policy.check(step)

    assert verdict == SafetyVerdict(allowed=True, risk_level="normal", reason="recorded")
    assert backend.operation == {
        "tool_name": "system.echo",
        "action": "echo",
        "params": {"message": "hello"},
        "risk_level": "normal",
        "intent_type": "unknown",
        "entities": {},
        "user_input": "",
    }
