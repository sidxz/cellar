"""SetResultDecision — set the screener's per-compound decision on a DRAFT campaign.

Accepts SELECTED, DEFERRED, or REJECTED along with an optional free-text
reason and notes. The campaign must be in DRAFT status; closed and superseded
campaigns are immutable.
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
from cellar.domain.research_organization.enums import CampaignDecision, CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
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
class SetResultDecisionCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID
    decision: CampaignDecision
    reason: str | None = None
    # UNSET means "don't touch"; None means "clear the notes"
    notes: str | _Unset | None = UNSET  # type: ignore[assignment]


class SetResultDecision:
    """Set the screener's decision (SELECTED / DEFERRED / REJECTED) on a result row.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
      4. Find the result by id on ``campaign.results``; NotFoundError if missing.
      5. ``result.set_decision(cmd.decision, reason=cmd.reason)``.
      6. Bump ``campaign.updated_at``.
      7. Save + commit inside UoW; dispatch events; return ``Success(campaign)``.
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
        input: SetResultDecisionCommand,
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
                    ValidationError(f"Cannot set decision: campaign is {campaign.status.value}")
                )

            result = next((r for r in campaign.results if r.id == input.result_id), None)
            if result is None:
                return Failure(NotFoundError("CampaignResult", str(input.result_id)))

            result.set_decision(input.decision, reason=input.reason)
            if not isinstance(input.notes, _Unset):
                result.notes = input.notes  # type: ignore[assignment]
            campaign.updated_at = datetime.now(UTC)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
