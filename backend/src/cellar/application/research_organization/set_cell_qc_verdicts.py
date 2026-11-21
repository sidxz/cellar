"""SetCellQcVerdicts — a person's QC verdict (verified / failed / not tested) on many cells.

One call names its cells as targets: a set of columns times a set of rows, where the
rows are listed ids, every row (``result_ids=None``), or the rows the results search
returns for a stage/outcome/filters (``where``; DAIKON's Hits tab is paged, so it cannot
list ids for "verify all"). Overlapping targets mark each cell once.

Patterned on ``SetStageOverride``: draft only (423 otherwise), the note and every target
validated before anything is applied, one aggregate save (none when nothing changed).
There is deliberately no ``managed_elsewhere`` check: QC is curation, open from
ChemCellar and the managing app.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.campaign_identity_reader import (
    CampaignIdentityReader,
)
from cellar.application.research_organization.campaign_row_selection import (
    RowSelection,
    select_campaign_rows,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_measurement import (
    QcApplyOutcome,
    normalize_qc_note,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import UNSET
from cellar.domain.research_organization.enums import CampaignStatus, QcVerdict
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.stage_evaluation import StageOutcomes, evaluate_stages
from cellar.domain.shared.errors import (
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class QcTarget:
    channel_ids: tuple[uuid.UUID, ...]
    #: Those rows; ``None`` (with no ``where``) is every row of the campaign.
    result_ids: tuple[uuid.UUID, ...] | None = None
    #: The rows the results search returns; never together with ``result_ids``.
    where: RowSelection | None = None


@dataclass(frozen=True, kw_only=True)
class SetCellQcVerdictsCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    user_id: uuid.UUID
    verdict: QcVerdict | None  # None = not tested
    targets: tuple[QcTarget, ...]
    #: Verified/Failed only: also replace the other verdict (and re-stamp a named note).
    overwrite: bool = False
    #: UNSET = not named: a cell already holding the verdict keeps its note and stamp.
    #: None or blank = "no note": with ``overwrite`` it re-stamps and removes one.
    note: str | object | None = UNSET


@dataclass(frozen=True)
class QcVerdictCounts:
    changed: int
    unchanged: int
    kept: int
    no_result: int


Cell = tuple[CampaignResult, uuid.UUID]


class SetCellQcVerdicts:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        identity_reader: CampaignIdentityReader,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._identity_reader = identity_reader
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SetCellQcVerdictsCommand, auth: AuthContext | None = None
    ) -> Result[QcVerdictCounts, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        if not input.targets:
            return Failure(ValidationError("targets must not be empty"))
        try:
            # Checked once, before any cell; each cell normalizes it again.
            normalize_qc_note(input.verdict, input.note if isinstance(input.note, str) else None)
        except ValidationError as e:
            return Failure(e)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))
            if campaign.status != CampaignStatus.DRAFT:
                return Failure(DataLockedError(f"Campaign is {campaign.status.value}"))

            expanded = await self._cells(campaign, input.targets)
            if isinstance(expanded, Failure):
                return expanded

            at = datetime.now(UTC)
            tally: Counter[QcApplyOutcome] = Counter()
            for result, channel_id in expanded.unwrap():
                m = result.find_measurement(channel_id)
                if m is None:
                    tally[QcApplyOutcome.NO_RESULT] += 1
                    continue
                outcome = m.apply_qc_verdict(
                    input.verdict,
                    by=input.user_id,
                    at=at,
                    note=input.note,
                    overwrite=input.overwrite,
                )
                tally[outcome] += 1

            counts = QcVerdictCounts(
                changed=tally[QcApplyOutcome.CHANGED],
                unchanged=tally[QcApplyOutcome.UNCHANGED],
                kept=tally[QcApplyOutcome.KEPT],
                no_result=tally[QcApplyOutcome.NO_RESULT],
            )
            # Nothing changed: no save, so no version bump to conflict with a concurrent writer.
            if not counts.changed:
                return Success(counts)
            campaign.updated_at = at
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(counts)

    async def _cells(
        self, campaign: Campaign, targets: tuple[QcTarget, ...]
    ) -> Result[list[Cell], DomainError]:
        """Every target's cells, deduped in first-seen order; the first bad id fails all."""
        channels = {ch.id for ch in campaign.channels}
        by_id = {r.id: r for r in campaign.results}
        outcomes: StageOutcomes | None = None
        cells: dict[tuple[uuid.UUID, uuid.UUID], Cell] = {}
        for target in targets:
            if not target.channel_ids:
                return Failure(ValidationError("channel_ids must not be empty"))
            if target.result_ids is not None and target.where is not None:
                return Failure(ValidationError("a target takes result_ids or where, not both"))
            unknown = next((c for c in target.channel_ids if c not in channels), None)
            if unknown is not None:
                return Failure(NotFoundError("CampaignChannel", str(unknown)))

            if target.where is not None:
                if outcomes is None:
                    outcomes = evaluate_stages(campaign)
                selected = await select_campaign_rows(
                    campaign,
                    target.where,
                    outcomes=outcomes,
                    identity_reader=self._identity_reader,
                )
                if isinstance(selected, Failure):
                    return selected
                rows = selected.unwrap()
            elif target.result_ids is None:
                rows = campaign.results
            else:
                missing = next((rid for rid in target.result_ids if rid not in by_id), None)
                if missing is not None:
                    return Failure(NotFoundError("CampaignResult", str(missing)))
                rows = [by_id[rid] for rid in target.result_ids]

            for row in rows:
                for channel_id in target.channel_ids:
                    cells.setdefault((row.id, channel_id), (row, channel_id))
        return Success(list(cells.values()))
