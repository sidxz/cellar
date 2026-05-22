"""Integration: AddIdentifier fans out auto-mirrors to every batch."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from returns.result import Success

from cellar.application.chemical_registration.identifiers import (
    AddIdentifier,
    AddIdentifierCommand,
)
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _insert_batch(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    batch_id: uuid.UUID,
    bn: str,
    actor: uuid.UUID,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, "
            "amount_value, amount_unit, source, chemist, version) "
            "VALUES (:id, :ws, :mol, :bn, 10.0, 'mg', 'synthesized', :chem, 1)"
        ),
        {"id": batch_id, "ws": ws_id, "mol": mol_id, "bn": bn, "chem": actor},
    )


@pytest.mark.integration
class TestAddIdentifierFansOutMirrors:

    async def test_add_identifier_creates_one_mirror_per_existing_batch(
        self,
        session_factory,
        seeded_workspace_and_molecule,
        fake_event_dispatcher,
        editor_auth,
    ) -> None:
        workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

        # Seed 3 batches for the molecule.
        uow_seed = AsyncUnitOfWork(session_factory)
        async with uow_seed:
            for i in (1, 2, 3):
                await _insert_batch(
                    uow_seed,
                    molecule_id,
                    workspace_id,
                    uuid.uuid4(),
                    f"CC-000001-00{i}",
                    actor,
                )
            await uow_seed.commit()

        # Run AddIdentifier with fan-out wiring.
        uow = AsyncUnitOfWork(session_factory)
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        use_case = AddIdentifier(
            uow, mol_repo, fake_event_dispatcher, sync=sync, batch_repo=batch_repo
        )

        result = await use_case(
            AddIdentifierCommand(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                identifier="VENDOR-FOO",
                identifier_type="custom",
                source="lab notebook",
                registered_by=actor,
            ),
            auth=editor_auth,
        )

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.mirror_summary.created == 3
        assert outcome.mirror_summary.skipped == []

        # Verify persisted mirrors.
        uow2 = AsyncUnitOfWork(session_factory)
        batch_repo2 = SQLAlchemyBatchRepository(uow2)
        async with uow2:
            all_batches = await batch_repo2.find_by_molecule(workspace_id, molecule_id)
        mirror_strings = {
            bi.identifier
            for b in all_batches
            for bi in b.identifiers
            if bi.derived_from_molecule_identifier_id is not None
        }
        assert mirror_strings == {"VENDOR-FOO-001", "VENDOR-FOO-002", "VENDOR-FOO-003"}

    async def test_add_identifier_no_batches_returns_zero_mirrors(
        self,
        session_factory,
        seeded_workspace_and_molecule,
        fake_event_dispatcher,
        editor_auth,
    ) -> None:
        workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

        uow = AsyncUnitOfWork(session_factory)
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        use_case = AddIdentifier(
            uow, mol_repo, fake_event_dispatcher, sync=sync, batch_repo=batch_repo
        )

        result = await use_case(
            AddIdentifierCommand(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                identifier="NO-BATCH-SYNONYM",
                identifier_type="custom",
                source="lab notebook",
                registered_by=actor,
            ),
            auth=editor_auth,
        )

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.mirror_summary.created == 0
        assert outcome.mirror_summary.skipped == []
        assert outcome.molecule.id == molecule_id
