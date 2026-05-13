"""Read-model port for resolving the "Scientist" readout per run.

A protocol may declare a free-text "Scientist" readout that the bench operator
fills in at run time. The campaign UI shows the scientist's name next to
result rows sourced from that run, so GetCampaign needs to look this up in a
single bulk query rather than per-row.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.research_organization.campaign_scientist_reader``.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class CampaignScientistReader(Protocol):
    """Looks up the "Scientist" readout text for each run in one query."""

    async def find_scientist_by_run_ids(
        self,
        workspace_id: uuid.UUID,
        run_ids: set[uuid.UUID],
    ) -> dict[uuid.UUID, str]: ...
