"""Integration: EnsureBatchExists fans out mirrors on the create branch."""

from __future__ import annotations

import pytest
from returns.pipeline import is_successful

from cellar.application.inventory.ensure_batch_exists import (
    EnsureBatchExists,
    EnsureBatchExistsCommand,
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
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.asyncio
async def test_create_branch_fans_out_mirrors(
    session_factory, seeded_workspace_and_molecule,
):
    workspace_id, molecule_id, _ident_id, actor = seeded_workspace_and_molecule

    uow = AsyncUnitOfWork(session_factory)
    batch_repo = SQLAlchemyBatchRepository(uow)
    settings_repo = SQLAlchemyWorkspaceSettingsRepository(uow)
    mol_repo = SQLAlchemyMoleculeRepository(uow)
    sync = SyncBatchIdentifierMirrors(batch_repo)
    use_case = EnsureBatchExists(
        uow=uow, batch_repo=batch_repo, settings_repo=settings_repo,
        molecule_repo=mol_repo, sync=sync,
    )

    # The EXT-LOT-Z9 ref will miss the alias lookup, triggering the create branch.
    result = await use_case(
        EnsureBatchExistsCommand(
            workspace_id=workspace_id,
            molecule_id=molecule_id,
            external_batch_ref="EXT-LOT-Z9",
            importing_user_id=actor,
            source_label="screening import test",
        ),
    )

    assert is_successful(result), f"Expected success but got: {result}"
    outcome = result.unwrap()
    assert outcome.created is True

    uow2 = AsyncUnitOfWork(session_factory)
    repo2 = SQLAlchemyBatchRepository(uow2)
    async with uow2:
        loaded = await repo2.find_by_id_in_workspace(workspace_id, outcome.batch.id)

    by_str = {bi.identifier: bi for bi in loaded.identifiers}
    assert "EXT-LOT-Z9" in by_str  # the trigger alias (chemist input, NULL FK)
    assert by_str["EXT-LOT-Z9"].derived_from_molecule_identifier_id is None
    mirror_keys = [k for k, v in by_str.items()
                   if v.derived_from_molecule_identifier_id is not None]
    assert len(mirror_keys) == 1
    assert mirror_keys[0].startswith("SACC-0001-")  # the seeded synonym, suffixed
