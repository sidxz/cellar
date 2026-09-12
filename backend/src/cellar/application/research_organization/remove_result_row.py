"""RemoveResultRow — remove compound result rows from a DRAFT campaign.

Looks up each result by id, then delegates to
``campaign.remove_result_by_molecule`` which also enforces DRAFT status.
The command takes a *list* of result ids: the per-row route is a one-element
call, and a bulk removal is one load + one save.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class RemoveResultRowCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_ids: list[uuid.UUID]


class RemoveResultRow:
    """Remove compound rows (and all their measurements) from a DRAFT campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
      4. Resolve *every* result id on ``campaign.results`` before removing
         anything; the first unknown id -> NotFoundError (all-or-nothing).
      5. ``campaign.remove_result_by_molecule(result.molecule_id)`` per id —
         removes the row and all associated measurements.
      6. Bump ``campaign.updated_at``. Save + commit; dispatch; return ``Success``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: RemoveResultRowCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot remove result: campaign is {campaign.status.value}")
                )

            by_id = {r.id: r for r in campaign.results}
            missing = next((rid for rid in input.result_ids if rid not in by_id), None)
            if missing is not None:
                return Failure(NotFoundError("CampaignResult", str(missing)))

            for result_id in input.result_ids:
                campaign.remove_result_by_molecule(by_id[result_id].molecule_id)
            campaign.updated_at = datetime.now(UTC)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
