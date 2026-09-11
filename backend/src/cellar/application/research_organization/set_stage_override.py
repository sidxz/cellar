"""SetStageOverride — manually force or clear a (result, stage) hit/miss verdict.

A chemist can promote/demote one compound past a stage's computed verdict,
with a required audit reason (spec §3.3, §6). Unlike ``OverrideResultCell``,
there is no measurement to build — the mutation lives entirely on
``CampaignResult.stage_overrides`` (see ``domain/research_organization/
campaign_result.py``); ``stage_evaluation.evaluate_stages`` applies it on
every read.
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
from cellar.domain.research_organization.enums import CampaignStatus, StageOutcome
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class SetStageOverrideCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID
    stage_id: uuid.UUID
    user_id: uuid.UUID
    #: ``None`` clears any existing override; otherwise must be HIT or MISS
    #: (enforced by the domain ``StageOverride``, not re-checked here).
    forced_outcome: StageOutcome | None
    reason: str | None = None


class SetStageOverride:
    """Force or clear a manual (result, stage) override on a draft Campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); ``Failure(NotFoundError)`` if missing.
      3. Status guard — ``Failure(DataLockedError)`` if not DRAFT (matches
         ``AddCampaignStage`` — an override is a stage-adjacent mutation, so
         a closed campaign reports 423, not 422).
      4. Find the result on ``campaign.results``; ``NotFoundError`` if missing.
      5. Find the stage via ``campaign.find_stage``; ``NotFoundError`` if missing.
      6. ``forced_outcome is None`` -> ``result.clear_stage_override`` (a
         no-op success when nothing was overridden). Otherwise ->
         ``result.set_stage_override`` — the domain ``StageOverride``
         validates ``forced_outcome in {HIT, MISS}`` and a non-empty
         ``reason``, surfaced here as ``Failure(ValidationError)``.
      7. Bump ``campaign.updated_at`` when something actually changed.
         Save + commit inside the UoW; dispatch outside; return
         ``Success(campaign)``.
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
        input: SetStageOverrideCommand,
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

            result = next((r for r in campaign.results if r.id == input.result_id), None)
            if result is None:
                return Failure(NotFoundError("CampaignResult", str(input.result_id)))

            if campaign.find_stage(input.stage_id) is None:
                return Failure(NotFoundError("CampaignStage", str(input.stage_id)))

            if input.forced_outcome is None:
                changed = result.clear_stage_override(input.stage_id)
            else:
                try:
                    result.set_stage_override(
                        stage_id=input.stage_id,
                        forced_outcome=input.forced_outcome,
                        reason=input.reason or "",
                        overridden_by=input.user_id,
                    )
                except ValidationError as e:
                    return Failure(e)
                changed = True

            if changed:
                campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
