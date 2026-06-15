"""Integration: the registration activity's _create_batch (used by CDD import +
bulk registration) fans out batch identifier mirrors from the molecule's
synonyms, and honors the workspace's configured batch-number width.

Regression test for the activity hand-building CreateBatch without the
SyncBatchIdentifierMirrors / WorkspaceSettingsRepository dependencies — so
imported batches silently lost their synonym aliases and always used the
default sequence width.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (  # noqa: E501
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.activities.dtos import ChunkItem
from cellar.infrastructure.temporal.activities.registration import _create_batch


async def _add_molecule_identifier(
    session_factory, workspace_id, molecule_id, actor, identifier: str
) -> None:
    uow = AsyncUnitOfWork(session_factory)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    async with uow:
        mol = await mol_repo.find_by_id_in_workspace(workspace_id, molecule_id)
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id,
                identifier=identifier,
                identifier_type="custom",
                source="lab notebook",
                registered_by=actor,
            )
        )
        await mol_repo.save(mol)
        await uow.commit()


@pytest.mark.asyncio
async def test_create_batch_fans_out_mirrors_from_molecule_synonyms(
    session_factory,
    seeded_workspace_and_molecule,
    fake_event_dispatcher,
):
    """A batch created during import carries the molecule's synonyms as `<id>-NNN`."""
    workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

    # Molecule already has "SACC-0001"; add a 2nd synonym so we fan out from 2.
    await _add_molecule_identifier(session_factory, workspace_id, molecule_id, actor, "VENDOR-FOO")

    # Mimic the post-registration state the activity passes into _create_batch:
    # the molecule already exists with its identifiers; the batch is created after.
    reg_outcome = SimpleNamespace(
        molecule=SimpleNamespace(id=molecule_id, descriptors=None),
        detected_salt=None,
    )
    item = ChunkItem(row_index=0, name="Test Mol", smiles="c1ccccc1")

    batch_id, _batch_number, _salt_matched = await _create_batch(
        item=item,
        reg_outcome=reg_outcome,
        workspace_id=workspace_id,
        submitted_by=actor,
        session_factory=session_factory,
        dispatcher=fake_event_dispatcher,
    )

    assert batch_id is not None, "batch should have been created"

    uow = AsyncUnitOfWork(session_factory)
    repo = SQLAlchemyBatchRepository(uow)
    async with uow:
        loaded = await repo.find_by_id_in_workspace(workspace_id, batch_id)

    suffix = loaded.batch_number.value.rsplit("-", 1)[-1]
    mirror_strings = {
        bi.identifier
        for bi in loaded.identifiers
        if bi.derived_from_molecule_identifier_id is not None
    }
    assert mirror_strings == {f"SACC-0001-{suffix}", f"VENDOR-FOO-{suffix}"}


@pytest.mark.asyncio
async def test_create_batch_honors_workspace_batch_sequence_width(
    session_factory,
    seeded_workspace_and_molecule,
    fake_event_dispatcher,
):
    """The imported batch uses the workspace's configured batch_sequence_width,
    not the hard-coded default (3)."""
    workspace_id, molecule_id, _seed_ident_id, actor = seeded_workspace_and_molecule

    # Configure a non-default batch sequence width (default is 3).
    settings_uow = AsyncUnitOfWork(session_factory)
    settings_repo = SQLAlchemyWorkspaceSettingsRepository(settings_uow)
    async with settings_uow:
        await settings_repo.save(
            WorkspaceSettings(id=workspace_id, registration_rules={"batch_sequence_width": 5})
        )
        await settings_uow.commit()

    reg_outcome = SimpleNamespace(
        molecule=SimpleNamespace(id=molecule_id, descriptors=None),
        detected_salt=None,
    )
    item = ChunkItem(row_index=0, name="Test Mol", smiles="c1ccccc1")

    _batch_id, batch_number, _salt_matched = await _create_batch(
        item=item,
        reg_outcome=reg_outcome,
        workspace_id=workspace_id,
        submitted_by=actor,
        session_factory=session_factory,
        dispatcher=fake_event_dispatcher,
    )

    assert batch_number is not None, "batch should have been created"
    suffix = batch_number.rsplit("-", 1)[-1]
    assert len(suffix) == 5, f"expected width-5 sequence, got {batch_number!r}"
