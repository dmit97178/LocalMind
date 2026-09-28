"""Shared pytest fixtures for P0a."""

import atexit
import os
import shutil
import tempfile

import pytest

from src.core.interfaces import (
    CloudAdvisoryBackend,
    EvolutionBackend,
    MemoryBackend,
    ModelBackend,
    SafetyBackend,
    ToolBackend,
)

if "PYTEST_DEBUG_TEMPROOT" not in os.environ:
    # This Windows environment can retain directory handles after pytest exits.
    # A fresh external root avoids reusing a locked directory on the next run.
    _temproot = tempfile.mkdtemp(prefix="localmind-pytest-")
    os.environ["PYTEST_DEBUG_TEMPROOT"] = _temproot
    atexit.register(shutil.rmtree, _temproot, ignore_errors=True)


@pytest.fixture
def mock_model() -> ModelBackend:
    from src.models.mock_backend import MockModelBackend

    return MockModelBackend()


@pytest.fixture
def in_memory_memory() -> MemoryBackend:
    from src.memory.in_memory_backend import InMemoryMemoryBackend

    return InMemoryMemoryBackend()


@pytest.fixture
def builtin_tools() -> ToolBackend:
    from src.tools.builtin_backend import BuiltinToolBackend

    return BuiltinToolBackend()


@pytest.fixture
def rule_only_safety() -> SafetyBackend:
    from src.safety.rule_only_backend import RuleOnlySafetyBackend

    return RuleOnlySafetyBackend()


@pytest.fixture
def noop_evolution() -> EvolutionBackend:
    from src.evolution.noop_backend import NoopEvolutionBackend

    return NoopEvolutionBackend()


@pytest.fixture
def noop_cloud_advisory() -> CloudAdvisoryBackend:
    from src.tools.cloud_advisory import NoopCloudAdvisoryBackend

    return NoopCloudAdvisoryBackend()
