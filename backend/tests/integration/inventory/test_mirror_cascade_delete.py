"""Integration: removing a molecule identifier cascade-deletes its batch mirrors."""

from __future__ import annotations

import pytest

from returns.result import Success

from cellar.application.chemical_registration.identifiers import (
    AddIdentifier,
    AddIdentifierCommand,
    RemoveIdentifier,
    RemoveIdentifierCommand,
)
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.integration
class TestMirrorCascadeDelete:

    async def test_remove_identifier_cascades_to_mirrors(
        self,
        session_factory,
        seeded_workspace_and_molecule,
        fake_event_dispatcher,
        editor_auth,
    ) -> None:
        workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

        # Seed 2 batches.
        uow_seed = AsyncUnitOfWork(session_factory)
        batch_repo_seed = SQLAlchemyBatchRepository(uow_seed)
        async with uow_seed:
            for i in (1, 2):
                b = Batch.create(
                    workspace_id=workspace_id,
                    molecule_id=molecule_id,
                    batch_number=BatchNumber(value=f"CC-000001-00{i}"),
                    amount=Amount(value=10.0, unit=AmountUnit.MG),
                    source=BatchSource.SYNTHESIZED,
                    chemist=actor,
                )
                await batch_repo_seed.save(b)
            await uow_seed.commit()

        # Add a synonym → fan out 2 mirrors.
        uow_add = AsyncUnitOfWork(session_factory)
        mol_repo_add = SQLAlchemyMoleculeRepository(uow_add)
        batch_repo_add = SQLAlchemyBatchRepository(uow_add)
        sync = SyncBatchIdentifierMirrors(batch_repo_add)
        add_uc = AddIdentifier(
            uow_add, mol_repo_add, fake_event_dispatcher, sync=sync, batch_repo=batch_repo_add,
        )
        add_result = await add_uc(
            AddIdentifierCommand(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                identifier="VENDOR-FOO",
                identifier_type="custom",
                source="lab",
                registered_by=actor,
            ),
            auth=editor_auth,
        )
        assert isinstance(add_result, Success)
        assert add_result.unwrap().mirror_summary.created == 2

        # Locate the new identifier id.
        new_ident = next(
            i for i in add_result.unwrap().molecule.identifiers
            if i.identifier == "VENDOR-FOO"
        )

        # Confirm 2 mirrors exist before removal.
        uow_chk1 = AsyncUnitOfWork(session_factory)
        batch_repo_chk1 = SQLAlchemyBatchRepository(uow_chk1)
        async with uow_chk1:
            loaded = await batch_repo_chk1.find_by_molecule(workspace_id, molecule_id)
        mirror_strings_before = {
            bi.identifier
            for b in loaded
            for bi in b.identifiers
            if bi.derived_from_molecule_identifier_id is not None
        }
        assert mirror_strings_before == {"VENDOR-FOO-001", "VENDOR-FOO-002"}

        # Remove the molecule identifier — DB cascade should wipe mirrors.
        uow_rm = AsyncUnitOfWork(session_factory)
        mol_repo_rm = SQLAlchemyMoleculeRepository(uow_rm)
        rm_uc = RemoveIdentifier(uow_rm, mol_repo_rm, fake_event_dispatcher)
        rm_result = await rm_uc(
            RemoveIdentifierCommand(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                identifier_id=new_ident.id,
            ),
            auth=editor_auth,
        )
        assert isinstance(rm_result, Success)

        # Verify cascade fired — no mirrors remain.
        uow_chk2 = AsyncUnitOfWork(session_factory)
        batch_repo_chk2 = SQLAlchemyBatchRepository(uow_chk2)
        async with uow_chk2:
            loaded_after = await batch_repo_chk2.find_by_molecule(workspace_id, molecule_id)
        mirror_strings_after = {
            bi.identifier
            for b in loaded_after
            for bi in b.identifiers
            if bi.derived_from_molecule_identifier_id is not None
        }
        assert mirror_strings_after == set()
