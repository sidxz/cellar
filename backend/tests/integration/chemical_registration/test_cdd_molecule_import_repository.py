"""The CDD import record keeps what a resume needs, real DB."""

from __future__ import annotations

import uuid

from cellar.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from cellar.domain.chemical_registration.enums import CddImportMode, CddMoleculeImportStatus
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_import_repository import (  # noqa: E501
    SQLAlchemyCddMoleculeImportRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration.chemical_registration.conftest import _ensure_org

SETTINGS = {"registration_mapping": [{"header": "name", "target": "name"}], "max_molecules": 5}


async def _load(session_factory, ws_id: uuid.UUID, imp_id: uuid.UUID) -> CddMoleculeImport:  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        found = await SQLAlchemyCddMoleculeImportRepository(uow).find_by_id_in_workspace(
            ws_id, imp_id
        )
    assert found is not None
    return found


async def _save(session_factory, imp: CddMoleculeImport) -> None:  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyCddMoleculeImportRepository(uow).save(imp)
        await uow.commit()


async def test_export_id_and_run_settings_round_trip(session_factory) -> None:  # type: ignore[no-untyped-def]
    ws_id = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _ensure_org(uow.session, ws_id, ws_id)
        await uow.commit()
    imp = CddMoleculeImport.create(
        workspace_id=ws_id,
        cdd_vault_id="4443",
        import_mode=CddImportMode.FULL_VAULT,
        originating_org_id=ws_id,
        submitted_by=uuid.uuid4(),
        workflow_id="wf-1",
        run_settings=SETTINGS,
    )
    imp.start_discovery()
    imp.complete_discovery(10, export_id=82939461)
    await _save(session_factory, imp)

    loaded = await _load(session_factory, ws_id, imp.id)
    assert (loaded.cdd_export_id, loaded.run_settings) == (82939461, SETTINGS)

    loaded.fail("chunk failed")
    await _save(session_factory, loaded)
    failed = await _load(session_factory, ws_id, imp.id)
    assert failed.resumable
    assert failed.failure_reason == "chunk failed"

    failed.resume("wf-2", resumed_by=uuid.uuid4())
    await _save(session_factory, failed)
    resumed = await _load(session_factory, ws_id, imp.id)
    assert (resumed.status, resumed.workflow_id) == (CddMoleculeImportStatus.PROCESSING, "wf-2")
    assert resumed.completed_at is None
    assert resumed.failure_reason is None
