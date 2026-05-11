"""RemoveResultRow — remove a compound result row from a DRAFT campaign.

Looks up the result by id, then delegates to
``campaign.remove_result_by_molecule`` which also enforces DRAFT status.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.enums import CampaignStatus
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class RemoveResultRowCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID


class RemoveResultRow:
    """Remove a compound row (and all its measurements) from a DRAFT campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
      4. Find the result by id on ``campaign.results``; NotFoundError if missing.
      5. ``campaign.remove_result_by_molecule(result.molecule_id)`` removes the
         row and all associated measurements.
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
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(
                        f"Cannot remove result: campaign is {campaign.status.value}"
                    )
                )

            result = next(
                (r for r in campaign.results if r.id == input.result_id), None
            )
            if result is None:
                return Failure(NotFoundError("CampaignResult", str(input.result_id)))

            campaign.remove_result_by_molecule(result.molecule_id)
            campaign.updated_at = datetime.now(UTC)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
