"""AddResultsFromRun — pull molecules tested in a protocol Run into a Campaign.

Extracts distinct molecule_ids from ReadoutData for the given run.
When a molecule has a single batch in the run's ReadoutData, that batch is
carried as representative_batch_id. Multiple batches → picks the first
(intentional pragmatism; iterate later).

Idempotent: re-adding molecules already in the campaign is silently skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success
from sqlalchemy import distinct, func, select

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.research_organization.add_results_from_collection import (
    AddResultsOutcome,
)
from chem_vault.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.research_organization.source_ref import RunRef
from chem_vault.domain.screening_assay.repository import RunRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
)


@dataclass(frozen=True, kw_only=True)
class AddResultsFromRunCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    run_id: uuid.UUID
    description: str | None = None


class AddResultsFromRun:
    """Add results from the molecule set of a protocol run into a DRAFT Campaign.

    Molecules are sourced from ReadoutData (the primary data-bearing table for
    runs). Per-molecule batch id is taken as the single batch if unambiguous,
    or the first encountered batch if multiple batches tested the same molecule.

    Pipeline:
      1. require_editor auth guard.
      2. Load campaign; NotFoundError if missing.
      3. Verify the run exists in this workspace; NotFoundError if missing.
      4. Query ReadoutData for distinct molecule_ids + representative batch_id.
      5. Build CampaignResult rows attributed to RunRef.
      6. campaign.add_results() — idempotent.
      7. Resolve measurements for newly added results.
      8. Save + commit + dispatch.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        run_repo: RunRepository,
        resolver: ChannelResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._run_repo = run_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddResultsFromRunCommand,
        auth: AuthContext | None = None,
    ) -> Result[AddResultsOutcome, DomainError]:
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

            run = await self._run_repo.find_by_id_in_workspace(
                input.workspace_id, input.run_id
            )
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            # Query distinct (molecule_id, batch_id) rows from ReadoutData.
            # We pick the first batch per molecule via MIN(batch_id) for
            # determinism (UUID ordering); pragmatic choice documented in spec.
            stmt = (
                select(
                    ReadoutDataModel.molecule_id,
                    func.min(ReadoutDataModel.batch_id).label("batch_id"),
                )
                .where(
                    ReadoutDataModel.run_id == input.run_id,
                    ReadoutDataModel.workspace_id == input.workspace_id,
                    ReadoutDataModel.molecule_id.is_not(None),
                )
                .group_by(ReadoutDataModel.molecule_id)
            )
            rows = (await self._uow.session.execute(stmt)).all()
            # rows: [(molecule_id, batch_id), ...]

            source_ref = RunRef(run_id=input.run_id, description=input.description)
            new_results = [
                CampaignResult(
                    campaign_id=campaign.id,
                    molecule_id=row.molecule_id,
                    representative_batch_id=row.batch_id,
                    added_from=source_ref,
                )
                for row in rows
                if row.molecule_id is not None
            ]

            try:
                added, skipped = campaign.add_results(new_results)
            except ValidationError as e:
                return Failure(e)

            if added > 0:
                added_molecule_ids = {r.molecule_id for r in new_results}
                for result in campaign.results:
                    if result.molecule_id not in added_molecule_ids:
                        continue
                    for channel in campaign.channels:
                        measurement = await self._resolver.resolve(
                            workspace_id=input.workspace_id,
                            channel=channel,
                            result_id=result.id,
                            molecule_id=result.molecule_id,
                        )
                        result.add_measurement(measurement)

            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(AddResultsOutcome(campaign=campaign, added=added, skipped=skipped))
