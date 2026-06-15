"""End-to-end async path against the real DB.

Start (> inline_threshold) -> real NullSarActivityProjectionOrchestrator -> real
RunActivityProjection (real MoleculeActivityService) -> Postgres -> projection
reaches READY. ``inline_threshold=1`` forces the async branch on a tiny set. No
screening data is seeded, so value_count is 0 — this test exercises the job
plumbing, not enrich correctness (that is unit-tested in test_activity_channel /
test_activity_enrichment).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection
from cellar.application.sar_analysis.start_activity_projection import (
    StartActivityProjection,
    StartActivityProjectionInput,
)
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjectionStatus
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.orchestrators.sar_activity_projection import (
    NullSarActivityProjectionOrchestrator,
)


async def _seed_molecules(session_factory, ws, n):
    org_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(n)]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'org-e2e-ap', 'internal', true, 1)"
            ),
            {"id": org_id, "ws": ws},
        )
        for i, mid in enumerate(ids):
            await session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                    "molecule_type, smiles, version, originating_org_id) VALUES "
                    "(:id, :ws, :r, :r, 'small_molecule', 'Fc1ccccc1', 1, :org)"
                ),
                {"id": mid, "ws": ws, "r": f"E2E-AP-{i}", "org": org_id},
            )
        await session.commit()
    return ids


def _members(uow):
    return DecompositionMemberStream(
        molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
        collection_reader=SQLAlchemyCollectionRepository(uow),
    )


def _enricher(uow):
    return MoleculeActivityService(
        uow=uow,
        readout_repo=SQLAlchemyReadoutDataRepository(uow),
        curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        protocol_repo=SQLAlchemyProtocolRepository(uow),
        run_repo=SQLAlchemyRunRepository(uow),
    )


def _channel():
    return ActivityChannelSpec(
        column="drc:" + str(uuid.uuid4()),
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )


@pytest.mark.asyncio
async def test_async_projection_completes_via_null_orchestrator(session_factory):
    ws = uuid.uuid4()
    ids = await _seed_molecules(session_factory, ws, n=3)

    run_uow = AsyncUnitOfWork(session_factory)
    runner = RunActivityProjection(
        members=_members(run_uow),
        enricher=_enricher(run_uow),
        repository=SQLAlchemySarActivityProjectionRepository(run_uow),
        uow=run_uow,
    )
    orchestrator = NullSarActivityProjectionOrchestrator(runner)

    start_uow = AsyncUnitOfWork(session_factory)
    start = StartActivityProjection(
        members=_members(start_uow),
        enricher=_enricher(start_uow),
        repository=SQLAlchemySarActivityProjectionRepository(start_uow),
        orchestrator=orchestrator,
        uow=start_uow,
        inline_threshold=1,  # 3 members force the async (202) branch
    )

    proj = await start.execute(
        StartActivityProjectionInput(
            workspace_id=ws,
            requested_by=uuid.uuid4(),
            collection_id=None,
            molecule_ids=ids,
            channel=_channel(),
            now=datetime.now(UTC),
        )
    )
    assert proj.status == SarActivityProjectionStatus.PENDING  # scheduled, not inline

    assert orchestrator._tasks, "orchestrator should have scheduled a background run"
    await asyncio.gather(*list(orchestrator._tasks))

    verify_uow = AsyncUnitOfWork(session_factory)
    async with verify_uow:
        repo = SQLAlchemySarActivityProjectionRepository(verify_uow)
        final = await repo.find_by_id(proj.id, workspace_id=ws)
        n_values = await repo.count_values(proj.id, workspace_id=ws)

    assert final is not None
    assert final.status == SarActivityProjectionStatus.READY
    assert final.value_count == 0  # no screening data seeded -> sparse, empty
    assert n_values == 0
