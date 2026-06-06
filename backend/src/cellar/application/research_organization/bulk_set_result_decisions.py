"""BulkSetResultDecisions — apply one decision to many results in a single DRAFT-aggregate save.

Single-row :class:`SetResultDecision` loads + saves the whole Campaign
aggregate per call. With 100s of compounds in a campaign that's 100s of
round-trips; this UC handles the bulk path by loading once, applying
``result.set_decision(...)`` to every matching id, and saving once.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignDecision, CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class BulkSetResultDecisionsCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_ids: list[uuid.UUID]
    decision: CampaignDecision
    reason: str | None = None


@dataclass(frozen=True)
class BulkSetResultDecisionsOutcome:
    campaign: Campaign
    #: Count of results whose decision actually changed (already-matching rows skipped).
    updated_count: int
    #: Result ids in `result_ids` that didn't exist on the campaign.
    missing_ids: list[uuid.UUID] = field(default_factory=list)


class BulkSetResultDecisions:
    """Apply one decision to many CampaignResult rows in one DRAFT-aggregate save.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Validate non-empty ``result_ids``.
      3. Load campaign (workspace-scoped); NotFoundError if missing.
      4. Inline DRAFT check.
      5. For each requested id: call ``result.set_decision`` if found and the
         decision is actually changing. Track missing ids + updated count.
      6. Bump ``campaign.updated_at`` only when at least one row changed —
         a no-op call returns the aggregate untouched.
      7. Save + commit; dispatch events; return Success(outcome).
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
        input: BulkSetResultDecisionsCommand,
        auth: AuthContext | None = None,
    ) -> Result[BulkSetResultDecisionsOutcome, DomainError]:
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
                return Failure(
                    ValidationError(f"Cannot set decisions: campaign is {campaign.status.value}")
                )

            results_by_id = {r.id: r for r in campaign.results}
            requested = set(input.result_ids)
            missing = sorted(requested - results_by_id.keys())

            updated = 0
            for rid in input.result_ids:
                r = results_by_id.get(rid)
                if r is None:
                    continue
                if r.decision == input.decision:
                    continue  # already at target — no-op, no event noise
                r.set_decision(input.decision, reason=input.reason)
                updated += 1

            if updated > 0:
                campaign.updated_at = datetime.now(UTC)
                await self._campaign_repo.save(campaign)
                events = await self._uow.commit()
            else:
                events = []

        await self._dispatcher.dispatch_all(events)
        return Success(
            BulkSetResultDecisionsOutcome(
                campaign=campaign,
                updated_count=updated,
                missing_ids=missing,
            )
        )
