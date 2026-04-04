"""Lagom composition root — wires all dependencies for the application.

Usage::

    container = create_container(db_settings)

    # In FastAPI dependencies:
    uow = container[AsyncUnitOfWork]
"""

from __future__ import annotations

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.chemical_registration.get_molecule import GetMolecule
from chem_vault.application.chemical_registration.list_molecules import ListMolecules
from chem_vault.application.chemical_registration.register_molecule import RegisterMolecule
from chem_vault.application.chemical_registration.update_molecule import UpdateMolecule
from chem_vault.application.user.get_preferences import GetPreferences
from chem_vault.application.user.update_preferences import UpdatePreferences
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.application.workspace_config.create_organization import CreateOrganization
from chem_vault.application.workspace_config.create_vocabulary import CreateVocabulary
from chem_vault.application.workspace_config.delete_vocabulary import DeleteVocabulary
from chem_vault.application.workspace_config.get_organization import GetOrganization
from chem_vault.application.workspace_config.get_workspace_settings import GetWorkspaceSettings
from chem_vault.application.workspace_config.list_organizations import ListOrganizations
from chem_vault.application.workspace_config.list_vocabularies import ListVocabularies
from chem_vault.application.workspace_config.update_organization import UpdateOrganization
from chem_vault.application.workspace_config.update_vocabulary import UpdateVocabulary
from chem_vault.application.workspace_config.update_workspace_settings import UpdateWorkspaceSettings
from chem_vault.domain.audit_compliance.repository import AuditRepository
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.shared.user_preferences import UserPreferencesRepository
from chem_vault.domain.workspace_config.repository import (
    ControlledVocabularyRepository,
    OrganizationRepository,
    WorkspaceSettingsRepository,
)
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from chem_vault.infrastructure.persistence.settings import DatabaseSettings
from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.infrastructure.rdkit.structure_processor import StructureProcessor
from chem_vault.infrastructure.persistence.sqlalchemy.user_preferences_repository import (
    SQLAlchemyUserPreferencesRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (
    SQLAlchemyControlledVocabularyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.organization_repository import (
    SQLAlchemyOrganizationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def create_container(
    db_settings: DatabaseSettings | None = None,
) -> Container:
    """Build and return the fully-wired DI container.

    Singletons: engine, session_factory, event_dispatcher
    Per-resolve: UoW, repositories, services
    """
    container = Container()

    # --- Database ---
    settings = db_settings or DatabaseSettings()  # type: ignore[call-arg]
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    container.define(AsyncEngine, Singleton(lambda: engine))
    container.define(
        async_sessionmaker, Singleton(lambda: session_factory)
    )
    container.define(
        AsyncUnitOfWork, lambda c: AsyncUnitOfWork(c[async_sessionmaker])
    )
    container.define(UnitOfWork, lambda c: c[AsyncUnitOfWork])

    # --- Event Dispatcher (singleton) ---
    container.define(EventDispatcher, Singleton(EventDispatcher))

    # --- Audit ---
    container.define(
        SQLAlchemyAuditRepository,
        lambda c: SQLAlchemyAuditRepository(c[async_sessionmaker]()),
    )
    container.define(AuditRepository, lambda c: c[SQLAlchemyAuditRepository])
    container.define(
        AuditRecordingService,
        lambda c: AuditRecordingService(c[AuditRepository]),
    )

    # --- User Preferences ---
    container.define(
        SQLAlchemyUserPreferencesRepository,
        lambda c: SQLAlchemyUserPreferencesRepository(c[async_sessionmaker]()),
    )
    container.define(
        UserPreferencesRepository, lambda c: c[SQLAlchemyUserPreferencesRepository]
    )
    container.define(
        GetPreferences,
        lambda c: GetPreferences(c[UserPreferencesRepository]),
    )
    container.define(
        UpdatePreferences,
        lambda c: UpdatePreferences(c[UserPreferencesRepository]),
    )

    # --- Workspace Config ---
    # Each use case gets a shared UoW + repo pair.
    # Command use cases also get the event dispatcher.

    def _org_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOrganizationRepository(uow), c[EventDispatcher])
        return _f

    def _org_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOrganizationRepository(uow))
        return _f

    def _settings_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyWorkspaceSettingsRepository(uow), c[EventDispatcher])
        return _f

    def _settings_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyWorkspaceSettingsRepository(uow))
        return _f

    def _vocab_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyControlledVocabularyRepository(uow), c[EventDispatcher])
        return _f

    def _vocab_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyControlledVocabularyRepository(uow))
        return _f

    container.define(CreateOrganization, _org_cmd(CreateOrganization))
    container.define(UpdateOrganization, _org_cmd(UpdateOrganization))
    container.define(GetOrganization, _org_query(GetOrganization))
    container.define(ListOrganizations, _org_query(ListOrganizations))
    container.define(GetWorkspaceSettings, _settings_query(GetWorkspaceSettings))
    container.define(UpdateWorkspaceSettings, _settings_cmd(UpdateWorkspaceSettings))
    container.define(CreateVocabulary, _vocab_cmd(CreateVocabulary))
    container.define(UpdateVocabulary, _vocab_cmd(UpdateVocabulary))
    container.define(ListVocabularies, _vocab_query(ListVocabularies))
    container.define(DeleteVocabulary, _vocab_query(DeleteVocabulary))

    # --- Chemical Registration ---
    container.define(StructureProcessor, Singleton(StructureProcessor))
    container.define(StructureProcessorProtocol, lambda c: c[StructureProcessor])

    def _mol_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyMoleculeRepository(uow), c[EventDispatcher], c[StructureProcessorProtocol])
        return _f

    def _mol_cmd_no_proc(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyMoleculeRepository(uow), c[EventDispatcher])
        return _f

    def _mol_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyMoleculeRepository(uow))
        return _f

    container.define(RegisterMolecule, _mol_cmd(RegisterMolecule))
    container.define(UpdateMolecule, _mol_cmd_no_proc(UpdateMolecule))
    container.define(GetMolecule, _mol_query(GetMolecule))
    container.define(ListMolecules, _mol_query(ListMolecules))

    return container
