"""FastAPI dependency functions — resolve services from Lagom container.

Usage in route handlers::

    @router.post("/molecules")
    async def create_molecule(
        uow: UoWDep,
        dispatcher: EventDispatcherDep,
    ):
        ...
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from lagom import Container

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.chemical_registration.disclosure_service import DisclosureService
from chem_vault.application.chemical_registration.get_disclosure import GetDisclosure
from chem_vault.application.chemical_registration.get_molecule import GetMolecule
from chem_vault.application.chemical_registration.list_disclosures import ListDisclosures
from chem_vault.application.chemical_registration.list_molecules import ListMolecules
from chem_vault.application.chemical_registration.merge_service import MergeService
from chem_vault.application.chemical_registration.register_molecule import RegisterMolecule
from chem_vault.application.chemical_registration.update_molecule import UpdateMolecule
from chem_vault.application.user.get_preferences import GetPreferences
from chem_vault.application.user.update_preferences import UpdatePreferences
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
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.sentinel.auth import get_sentinel


def get_container(request: Request) -> Container:
    """Retrieve the DI container from app state."""
    return request.app.state.container


def get_uow(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncUnitOfWork:
    """Request-scoped Unit of Work."""
    return container[AsyncUnitOfWork]


def get_event_dispatcher(
    container: Annotated[Container, Depends(get_container)],
) -> EventDispatcher:
    """Singleton event dispatcher."""
    return container[EventDispatcher]


def get_audit_service(
    container: Annotated[Container, Depends(get_container)],
) -> AuditRecordingService:
    """Audit recording service."""
    return container[AuditRecordingService]


def get_preferences_query(
    container: Annotated[Container, Depends(get_container)],
) -> GetPreferences:
    """GetPreferences use case."""
    return container[GetPreferences]


def get_preferences_command(
    container: Annotated[Container, Depends(get_container)],
) -> UpdatePreferences:
    """UpdatePreferences use case."""
    return container[UpdatePreferences]


# Sentinel auth dependency — stable wrapper so dependency_overrides work in tests.
# _sentinel.get_auth is a property returning a new callable each time, so we wrap it.
_sentinel = get_sentinel()
_sentinel_get_auth = _sentinel.get_auth  # capture once


async def get_auth(auth: Annotated[Any, Depends(_sentinel_get_auth)]) -> Any:
    """Stable auth dependency wrapper — overridable via dependency_overrides."""
    return auth


# Convenience type aliases for route handler signatures
AuthDep = Annotated[Any, Depends(get_auth)]
UoWDep = Annotated[UnitOfWork, Depends(get_uow)]
EventDispatcherDep = Annotated[EventDispatcher, Depends(get_event_dispatcher)]
AuditServiceDep = Annotated[AuditRecordingService, Depends(get_audit_service)]
GetPreferencesDep = Annotated[GetPreferences, Depends(get_preferences_query)]
UpdatePreferencesDep = Annotated[UpdatePreferences, Depends(get_preferences_command)]


# --- Workspace Config dependencies ---
def _get_use_case(uc_type: type):  # noqa: ANN001
    def _dep(container: Annotated[Container, Depends(get_container)]):  # noqa: ANN001
        return container[uc_type]
    return _dep


CreateOrganizationDep = Annotated[CreateOrganization, Depends(_get_use_case(CreateOrganization))]
UpdateOrganizationDep = Annotated[UpdateOrganization, Depends(_get_use_case(UpdateOrganization))]
GetOrganizationDep = Annotated[GetOrganization, Depends(_get_use_case(GetOrganization))]
ListOrganizationsDep = Annotated[ListOrganizations, Depends(_get_use_case(ListOrganizations))]
GetWorkspaceSettingsDep = Annotated[GetWorkspaceSettings, Depends(_get_use_case(GetWorkspaceSettings))]
UpdateWorkspaceSettingsDep = Annotated[UpdateWorkspaceSettings, Depends(_get_use_case(UpdateWorkspaceSettings))]
CreateVocabularyDep = Annotated[CreateVocabulary, Depends(_get_use_case(CreateVocabulary))]
UpdateVocabularyDep = Annotated[UpdateVocabulary, Depends(_get_use_case(UpdateVocabulary))]
ListVocabulariesDep = Annotated[ListVocabularies, Depends(_get_use_case(ListVocabularies))]
DeleteVocabularyDep = Annotated[DeleteVocabulary, Depends(_get_use_case(DeleteVocabulary))]

# --- Chemical Registration dependencies ---
RegisterMoleculeDep = Annotated[RegisterMolecule, Depends(_get_use_case(RegisterMolecule))]
GetMoleculeDep = Annotated[GetMolecule, Depends(_get_use_case(GetMolecule))]
ListMoleculesDep = Annotated[ListMolecules, Depends(_get_use_case(ListMolecules))]
UpdateMoleculeDep = Annotated[UpdateMolecule, Depends(_get_use_case(UpdateMolecule))]

# --- Disclosure & Merge dependencies ---
DisclosureServiceDep = Annotated[DisclosureService, Depends(_get_use_case(DisclosureService))]
MergeServiceDep = Annotated[MergeService, Depends(_get_use_case(MergeService))]
GetDisclosureDep = Annotated[GetDisclosure, Depends(_get_use_case(GetDisclosure))]
ListDisclosuresDep = Annotated[ListDisclosures, Depends(_get_use_case(ListDisclosures))]
