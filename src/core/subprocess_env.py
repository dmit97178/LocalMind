"""Restricted environment shared by local helper subprocesses."""

from __future__ import annotations

import os

_COPY_ALLOWLIST = (
    "SystemRoot", "windir", "TEMP", "TMP", "PATHEXT", "ComSpec",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)


def restricted_subprocess_environment() -> dict[str, str]:
    environment = {
        key: value for key in _COPY_ALLOWLIST if (value := os.getenv(key)) is not None
    }
    environment.update(
        {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    )
    return environment
