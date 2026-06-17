"""End-to-end async path against the real DB.

Start (> inline_threshold) -> real NullRGroupDecompositionOrchestrator ->
real RunDecomposition -> Postgres -> run reaches READY with assignments.

The per-component tests each verify a join against a fake on one side; this test
wires the real Start, the real Null orchestrator, and the real RunDecomposition
together so a contract drift *between* two real components is caught. Uses
``inline_threshold=1`` so a tiny member set still takes the async branch (no need
to seed 200+ rows). The async branch mirrors the production scaffold-tree
fire-and-forget pattern.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.application.sar_analysis.start_decomposition_run import (
    StartDecompositionRun,
    StartDecompositionRunInput,
)
from cellar.domain.shared.async_job import AsyncJobStatus
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.streaming_rgroup_decomposer import StreamingRGroupDecomposer
from cellar.infrastructure.temporal.orchestrators.rgroup_decomposition import (
    NullRGroupDecompositionOrchestrator,
)


async def _seed_molecules(session_factory, ws: uuid.UUID, n: int) -> list[uuid.UUID]:
    org_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(n)]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, :n, 'internal', true, 1)"
            ),
            {"id": org_id, "ws": ws, "n": "org-e2e"},
        )
        for i, mid in enumerate(ids):
            await session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                    "molecule_type, smiles, version, originating_org_id) VALUES "
                    "(:id, :ws, :r, :r, 'small_molecule', :smi, 1, :org)"
                ),
                {"id": mid, "ws": ws, "r": f"E2E-{i}", "smi": "Fc1ccccc1", "org": org_id},
            )
        await session.commit()
    return ids


def _member_stream(uow: AsyncUnitOfWork) -> DecompositionMemberStream:
    # The stream's repos MUST share the use case's UoW (as the DI factory wires
    # them) so they are active inside the use case's ``async with self._uow``.
    return DecompositionMemberStream(
        molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
        collection_reader=SQLAlchemyCollectionRepository(uow),
    )


@pytest.mark.asyncio
async def test_async_path_completes_via_null_orchestrator(session_factory):
    ws = uuid.uuid4()
    ids = await _seed_molecules(session_factory, ws, n=3)
    decomposer = StreamingRGroupDecomposer()  # stateless; safe to share

    # Real RunDecomposition (its own UoW) wrapped by the real Null orchestrator.
    run_uow = AsyncUnitOfWork(session_factory)
    runner = RunDecomposition(
        members=_member_stream(run_uow),
        decomposer=decomposer,
        repository=SQLAlchemyRGroupDecompositionRunRepository(run_uow),
        uow=run_uow,
    )
    orchestrator = NullRGroupDecompositionOrchestrator(runner)

    # Real Start with inline_threshold=1 so 3 members force the async (202) branch.
    start_uow = AsyncUnitOfWork(session_factory)
    start = StartDecompositionRun(
        members=_member_stream(start_uow),
        decomposer=decomposer,
        repository=SQLAlchemyRGroupDecompositionRunRepository(start_uow),
        orchestrator=orchestrator,
        uow=start_uow,
        inline_threshold=1,
    )

    run = await start.execute(
        StartDecompositionRunInput(
            workspace_id=ws,
            requested_by=uuid.uuid4(),
            collection_id=None,
            molecule_ids=ids,
            core_smiles="c1ccccc1",
            now=datetime.now(UTC),
        )
    )
    assert run.status == AsyncJobStatus.PENDING  # scheduled, not inline

    # Drain the fire-and-forget task the Null orchestrator spawned.
    assert orchestrator._tasks, "orchestrator should have scheduled a background run"
    await asyncio.gather(*list(orchestrator._tasks))

    # The real runner should have driven the persisted run to READY with rows.
    verify_uow = AsyncUnitOfWork(session_factory)
    async with verify_uow:
        repo = SQLAlchemyRGroupDecompositionRunRepository(verify_uow)
        final = await repo.find_by_id_in_workspace(ws, run.id)
        assignment_count = await repo.count_assignments(run.id, workspace_id=ws)

    assert final is not None
    assert final.status == AsyncJobStatus.READY
    assert final.matched_count == 3
    assert final.total_count == 3
    assert final.rgroup_labels  # at least one R-position discovered
    assert assignment_count == 3
