"""P0a reflection recorder placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.interfaces import EvolutionBackend


@dataclass(frozen=True)
class ReflectionRecorder:
    """Preserve the reflection boundary without enabling evolution in P0a."""

    evolution: EvolutionBackend

    def record(self, task_context: dict, outcome: str) -> None:
        del task_context, outcome
