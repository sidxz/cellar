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
    container.define(
        SQLAlchemyOrganizationRepository,
        lambda c: SQLAlchemyOrganizationRepository(c[AsyncUnitOfWork]),
    )
    container.define(OrganizationRepository, lambda c: c[SQLAlchemyOrganizationRepository])
    container.define(
        SQLAlchemyWorkspaceSettingsRepository,
        lambda c: SQLAlchemyWorkspaceSettingsRepository(c[AsyncUnitOfWork]),
    )
    container.define(WorkspaceSettingsRepository, lambda c: c[SQLAlchemyWorkspaceSettingsRepository])
    container.define(
        SQLAlchemyControlledVocabularyRepository,
        lambda c: SQLAlchemyControlledVocabularyRepository(c[AsyncUnitOfWork]),
    )
    container.define(ControlledVocabularyRepository, lambda c: c[SQLAlchemyControlledVocabularyRepository])

    # Workspace Config use cases
    container.define(
        CreateOrganization,
        lambda c: CreateOrganization(c[UnitOfWork], c[OrganizationRepository]),
    )
    container.define(
        UpdateOrganization,
        lambda c: UpdateOrganization(c[UnitOfWork], c[OrganizationRepository]),
    )
    container.define(
        GetOrganization,
        lambda c: GetOrganization(c[UnitOfWork], c[OrganizationRepository]),
    )
    container.define(
        ListOrganizations,
        lambda c: ListOrganizations(c[UnitOfWork], c[OrganizationRepository]),
    )
    container.define(
        GetWorkspaceSettings,
        lambda c: GetWorkspaceSettings(c[UnitOfWork], c[WorkspaceSettingsRepository]),
    )
    container.define(
        UpdateWorkspaceSettings,
        lambda c: UpdateWorkspaceSettings(c[UnitOfWork], c[WorkspaceSettingsRepository]),
    )
    container.define(
        CreateVocabulary,
        lambda c: CreateVocabulary(c[UnitOfWork], c[ControlledVocabularyRepository]),
    )
    container.define(
        UpdateVocabulary,
        lambda c: UpdateVocabulary(c[UnitOfWork], c[ControlledVocabularyRepository]),
    )
    container.define(
        ListVocabularies,
        lambda c: ListVocabularies(c[UnitOfWork], c[ControlledVocabularyRepository]),
    )
    container.define(
        DeleteVocabulary,
        lambda c: DeleteVocabulary(c[UnitOfWork], c[ControlledVocabularyRepository]),
    )

    return container
