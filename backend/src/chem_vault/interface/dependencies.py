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
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.audit.query_audit import GetAuditOperation, ListAuditOperations
from chem_vault.application.chemical_registration.bulk_registration_service import BulkRegistrationService
from chem_vault.application.chemical_registration.export_sdf import ExportMoleculesSDF
from chem_vault.application.chemical_registration.create_relationship import CreateRelationship
from chem_vault.application.chemical_registration.delete_relationship import DeleteRelationship
from chem_vault.application.chemical_registration.disclosure_service import DisclosureService
from chem_vault.application.chemical_registration.get_disclosure import GetDisclosure
from chem_vault.application.chemical_registration.identifiers import (
    AddIdentifier,
    ListIdentifiers,
    RemoveIdentifier,
)
from chem_vault.application.chemical_registration.get_molecule import GetMolecule
from chem_vault.application.chemical_registration.get_molecule_by_identifier import GetMoleculeByIdentifier
from chem_vault.application.chemical_registration.get_merge_history import GetMergeHistory
from chem_vault.application.chemical_registration.list_relationships import ListRelationships
from chem_vault.application.chemical_registration.resolve_disclosure_conflict import ResolveDisclosureConflict
from chem_vault.application.chemical_registration.list_disclosures import ListDisclosures
from chem_vault.application.chemical_registration.list_disclosures_by_workspace import ListDisclosuresByWorkspace
from chem_vault.application.chemical_registration.list_molecules import ListMolecules
from chem_vault.application.chemical_registration.merge_service import MergeService
from chem_vault.application.chemical_registration.register_molecule import RegisterMolecule
from chem_vault.application.chemical_registration.search_molecules import SearchMolecules
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
from chem_vault.application.inventory.delete_storage_location import DeleteStorageLocation
from chem_vault.application.inventory.update_storage_location import UpdateStorageLocation
from chem_vault.application.research_organization.archive_project import ArchiveProject
from chem_vault.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    ListCollectionMolecules,
    RemoveMoleculesFromCollection,
)
from chem_vault.application.research_organization.create_collection import CreateCollection
from chem_vault.application.research_organization.create_project import CreateProject
from chem_vault.application.research_organization.create_saved_search import CreateSavedSearch
from chem_vault.application.research_organization.delete_collection import DeleteCollection
from chem_vault.application.research_organization.delete_saved_search import DeleteSavedSearch
from chem_vault.application.research_organization.get_collection import GetCollection, ListCollections
from chem_vault.application.research_organization.get_project import GetProject, ListProjects
from chem_vault.application.research_organization.get_saved_search import GetSavedSearch, ListSavedSearches
from chem_vault.application.research_organization.update_collection import UpdateCollection
from chem_vault.application.research_organization.update_project import UpdateProject
from chem_vault.application.research_organization.update_saved_search import UpdateSavedSearch
from chem_vault.application.screening.plate_templates import (
    CreatePlateTemplate,
    DeletePlateTemplate,
    GetPlateTemplate,
    ListPlateTemplates,
    UpdatePlateTemplate,
)
from chem_vault.application.screening.create_dose_response import CreateDoseResponseCurve
from chem_vault.application.screening.create_protocol import CreateProtocol
from chem_vault.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from chem_vault.application.screening.create_readout_data import CreateReadoutData
from chem_vault.application.screening.create_run import CreateRun
from chem_vault.application.screening.create_target import CreateTarget
from chem_vault.application.screening.get_dose_response import ListDoseResponseByRun
from chem_vault.application.screening.get_protocol import GetProtocol, ListProtocols
from chem_vault.application.screening.get_readout_data import ListReadoutDataByRun
from chem_vault.application.screening.get_run import GetRun, ListRunsByProtocol
from chem_vault.application.screening.get_target import GetTarget, ListTargets
from chem_vault.application.screening.lock_run import LockRun, UnlockRun
from chem_vault.application.screening.manage_protocol import PublishProtocol, RetireProtocol, VersionProtocol
from chem_vault.application.screening.manage_run import ApproveRun, CompleteRun, RejectRun, StartRun
from chem_vault.application.screening.update_run import UpdateRun
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


def get_session_factory(
    container: Annotated[Container, Depends(get_container)],
) -> async_sessionmaker:
    """Async session factory."""
    return container[async_sessionmaker]


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
# Lazy init: don't crash at import time if Sentinel env vars aren't set.
# Uses a reject-all stub when Sentinel is unavailable so auth is never bypassed.


async def _sentinel_not_configured() -> None:
    """Stub dependency that rejects all requests when Sentinel is not configured."""
    from fastapi import HTTPException

    raise HTTPException(
        status_code=503,
        detail="Sentinel auth not configured. Set SENTINEL_URL and SENTINEL_SERVICE_KEY.",
    )


try:
    _sentinel = get_sentinel()
    _sentinel_get_auth = _sentinel.get_auth
except (ValueError, Exception):
    _sentinel = None
    _sentinel_get_auth = _sentinel_not_configured


async def get_auth(auth: Annotated[Any, Depends(_sentinel_get_auth)]) -> Any:
    """Stable auth dependency wrapper — overridable via dependency_overrides."""
    return auth


# Convenience type aliases for route handler signatures
AuthDep = Annotated[Any, Depends(get_auth)]
UoWDep = Annotated[UnitOfWork, Depends(get_uow)]
SessionFactoryDep = Annotated[async_sessionmaker, Depends(get_session_factory)]
EventDispatcherDep = Annotated[EventDispatcher, Depends(get_event_dispatcher)]
AuditServiceDep = Annotated[AuditRecordingService, Depends(get_audit_service)]
GetPreferencesDep = Annotated[GetPreferences, Depends(get_preferences_query)]
UpdatePreferencesDep = Annotated[UpdatePreferences, Depends(get_preferences_command)]


# --- Generic use-case dependency factory ---
def _get_use_case(uc_type: type):  # noqa: ANN001
    def _dep(container: Annotated[Container, Depends(get_container)]):  # noqa: ANN001
        return container[uc_type]
    return _dep


# --- Audit query dependencies ---
ListAuditOperationsDep = Annotated[ListAuditOperations, Depends(_get_use_case(ListAuditOperations))]
GetAuditOperationDep = Annotated[GetAuditOperation, Depends(_get_use_case(GetAuditOperation))]

# --- Workspace Config dependencies ---
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
SearchMoleculesDep = Annotated[SearchMolecules, Depends(_get_use_case(SearchMolecules))]
ExportMoleculesSDFDep = Annotated[ExportMoleculesSDF, Depends(_get_use_case(ExportMoleculesSDF))]
GetMoleculeByIdentifierDep = Annotated[GetMoleculeByIdentifier, Depends(_get_use_case(GetMoleculeByIdentifier))]
AddIdentifierDep = Annotated[AddIdentifier, Depends(_get_use_case(AddIdentifier))]
RemoveIdentifierDep = Annotated[RemoveIdentifier, Depends(_get_use_case(RemoveIdentifier))]
ListIdentifiersDep = Annotated[ListIdentifiers, Depends(_get_use_case(ListIdentifiers))]
CreateRelationshipDep = Annotated[CreateRelationship, Depends(_get_use_case(CreateRelationship))]
ListRelationshipsDep = Annotated[ListRelationships, Depends(_get_use_case(ListRelationships))]
DeleteRelationshipDep = Annotated[DeleteRelationship, Depends(_get_use_case(DeleteRelationship))]

# --- Disclosure & Merge dependencies ---
DisclosureServiceDep = Annotated[DisclosureService, Depends(_get_use_case(DisclosureService))]
MergeServiceDep = Annotated[MergeService, Depends(_get_use_case(MergeService))]
GetDisclosureDep = Annotated[GetDisclosure, Depends(_get_use_case(GetDisclosure))]
ListDisclosuresDep = Annotated[ListDisclosures, Depends(_get_use_case(ListDisclosures))]
ListDisclosuresByWorkspaceDep = Annotated[ListDisclosuresByWorkspace, Depends(_get_use_case(ListDisclosuresByWorkspace))]
ResolveDisclosureConflictDep = Annotated[ResolveDisclosureConflict, Depends(_get_use_case(ResolveDisclosureConflict))]
GetMergeHistoryDep = Annotated[GetMergeHistory, Depends(_get_use_case(GetMergeHistory))]
BulkRegistrationServiceDep = Annotated[BulkRegistrationService, Depends(_get_use_case(BulkRegistrationService))]

# --- Inventory dependencies ---
UpdateStorageLocationDep = Annotated[UpdateStorageLocation, Depends(_get_use_case(UpdateStorageLocation))]
DeleteStorageLocationDep = Annotated[DeleteStorageLocation, Depends(_get_use_case(DeleteStorageLocation))]

# --- Screening dependencies ---
CreateProtocolDep = Annotated[CreateProtocol, Depends(_get_use_case(CreateProtocol))]
GetProtocolDep = Annotated[GetProtocol, Depends(_get_use_case(GetProtocol))]
ListProtocolsDep = Annotated[ListProtocols, Depends(_get_use_case(ListProtocols))]
PublishProtocolDep = Annotated[PublishProtocol, Depends(_get_use_case(PublishProtocol))]
RetireProtocolDep = Annotated[RetireProtocol, Depends(_get_use_case(RetireProtocol))]
VersionProtocolDep = Annotated[VersionProtocol, Depends(_get_use_case(VersionProtocol))]
CreateTargetDep = Annotated[CreateTarget, Depends(_get_use_case(CreateTarget))]
GetTargetDep = Annotated[GetTarget, Depends(_get_use_case(GetTarget))]
ListTargetsDep = Annotated[ListTargets, Depends(_get_use_case(ListTargets))]
CreateRunDep = Annotated[CreateRun, Depends(_get_use_case(CreateRun))]
GetRunDep = Annotated[GetRun, Depends(_get_use_case(GetRun))]
ListRunsByProtocolDep = Annotated[ListRunsByProtocol, Depends(_get_use_case(ListRunsByProtocol))]
StartRunDep = Annotated[StartRun, Depends(_get_use_case(StartRun))]
CompleteRunDep = Annotated[CompleteRun, Depends(_get_use_case(CompleteRun))]
ApproveRunDep = Annotated[ApproveRun, Depends(_get_use_case(ApproveRun))]
RejectRunDep = Annotated[RejectRun, Depends(_get_use_case(RejectRun))]
LockRunDep = Annotated[LockRun, Depends(_get_use_case(LockRun))]
UpdateRunDep = Annotated[UpdateRun, Depends(_get_use_case(UpdateRun))]
UnlockRunDep = Annotated[UnlockRun, Depends(_get_use_case(UnlockRun))]
CreateReadoutDataDep = Annotated[CreateReadoutData, Depends(_get_use_case(CreateReadoutData))]
BulkCreateReadoutDataDep = Annotated[BulkCreateReadoutData, Depends(_get_use_case(BulkCreateReadoutData))]
ListReadoutDataByRunDep = Annotated[ListReadoutDataByRun, Depends(_get_use_case(ListReadoutDataByRun))]
CreateDoseResponseCurveDep = Annotated[CreateDoseResponseCurve, Depends(_get_use_case(CreateDoseResponseCurve))]
ListDoseResponseByRunDep = Annotated[ListDoseResponseByRun, Depends(_get_use_case(ListDoseResponseByRun))]

# --- Plate Template dependencies ---
CreatePlateTemplateDep = Annotated[CreatePlateTemplate, Depends(_get_use_case(CreatePlateTemplate))]
UpdatePlateTemplateDep = Annotated[UpdatePlateTemplate, Depends(_get_use_case(UpdatePlateTemplate))]
DeletePlateTemplateDep = Annotated[DeletePlateTemplate, Depends(_get_use_case(DeletePlateTemplate))]
GetPlateTemplateDep = Annotated[GetPlateTemplate, Depends(_get_use_case(GetPlateTemplate))]
ListPlateTemplatesDep = Annotated[ListPlateTemplates, Depends(_get_use_case(ListPlateTemplates))]

# --- Research Organization dependencies ---
CreateProjectDep = Annotated[CreateProject, Depends(_get_use_case(CreateProject))]
UpdateProjectDep = Annotated[UpdateProject, Depends(_get_use_case(UpdateProject))]
ArchiveProjectDep = Annotated[ArchiveProject, Depends(_get_use_case(ArchiveProject))]
GetProjectDep = Annotated[GetProject, Depends(_get_use_case(GetProject))]
ListProjectsDep = Annotated[ListProjects, Depends(_get_use_case(ListProjects))]
CreateCollectionDep = Annotated[CreateCollection, Depends(_get_use_case(CreateCollection))]
UpdateCollectionDep = Annotated[UpdateCollection, Depends(_get_use_case(UpdateCollection))]
DeleteCollectionDep = Annotated[DeleteCollection, Depends(_get_use_case(DeleteCollection))]
GetCollectionDep = Annotated[GetCollection, Depends(_get_use_case(GetCollection))]
ListCollectionsDep = Annotated[ListCollections, Depends(_get_use_case(ListCollections))]
AddMoleculesToCollectionDep = Annotated[AddMoleculesToCollection, Depends(_get_use_case(AddMoleculesToCollection))]
RemoveMoleculesFromCollectionDep = Annotated[RemoveMoleculesFromCollection, Depends(_get_use_case(RemoveMoleculesFromCollection))]
ListCollectionMoleculesDep = Annotated[ListCollectionMolecules, Depends(_get_use_case(ListCollectionMolecules))]
CreateSavedSearchDep = Annotated[CreateSavedSearch, Depends(_get_use_case(CreateSavedSearch))]
UpdateSavedSearchDep = Annotated[UpdateSavedSearch, Depends(_get_use_case(UpdateSavedSearch))]
DeleteSavedSearchDep = Annotated[DeleteSavedSearch, Depends(_get_use_case(DeleteSavedSearch))]
GetSavedSearchDep = Annotated[GetSavedSearch, Depends(_get_use_case(GetSavedSearch))]
ListSavedSearchesDep = Annotated[ListSavedSearches, Depends(_get_use_case(ListSavedSearches))]
