"""SupersedeCampaign — mark an old closed campaign as superseded by a newer one.

The new campaign was already created via ``CreateCampaign`` with
``supersedes_campaign_id`` pre-set. This use case validates that pairing,
calls ``old.mark_superseded_by(new.id)`` (which enforces old.status == CLOSED),
and emits ``CampaignSuperseded``.

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load old campaign (workspace-scoped); Failure(NotFoundError) if missing.
  3. Load new campaign (workspace-scoped); Failure(NotFoundError) if missing.
  4. Sanity check: ``new.supersedes_campaign_id == old.id``;
     Failure(ValidationError) on mismatch.
  5. ``old.mark_superseded_by(new.id)`` — aggregate enforces old.status == CLOSED;
     catch ValidationError and return Failure.
  6. ``await campaign_repo.save(old)`` + ``await uow.commit()`` inside UoW.
  7. Dispatch events; return ``Success(old)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class SupersedeCampaignCommand(Command):
    workspace_id: uuid.UUID
    old_campaign_id: uuid.UUID
    new_campaign_id: uuid.UUID


class SupersedeCampaign:
    """Mark an old closed campaign as superseded by a new one.

    Validates the supersession pairing and transitions the old campaign from
    CLOSED → SUPERSEDED, recording the back-pointer and emitting
    ``CampaignSuperseded``.
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
        input: SupersedeCampaignCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)

        async with self._uow:
            old = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.old_campaign_id
            )
            if old is None:
                return Failure(NotFoundError("Campaign", str(input.old_campaign_id)))

            new = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.new_campaign_id
            )
            if new is None:
                return Failure(NotFoundError("Campaign", str(input.new_campaign_id)))

            if new.supersedes_campaign_id != old.id:
                return Failure(
                    ValidationError(
                        f"new campaign's supersedes_campaign_id "
                        f"({new.supersedes_campaign_id}) does not match old "
                        f"campaign id ({old.id})"
                    )
                )

            try:
                old.mark_superseded_by(new.id)
            except ValidationError as e:
                return Failure(e)

            await self._campaign_repo.save(old)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(old)
