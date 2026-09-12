"""SetStageOverride — manually force or clear (result, stage) hit/miss verdicts.

A chemist can promote/demote compounds past a stage's computed verdict, with
a required audit reason (spec §3.3, §6). Unlike ``OverrideResultCell``, there
is no measurement to build — the mutation lives entirely on
``CampaignResult.stage_overrides`` (see ``domain/research_organization/
campaign_result.py``); ``stage_evaluation.evaluate_stages`` applies it on
every read.

The command takes a *list* of result ids: the per-result routes are
one-element calls, and a bulk promote/demote is one load + one save (the
repository persists the whole aggregate with a single version bump).
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
    result_ids: list[uuid.UUID]
    stage_id: uuid.UUID
    user_id: uuid.UUID
    #: ``None`` clears any existing override; otherwise must be HIT or MISS
    #: (enforced by the domain ``StageOverride``, not re-checked here).
    forced_outcome: StageOutcome | None
    reason: str | None = None


class SetStageOverride:
    """Force or clear manual (result, stage) overrides on a draft Campaign.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Empty ``result_ids`` -> ``Failure(ValidationError)``.
      3. Load campaign (workspace-scoped); ``Failure(NotFoundError)`` if missing.
      4. Status guard — ``Failure(DataLockedError)`` if not DRAFT (matches
         ``AddCampaignStage`` — an override is a stage-adjacent mutation, so
         a closed campaign reports 423, not 422).
      5. Find the stage via ``campaign.find_stage``; ``NotFoundError`` if missing.
      6. Resolve *every* result id before mutating anything; the first
         unknown id -> ``NotFoundError`` (all-or-nothing).
      7. ``forced_outcome is None`` -> ``clear_stage_override`` on each (a
         no-op success when nothing was overridden). Otherwise ->
         ``set_stage_override`` — the domain ``StageOverride`` validates
         ``forced_outcome in {HIT, MISS}`` and a non-empty ``reason``,
         surfaced here as ``Failure(ValidationError)``. Both depend only on
         the command, so an invalid one fails on the first result, before
         any result has been touched.
      8. Bump ``campaign.updated_at`` when something actually changed.
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

        if not input.result_ids:
            return Failure(ValidationError("result_ids must not be empty"))

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(DataLockedError(f"Campaign is {campaign.status.value}"))

            if campaign.find_stage(input.stage_id) is None:
                return Failure(NotFoundError("CampaignStage", str(input.stage_id)))

            by_id = {r.id: r for r in campaign.results}
            missing = next((rid for rid in input.result_ids if rid not in by_id), None)
            if missing is not None:
                return Failure(NotFoundError("CampaignResult", str(missing)))

            changed = False
            for result_id in input.result_ids:
                result = by_id[result_id]
                if input.forced_outcome is None:
                    changed = result.clear_stage_override(input.stage_id) or changed
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
