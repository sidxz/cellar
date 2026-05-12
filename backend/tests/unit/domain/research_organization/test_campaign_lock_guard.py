import uuid

import pytest

from cellar.domain.research_organization.campaign_lock_guard import (
    CampaignLockChecker,
    CampaignLockGuard,
)
from cellar.domain.shared.errors import DataLockedError


class _FakeChecker:
    def __init__(self, locked: bool) -> None:
        self._locked = locked

    async def is_locked(self, workspace_id, campaign_id) -> bool:
        return self._locked


@pytest.mark.asyncio
async def test_guard_passes_when_unlocked():
    guard = CampaignLockGuard(_FakeChecker(locked=False))
    await guard.guard_write(uuid.uuid4(), uuid.uuid4())  # no raise


@pytest.mark.asyncio
async def test_guard_raises_when_locked():
    guard = CampaignLockGuard(_FakeChecker(locked=True))
    with pytest.raises(DataLockedError, match="closed or superseded"):
        await guard.guard_write(uuid.uuid4(), uuid.uuid4())


def test_protocol_is_runtime_checkable():
    # any class with is_locked(workspace_id, campaign_id) -> bool satisfies it
    assert isinstance(_FakeChecker(False), CampaignLockChecker)
