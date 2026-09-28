"""Core-only bounded orchestration for cloud advisory sub-turns."""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.core.interfaces import CloudGrant, CloudTurnGateway
from src.core.schemas import CloudRequestPackage, ConsultOutcome, LocalMindError

_FOLLOWUP_CATEGORIES = {"memory_evidence", "user_entity"}


@dataclass
class CloudAdvisoryService:
    """Coordinate a bounded consultation through the protected gateway only."""

    gateway: CloudTurnGateway
    max_turns: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.max_turns, int) or isinstance(self.max_turns, bool) or not 1 <= self.max_turns <= 3:
            raise LocalMindError("CONFIG_ERROR", "cloud max_turns must be 1..3", "系统配置有误，请检查 cloud_advisory.config。")

    def consult(
        self, package: CloudRequestPackage, grant: CloudGrant, task_id: str, intent_id: str
    ) -> ConsultOutcome:
        """Run one grant-bound turn and suspend before any boundary expansion."""

        result = self.gateway.execute_cloud_turn(package, grant, task_id, intent_id, package.turn)
        categories = _normalize_requested_categories(result.requested_context_categories)
        if result.needs_more_info and categories:
            return ConsultOutcome(status="suspended", result=result, requested_categories=categories)
        if result.needs_more_info:
            result = replace(
                result,
                needs_more_info=False,
                requested_context_categories=(),
                followup_question="",
            )
        return ConsultOutcome(status="completed", result=result)


def _normalize_requested_categories(categories: object) -> tuple[str, ...]:
    if not isinstance(categories, tuple):
        return ()
    normalized: list[str] = []
    for category in categories:
        value = category.strip().lower() if isinstance(category, str) else ""
        if value in _FOLLOWUP_CATEGORIES and value not in normalized:
            normalized.append(value)
    return tuple(normalized)
