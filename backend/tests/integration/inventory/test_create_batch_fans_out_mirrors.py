"""Integration: CreateBatch fans out mirrors from existing molecule synonyms."""

from __future__ import annotations

import pytest
from returns.pipeline import is_successful

from cellar.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_create_batch_fans_out_mirrors_from_existing_synonyms(
    session_factory, seeded_workspace_and_molecule, fake_event_dispatcher, editor_auth,
):
    workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

    # Add a 2nd molecule synonym so we have 2 to fan out from.
    uow_seed = AsyncUnitOfWork(session_factory)
    mol_repo_seed = SQLAlchemyMoleculeRepository(uow_seed)
    async with uow_seed:
        mol = await mol_repo_seed.find_by_id_in_workspace(workspace_id, molecule_id)
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id,
                identifier="VENDOR-FOO",
                identifier_type="custom",
                source="lab notebook",
                registered_by=actor,
            )
        )
        await mol_repo_seed.save(mol)
        await uow_seed.commit()

    uow = AsyncUnitOfWork(session_factory)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    batch_repo = SQLAlchemyBatchRepository(uow)
    sync = SyncBatchIdentifierMirrors(batch_repo)
    use_case = CreateBatch(
        uow, batch_repo, mol_repo, fake_event_dispatcher,
        custom_field_validator=None, workspace_settings_repo=None, sync=sync,
    )

    result = await use_case(
        CreateBatchCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            source=BatchSource.SYNTHESIZED.value,
            chemist=actor,
            amount_value=10.0,
            amount_unit="mg",
        ),
        auth=editor_auth,
    )

    assert is_successful(result), f"Expected success but got: {result}"
    outcome = result.unwrap()
    assert outcome.mirror_summary.created == 2  # "SACC-0001" + "VENDOR-FOO"

    uow2 = AsyncUnitOfWork(session_factory)
    repo2 = SQLAlchemyBatchRepository(uow2)
    async with uow2:
        loaded = await repo2.find_by_id_in_workspace(workspace_id, outcome.batch.id)
    suffix = loaded.batch_number.value.rsplit("-", 1)[-1]
    mirror_strings = {
        bi.identifier
        for bi in loaded.identifiers
        if bi.derived_from_molecule_identifier_id is not None
    }
    assert mirror_strings == {f"SACC-0001-{suffix}", f"VENDOR-FOO-{suffix}"}
