"""Deterministic write-time sanitization for persistent memory."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from src.safety.secret_scan import contains_credential, redact_local

_PROTECTED_PATH_RE = re.compile(
    r"~[\\/]\.ssh(?:[\\/]\S*)?|/etc/shadow\S*|C:[\\/]Windows[\\/]System32\S*",
    re.IGNORECASE,
)


def sanitize_for_memory(text: str, *, forbidden_paths: tuple[str, ...] = ()) -> str:
    """Replace secrets and protected paths with stable semantic placeholders."""

    sanitized = redact_local(text)
    sanitized = _PROTECTED_PATH_RE.sub("[已脱敏:path]", sanitized)
    configured_path_re = _configured_path_pattern(forbidden_paths)
    if configured_path_re is not None:
        sanitized = configured_path_re.sub("[已脱敏:path]", sanitized)
    if (
        contains_credential(sanitized)
        or _PROTECTED_PATH_RE.search(sanitized)
        or (configured_path_re is not None and configured_path_re.search(sanitized))
    ):
        return "[已脱敏:block]"
    return sanitized


def sanitize_memory_value(value: Any, *, forbidden_paths: tuple[str, ...] = ()) -> Any:
    """Recursively sanitize text values before serializing memory records."""

    if isinstance(value, str):
        return sanitize_for_memory(value, forbidden_paths=forbidden_paths)
    if isinstance(value, Mapping):
        return {key: sanitize_memory_value(item, forbidden_paths=forbidden_paths) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_memory_value(item, forbidden_paths=forbidden_paths) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_memory_value(item, forbidden_paths=forbidden_paths) for item in value)
    return value


def _configured_path_pattern(forbidden_paths: tuple[str, ...]) -> re.Pattern[str] | None:
    patterns = [re.escape(path.rstrip("/\\")) + r"\S*" for path in forbidden_paths if path.strip()]
    return re.compile("|".join(patterns), re.IGNORECASE) if patterns else None
