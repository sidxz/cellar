"""Workspace-scoped identity matching for candidate campaign compounds."""

from __future__ import annotations

import uuid
from typing import Protocol


class CampaignIdentityReader(Protocol):
    async def matching_ids(
        self, workspace_id: uuid.UUID, molecule_ids: list[uuid.UUID], search: str
    ) -> set[uuid.UUID]: ...
