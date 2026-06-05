"""UpdateCampaignMetadata — rename / re-describe a DRAFT campaign.

Uses an ``UNSET`` sentinel to distinguish "caller did not supply description"
from "caller explicitly cleared description to None".

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load campaign (workspace-scoped); Failure(NotFoundError) if missing.
  3. Status guard: campaign must be DRAFT — Failure(DataLockedError) otherwise.
  4. Apply name / description mutations when provided.
  5. Bump ``campaign.updated_at``. Save + commit; dispatch events; return
     ``Success(campaign)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class _Unset:
    """Singleton sentinel meaning "caller did not supply this field"."""

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True, kw_only=True)
class UpdateCampaignMetadataCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    # None means "don't change"; a string means "change to this value"
    name: str | None = None
    # UNSET means "don't touch"; None means "clear the description"
    description: str | None | object = UNSET


class UpdateCampaignMetadata:
    """Rename / re-describe a DRAFT campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); reject if missing.
      3. Status guard — reject with ``DataLockedError`` if not DRAFT.
      4. Validate and apply ``name`` when provided (not None, not empty).
      5. Apply ``description`` when not UNSET.
      6. Bump ``campaign.updated_at`` if anything changed. Save + commit;
         dispatch events; return ``Success(campaign)``.
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
        input: UpdateCampaignMetadataCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        require_editor(auth)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(DataLockedError(f"Campaign is {campaign.status.value}"))

            changed = False

            if input.name is not None:
                stripped = input.name.strip()
                if not stripped:
                    return Failure(ValidationError("Campaign.name must not be empty"))
                if stripped != campaign.name:
                    campaign.name = stripped
                    changed = True

            if (
                not isinstance(input.description, _Unset)
                and input.description != campaign.description
            ):
                campaign.description = input.description  # type: ignore[assignment]
                changed = True

            if changed:
                campaign.updated_at = datetime.now(UTC)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
