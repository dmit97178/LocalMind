"""P0a cloud advisory backend."""

from __future__ import annotations

from src.core.interfaces import CloudAdvisoryBackend
from src.core.schemas import AdvisoryResult, CloudRequestPackage


class NoopCloudAdvisoryBackend(CloudAdvisoryBackend):
    """Return a safe advisory result while cloud access is disabled."""

    def advise(self, request: CloudRequestPackage) -> AdvisoryResult:
        del request
        return AdvisoryResult(
            analysis="云端咨询暂未启用。",
            risks=[],
            requires_local_validation=True,
        )
