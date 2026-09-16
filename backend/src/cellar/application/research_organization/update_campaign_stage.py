"""UpdateCampaignStage — mutate name / parent / criteria / display_order.

The UNSET-sentinel handling lives entirely in ``Campaign.update_stage`` —
this use case imports the domain-owned ``UNSET`` (see
``domain/research_organization/campaign_stage.py``) and passes the command's
fields straight through, rather than re-implementing the sentinel dance that
``UpdateCampaignChannel`` does for its own (measurement-re-resolving) fields.
``criteria`` is replaced whole, never patched per item.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_stage import UNSET, StageCriterion
from cellar.domain.research_organization.enums import CampaignStatus, StageKind
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class UpdateCampaignStageCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    stage_id: uuid.UUID
    # UNSET means "don't touch"; None is meaningful only for parent_stage_id
    # (clears it) — mirrors Campaign.update_stage's own kwarg semantics.
    name: str | object = UNSET
    parent_stage_id: uuid.UUID | object | None = UNSET
    criteria: list[StageCriterion] | object = UNSET
    display_order: int | object = UNSET
    kind: StageKind | object = UNSET


class UpdateCampaignStage:
    """Update a stage's mutable fields on a draft Campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); ``Failure(NotFoundError)`` if missing.
      3. Status guard — ``Failure(DataLockedError)`` if not DRAFT.
      4. ``campaign.update_stage(...)`` — aggregate applies the UNSET-aware
         partial update and raises ``NotFoundError``/``ValidationError`` for
         an unknown stage / invalid name, parent, or criteria.
      5. Save + commit; dispatch events; return ``Success(campaign)``.
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
        input: UpdateCampaignStageCommand,
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
                return Failure(DataLockedError(f"Campaign is {campaign.status.value}"))

            try:
                campaign.update_stage(
                    input.stage_id,
                    name=input.name,
                    parent_stage_id=input.parent_stage_id,
                    criteria=input.criteria,
                    display_order=input.display_order,
                    kind=input.kind,
                )
            except (NotFoundError, ValidationError) as e:
                return Failure(e)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
