"""CampaignLockGuard — prevents writes to closed or superseded campaigns.

Mirrors the DataLockGuard pattern from the screening_assay context. Every
write path to campaign_result and campaign_measurement (and any other
descendant table) must route through this guard. The repository's
is_locked method is the canonical CampaignLockChecker.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.domain.shared.errors import DataLockedError


@runtime_checkable
class CampaignLockChecker(Protocol):
    """Port for checking whether a campaign is locked.

    The infrastructure-layer CampaignRepository will satisfy this via
    structural typing.
    """

    async def is_locked(
        self, workspace_id: uuid.UUID, campaign_id: uuid.UUID
    ) -> bool: ...


class CampaignLockGuard:
    """Domain service that rejects writes when the campaign is locked."""

    def __init__(self, lock_checker: CampaignLockChecker) -> None:
        self._checker = lock_checker

    async def guard_write(
        self, workspace_id: uuid.UUID, campaign_id: uuid.UUID
    ) -> None:
        if await self._checker.is_locked(workspace_id, campaign_id):
            raise DataLockedError(
                f"Campaign '{campaign_id}' is closed or superseded — "
                f"modifications are not allowed"
            )
