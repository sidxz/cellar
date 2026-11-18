"""AddResultsFromRuns — add runs to a stage (or the campaign) and their compounds as rows (B6).

The import itself is ``preview_run_import.apply_run_import``, shared with the preview
so the committed cells are exactly the previewed ones. This use case loads, guards
and saves:

- DRAFT only (campaign lock guard).
- The runs join ``stage_id``, else the ``stage_name`` stage (created or reused, by
  case-insensitive name, under ``parent_stage_id``), else they are campaign runs.
- Every target column is recomputed for every row over all of the stage's runs, so a
  mean across runs means every run added so far, not the latest request's
  (spec §6.3). Manual overrides are never rewritten.
- ``scope='hits_only'`` adds the compounds whose recomputed values pass the request's
  thresholds (``filter_mode`` any/all). The thresholds replace the stage's criteria
  only when some config carries one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.add_results_from_collection import (
    AddResultsOutcome,
)
from cellar.application.research_organization.column_resolution import ColumnCandidateQuery
from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
    apply_run_import,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AddResultsFromRunsCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfig]
    filter_mode: Literal["any", "all"] = "all"
    scope: Literal["hits_only", "all"] = "hits_only"
    description: str | None = None
    #: The stage the runs join; its columns take the configs. None with no
    #: ``stage_name`` adds campaign runs feeding campaign columns.
    stage_id: uuid.UUID | None = None
    #: When no ``stage_id``: creates (or reuses, by case-insensitive name) this stage
    #: and puts the runs and columns on it.
    stage_name: str | None = None
    #: Parent for the stage ``stage_name`` creates, making it a child in the
    #: funnel. On reuse of an existing stage, ``None`` leaves the current
    #: parent alone.
    parent_stage_id: uuid.UUID | None = None


@dataclass
class AddFromRunsOutcome(AddResultsOutcome):
    """Extends the shared AddResultsOutcome with channel counts."""

    channels_created: int = 0
    channels_reused: int = 0
    stage_created: bool = False


class AddResultsFromRuns:
    """Adds runs to a stage, ensures its columns, recomputes them and adds the rows."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        run_repo: RunRepository,
        query: ColumnCandidateQuery,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._run_repo = run_repo
        self._query = query
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddResultsFromRunsCommand,
        auth: AuthContext | None = None,
    ) -> Result[AddFromRunsOutcome, DomainError]:
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
                    ValidationError(f"Cannot add results: campaign is {campaign.status.value}")
                )
            if not input.run_ids:
                return Failure(ValidationError("At least one run_id is required"))
            if not input.channel_configs:
                return Failure(ValidationError("At least one channel_config is required"))

            runs = await self._run_repo.find_by_ids(input.workspace_id, input.run_ids)
            try:
                imp = await apply_run_import(
                    campaign,
                    query=self._query,
                    runs=runs,
                    run_ids=input.run_ids,
                    configs=input.channel_configs,
                    filter_mode=input.filter_mode,
                    scope=input.scope,
                    description=input.description,
                    stage_id=input.stage_id,
                    stage_name=input.stage_name,
                    parent_stage_id=input.parent_stage_id,
                )
            except (NotFoundError, ValidationError) as e:
                return Failure(e)

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            AddFromRunsOutcome(
                campaign=campaign,
                added=imp.added,
                skipped=imp.skipped,
                channels_created=imp.reused.count(False),
                channels_reused=imp.reused.count(True),
                stage_created=imp.stage_created,
            )
        )
