"""Rule-only implementation of SafetyBackend."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.interfaces import SafetyBackend
from src.core.schemas import SafetyVerdict
from src.safety.secret_scan import contains_credential

_DEFAULT_FORBIDDEN_COMMANDS = [
    "rm -rf /",
    "dd if=",
    "mkfs.",
    ":(){ :|:& };:",
]
_DEFAULT_FORBIDDEN_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "C:\\Windows\\System32",
    "~/.ssh",
]
_DEFAULT_SENSITIVE_PATTERNS: list[str] = []


@dataclass
class RuleOnlySafetyBackend(SafetyBackend):
    """P0 L1 safety backend using deterministic local rules only."""

    config: dict | None = None
    forbidden_commands: list[str] = field(init=False)
    forbidden_paths: list[str] = field(init=False)
    sensitive_patterns: list[re.Pattern[str]] = field(init=False)
    workspace_root: Path = field(init=False)

    def __post_init__(self) -> None:
        config = self.config or {}
        rules = _extract_l1_rules(config)
        self.workspace_root = Path(str(config.get("workspace_root", "./data/workspace"))).resolve()
        self.forbidden_commands = list(
            rules.get("forbidden_commands", _DEFAULT_FORBIDDEN_COMMANDS)
        )
        self.forbidden_paths = list(rules.get("forbidden_paths", _DEFAULT_FORBIDDEN_PATHS))
        self.sensitive_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in rules.get("sensitive_patterns", _DEFAULT_SENSITIVE_PATTERNS)
        ]

    def check_dangerous(self, operation: dict) -> SafetyVerdict:
        if operation.get("tool_name") == "file.write" and not self._write_path_allowed(operation):
            return SafetyVerdict(False, "dangerous", "workspace_escape")
        haystack = _operation_text(operation)
        haystack_lower = haystack.lower()

        for command_pattern in self.forbidden_commands:
            if command_pattern.lower() in haystack_lower:
                return SafetyVerdict(
                    allowed=False,
                    risk_level="dangerous",
                    reason=f"Matched forbidden command pattern: {command_pattern}",
                )

        for path in self.forbidden_paths:
            if path.lower() in haystack_lower:
                return SafetyVerdict(
                    allowed=False,
                    risk_level="dangerous",
                    reason=f"Matched forbidden path pattern: {path}",
                )

        if contains_credential(haystack):
            return SafetyVerdict(
                allowed=False,
                risk_level="sensitive",
                reason="Matched built-in credential pattern",
            )

        for sensitive_pattern in self.sensitive_patterns:
            if sensitive_pattern.search(haystack):
                return SafetyVerdict(
                    allowed=False,
                    risk_level="sensitive",
                    reason=f"Matched sensitive pattern: {sensitive_pattern.pattern}",
                )

        return SafetyVerdict(
            allowed=True,
            risk_level=_risk_level(operation),
            reason="No L1 safety rule matched.",
        )

    def _write_path_allowed(self, operation: dict) -> bool:
        params = operation.get("params")
        if not isinstance(params, dict):
            return False
        raw = params.get("path")
        if not isinstance(raw, str) or not raw.strip() or raw.startswith("~"):
            return False
        path = Path(raw)
        if path.is_absolute() or path.drive or raw.startswith(("\\\\", "//")):
            return False
        return (self.workspace_root / path).resolve().is_relative_to(self.workspace_root)


def _extract_l1_rules(config: dict) -> dict:
    if "l1_rules" in config and isinstance(config["l1_rules"], dict):
        return config["l1_rules"]
    return config


def _operation_text(operation: dict) -> str:
    return " ".join(_stringify(value) for value in operation.values())


def _stringify(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key}={_stringify(item)}" for key, item in value.items())
    if isinstance(value, list | tuple | set):
        return " ".join(_stringify(item) for item in value)
    return str(value)


def _risk_level(operation: dict) -> str:
    risk_level = operation.get("risk_level", "normal")
    if isinstance(risk_level, str) and risk_level.strip():
        return risk_level
    return "normal"
