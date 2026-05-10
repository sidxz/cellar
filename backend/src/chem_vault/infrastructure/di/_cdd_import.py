"""CDD Vault import bindings: protocol, molecule, and plate imports."""

from __future__ import annotations

import httpx
from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.cdd_import.cancel_cdd_molecule_import import (
    CancelCddMoleculeImport,
)
from chem_vault.application.cdd_import.cancel_cdd_plate_import import CancelCddPlateImport
from chem_vault.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportOrchestrator,
)
from chem_vault.application.cdd_import.cdd_plate_import_orchestrator import (
    CddPlateImportOrchestrator,
)
from chem_vault.application.cdd_import.force_fail_cdd_molecule_import import (
    ForceFailCddMoleculeImport,
)
from chem_vault.application.cdd_import.force_fail_cdd_plate_import import ForceFailCddPlateImport
from chem_vault.application.cdd_import.get_cdd_molecule_import_runtime_status import (
    GetCddMoleculeImportRuntimeStatus,
)
from chem_vault.application.cdd_import.get_cdd_molecule_import_status import (
    GetCddMoleculeImportStatusFromDb,
    SyncFailedCddMoleculeImport,
)
from chem_vault.application.cdd_import.get_cdd_plate_import_runtime_status import (
    GetCddPlateImportRuntimeStatus,
)
from chem_vault.application.cdd_import.get_cdd_plate_import_status import (
    GetCddPlateImportStatusFromDb,
    SyncFailedCddPlateImport,
)
from chem_vault.application.cdd_import.import_cdd_protocol import ImportCddProtocol
from chem_vault.application.cdd_import.list_cdd_molecule_imports import ListCddMoleculeImports
from chem_vault.application.cdd_import.list_cdd_plate_imports import ListCddPlateImports
from chem_vault.application.cdd_import.list_cdd_protocols import ListCddProtocols
from chem_vault.application.cdd_import.preview_cdd_protocol_import import PreviewCddProtocolImport
from chem_vault.application.cdd_import.start_cdd_molecule_import import StartCddMoleculeImport
from chem_vault.application.cdd_import.start_cdd_plate_import import StartCddPlateImport
from chem_vault.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.infrastructure.cdd.client import CddVaultClient
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_import_repository import (
    SQLAlchemyCddMoleculeImportRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_repository import (
    SQLAlchemyCddPlateImportRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.data_source_repository import (
    SQLAlchemyDataSourceRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.external_api_key_repository import (
    SQLAlchemyExternalApiKeyRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_cdd_import(container: Container) -> None:
    # CDD client reuses the shared httpx.AsyncClient registered in _core.
    container.define(CddVaultClient, Singleton(lambda c: CddVaultClient(c[httpx.AsyncClient])))

    # --- CDD Protocol Import ---
    def _make_get_data_source(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetDataSourceForImport(
            uow=uow,
            ds_repo=SQLAlchemyDataSourceRepository(uow),
            api_key_repo=SQLAlchemyExternalApiKeyRepository(uow),
            secret_provider=c[SecretProvider],
        )

    def _cdd_query(uc_cls: type):
        def _f(c: Container):
            return uc_cls(
                gateway=c[CddVaultClient],
                get_data_source=_make_get_data_source(c),
            )
        return _f

    def _cdd_import_cmd(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportCddProtocol(
            gateway=c[CddVaultClient],
            get_data_source=_make_get_data_source(c),
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(ListCddProtocols, _cdd_query(ListCddProtocols))
    container.define(PreviewCddProtocolImport, _cdd_query(PreviewCddProtocolImport))
    container.define(ImportCddProtocol, _cdd_import_cmd)

    # --- CDD Molecule Import ---
    def _start_cdd_mol_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        get_ds = GetDataSourceForImport(
            uow=uow,
            ds_repo=SQLAlchemyDataSourceRepository(uow),
            api_key_repo=SQLAlchemyExternalApiKeyRepository(uow),
            secret_provider=c[SecretProvider],
        )
        return StartCddMoleculeImport(
            get_data_source=get_ds,
            orchestrator=c[CddMoleculeImportOrchestrator],
        )

    def _list_cdd_mol_imports(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListCddMoleculeImports(
            uow=uow,
            repo=SQLAlchemyCddMoleculeImportRepository(uow),
        )

    def _force_fail_cdd_mol_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ForceFailCddMoleculeImport(
            uow=uow,
            repo=SQLAlchemyCddMoleculeImportRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(StartCddMoleculeImport, _start_cdd_mol_import)
    container.define(ListCddMoleculeImports, _list_cdd_mol_imports)
    container.define(ForceFailCddMoleculeImport, _force_fail_cdd_mol_import)

    def _get_cdd_mol_import_status_from_db(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetCddMoleculeImportStatusFromDb(
            uow=uow,
            repo=SQLAlchemyCddMoleculeImportRepository(uow),
        )

    def _sync_failed_cdd_mol_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SyncFailedCddMoleculeImport(
            uow=uow,
            repo=SQLAlchemyCddMoleculeImportRepository(uow),
        )

    container.define(GetCddMoleculeImportStatusFromDb, _get_cdd_mol_import_status_from_db)
    container.define(SyncFailedCddMoleculeImport, _sync_failed_cdd_mol_import)

    container.define(
        GetCddMoleculeImportRuntimeStatus,
        lambda c: GetCddMoleculeImportRuntimeStatus(
            orchestrator=c[CddMoleculeImportOrchestrator],
            db_status=c[GetCddMoleculeImportStatusFromDb],
            sync_failed=c[SyncFailedCddMoleculeImport],
        ),
    )
    container.define(
        CancelCddMoleculeImport,
        lambda c: CancelCddMoleculeImport(orchestrator=c[CddMoleculeImportOrchestrator]),
    )

    # --- CDD Plate Import ---
    def _start_cdd_plate_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        get_ds = GetDataSourceForImport(
            uow=uow,
            ds_repo=SQLAlchemyDataSourceRepository(uow),
            api_key_repo=SQLAlchemyExternalApiKeyRepository(uow),
            secret_provider=c[SecretProvider],
        )
        return StartCddPlateImport(
            get_data_source=get_ds,
            orchestrator=c[CddPlateImportOrchestrator],
        )

    def _list_cdd_plate_imports(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListCddPlateImports(
            uow=uow,
            repo=SQLAlchemyCddPlateImportRepository(uow),
        )

    def _force_fail_cdd_plate_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ForceFailCddPlateImport(
            uow=uow,
            repo=SQLAlchemyCddPlateImportRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(StartCddPlateImport, _start_cdd_plate_import)
    container.define(ListCddPlateImports, _list_cdd_plate_imports)
    container.define(ForceFailCddPlateImport, _force_fail_cdd_plate_import)

    def _get_cdd_plate_import_status_from_db(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetCddPlateImportStatusFromDb(
            uow=uow,
            repo=SQLAlchemyCddPlateImportRepository(uow),
        )

    def _sync_failed_cdd_plate_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SyncFailedCddPlateImport(
            uow=uow,
            repo=SQLAlchemyCddPlateImportRepository(uow),
        )

    container.define(GetCddPlateImportStatusFromDb, _get_cdd_plate_import_status_from_db)
    container.define(SyncFailedCddPlateImport, _sync_failed_cdd_plate_import)

    container.define(
        GetCddPlateImportRuntimeStatus,
        lambda c: GetCddPlateImportRuntimeStatus(
            orchestrator=c[CddPlateImportOrchestrator],
            db_status=c[GetCddPlateImportStatusFromDb],
            sync_failed=c[SyncFailedCddPlateImport],
        ),
    )
    container.define(
        CancelCddPlateImport,
        lambda c: CancelCddPlateImport(orchestrator=c[CddPlateImportOrchestrator]),
    )
