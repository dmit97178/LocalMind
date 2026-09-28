"""P0a no-op EvolutionBackend implementation."""

from __future__ import annotations

from src.core.interfaces import EvolutionBackend
from src.core.schemas import Experience, Skill


class NoopEvolutionBackend(EvolutionBackend):
    """Keep evolution disabled while preserving the adapter boundary."""

    def reflect(self, task_context: dict) -> list[Experience]:
        del task_context
        return []

    def get_skills(self, intent: str) -> list[Skill]:
        del intent
        return []

    def collect_experience(self, task: dict, outcome: str) -> None:
        del task, outcome
