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

from chem_vault.application.admin.admin_hard_delete import AdminHardDelete
from chem_vault.application.admin.cascade_preview import CascadePreview
from chem_vault.application.admin.cascade_delete import CascadeDelete
from chem_vault.application.dashboard.get_dashboard_stats import GetDashboardStats
from chem_vault.application.attachment.delete_attachment import DeleteAttachment
from chem_vault.application.attachment.download_attachment import DownloadAttachment
from chem_vault.application.attachment.list_attachments import ListAttachments
from chem_vault.application.attachment.upload_attachment import UploadAttachment
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.audit.query_audit import GetAuditOperation, ListAuditOperations
from chem_vault.application.chemical_registration.bulk_registration_service import BulkRegistrationService
from chem_vault.application.chemical_registration.get_bulk_registration_runtime_status import (
    GetBulkRegistrationRuntimeStatus,
)
from chem_vault.application.chemical_registration.list_bulk_registration_items import (
    ListBulkRegistrationItems,
)
from chem_vault.application.chemical_registration.preview_bulk_registration_file import (
    PreviewBulkRegistrationFile,
)
from chem_vault.application.chemical_registration.start_bulk_registration import (
    StartBulkRegistration,
)
from chem_vault.application.cdd_import.cancel_cdd_molecule_import import (
    CancelCddMoleculeImport,
)
from chem_vault.application.cdd_import.cancel_cdd_plate_import import CancelCddPlateImport
from chem_vault.application.cdd_import.get_cdd_molecule_import_runtime_status import (
    GetCddMoleculeImportRuntimeStatus,
)
from chem_vault.application.cdd_import.get_cdd_plate_import_runtime_status import (
    GetCddPlateImportRuntimeStatus,
)
from chem_vault.application.chemical_registration.export_sdf import ExportMoleculesSDF
from chem_vault.application.chemical_registration.create_relationship import CreateRelationship
from chem_vault.application.chemical_registration.delete_relationship import DeleteRelationship
from chem_vault.application.chemical_registration.confirm_disclosure import ConfirmDisclosure
from chem_vault.application.chemical_registration.depict_molecules import DepictMolecules
from chem_vault.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from chem_vault.application.chemical_registration.disclosure_service import DisclosureService
from chem_vault.application.chemical_registration.get_disclosure import GetDisclosure
from chem_vault.application.chemical_registration.get_merge_impact import GetMergeImpact
from chem_vault.application.chemical_registration.reject_disclosure import RejectDisclosure
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
from chem_vault.application.workspace_config.create_custom_field import CreateCustomField
from chem_vault.application.workspace_config.create_registration_form import CreateRegistrationForm
from chem_vault.application.workspace_config.get_registration_form import GetRegistrationForm
from chem_vault.application.workspace_config.create_salt_entry import CreateSaltEntry
from chem_vault.application.workspace_config.delete_custom_field import DeleteCustomField
from chem_vault.application.workspace_config.delete_registration_form import DeleteRegistrationForm
from chem_vault.application.workspace_config.delete_salt_entry import DeleteSaltEntry
from chem_vault.application.workspace_config.delete_vocabulary import DeleteVocabulary
from chem_vault.application.workspace_config.get_organization import GetOrganization
from chem_vault.application.workspace_config.get_workspace_settings import GetWorkspaceSettings
from chem_vault.application.workspace_config.list_organizations import ListOrganizations
from chem_vault.application.workspace_config.list_custom_fields import ListCustomFields
from chem_vault.application.workspace_config.list_registration_forms import ListRegistrationForms
from chem_vault.application.workspace_config.list_salt_entries import ListSaltEntries
from chem_vault.application.workspace_config.list_vocabularies import ListVocabularies
from chem_vault.application.workspace_config.update_organization import UpdateOrganization
from chem_vault.application.workspace_config.update_custom_field import UpdateCustomField
from chem_vault.application.workspace_config.update_registration_form import UpdateRegistrationForm
from chem_vault.application.workspace_config.update_salt_entry import UpdateSaltEntry
from chem_vault.application.workspace_config.update_vocabulary import UpdateVocabulary
from chem_vault.application.inventory.create_batch import CreateBatch
from chem_vault.application.inventory.create_sample import CreateSample
from chem_vault.application.inventory.delete_storage_location import DeleteStorageLocation
from chem_vault.application.inventory.get_batch import GetBatch, ListBatchesByMolecule
from chem_vault.application.inventory.list_batches_global import ListBatchesGlobal
from chem_vault.application.inventory.list_samples_global import ListSamplesGlobal
from chem_vault.application.inventory.get_sample import GetSample, ListSamplesByBatch
from chem_vault.application.inventory.manage_sample import (
    AliquotSample,
    ClearQuarantineSample,
    DisposeSample,
    MoveSample,
    QuarantineSample,
)
from chem_vault.application.inventory.get_inventory_summary import GetInventorySummary
from chem_vault.application.inventory.manage_storage import (
    CreateStorageLocation,
    GetStorageLocationChildren,
    ListStorageLocations,
    ListStorageLocationsWithCounts,
)
from chem_vault.application.inventory.plate_read_model import PlateReadModelService
from chem_vault.application.inventory.registered_plates import (
    ChangeStatus,
    DeletePlate,
    DerivePlate,
    GetPlate,
    ListChildren,
    ListPlates,
    MapWells,
    RegisterPlate,
    UpdatePlate,
)
from chem_vault.application.inventory.update_batch import UpdateBatch
from chem_vault.application.inventory.update_storage_location import UpdateStorageLocation
from chem_vault.application.research_organization.archive_project import ArchiveProject
from chem_vault.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    ListCollectionMolecules,
    RemoveMoleculesFromCollection,
)
from chem_vault.application.research_organization.compose_collections import ComposeCollections
from chem_vault.application.research_organization.create_collection import CreateCollection
from chem_vault.application.research_organization.count_search import CountSearch
from chem_vault.application.research_organization.execute_search import ExecuteSearch
from chem_vault.application.research_organization.create_project import CreateProject
from chem_vault.application.research_organization.create_saved_search import CreateSavedSearch
from chem_vault.application.research_organization.delete_collection import DeleteCollection
from chem_vault.application.research_organization.delete_saved_search import DeleteSavedSearch
from chem_vault.application.research_organization.get_collection import GetCollection, ListCollections
from chem_vault.application.research_organization.get_collections_for_molecule import ListCollectionsForMolecule
from chem_vault.application.research_organization.get_project import GetProject, ListProjects
from chem_vault.application.research_organization.get_project_scope_stats import (
    GetProjectScopeStats,
)
from chem_vault.application.research_organization.get_saved_search import GetSavedSearch, ListSavedSearches
from chem_vault.application.research_organization.manage_project_members import (
    AddProjectMember,
    ListProjectMembers,
    RemoveProjectMember,
    UpdateProjectMemberRole,
)
from chem_vault.application.research_organization.manage_molecule_projects import (
    AddMoleculeToProject,
    ListMoleculeProjects,
    RemoveMoleculeFromProject,
)
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
from chem_vault.application.screening.create_compound_flag import CreateCompoundFlag
from chem_vault.application.screening.delete_compound_flag import DeleteCompoundFlag
from chem_vault.application.screening.list_compound_flags import ListCompoundFlags
from chem_vault.application.screening.classify_dose_response import ClassifyDoseResponseCurve
from chem_vault.application.screening.create_dose_response import CreateDoseResponseCurve
from chem_vault.application.screening.refit_dose_response import RefitDoseResponseCurve
from chem_vault.application.screening.create_protocol import CreateProtocol
from chem_vault.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from chem_vault.application.screening.create_readout_data import CreateReadoutData
from chem_vault.application.screening.create_run import CreateRun
from chem_vault.application.screening.delete_run import DeleteRun
from chem_vault.application.screening.reset_run_data import ResetRunData
from chem_vault.application.screening.create_target import CreateTarget
from chem_vault.application.screening.get_dose_response import ListDoseResponseByRun
from chem_vault.application.screening.get_protocol import GetProtocol, ListProtocols
from chem_vault.application.screening.list_protocol_summaries import ListProtocolSummaries
from chem_vault.application.screening.get_readout_data import ListReadoutDataByRun
from chem_vault.application.screening.get_run import GetRun, ListRunsByProtocol
from chem_vault.application.screening.get_target import GetTarget, ListTargets
from chem_vault.application.screening.lock_protocol import LockProtocol, UnlockProtocol
from chem_vault.application.screening.lock_run import LockRun, UnlockRun
from chem_vault.application.screening.condition_grouping_service import ConditionGroupingService
from chem_vault.application.screening.delete_target import DeleteTarget
from chem_vault.application.screening.manage_protocol import (
    AddProtocolToProject,
    DeleteProtocol,
    ListProtocolsByProject,
    PublishProtocol,
    RemoveProtocolFromProject,
    RetireProtocol,
    UpdateProtocol,
    VersionProtocol,
)
from chem_vault.application.screening.manage_condition_definitions import (
    AddConditionDefinition,
    RemoveConditionDefinition,
    UpdateConditionDefinition,
)
from chem_vault.application.screening.manage_control_layouts import (
    RemoveControlLayout,
    SetControlLayout,
)
from chem_vault.application.screening.manage_readout_definitions import (
    AddReadoutDefinition,
    RemoveReadoutDefinition,
    UpdateReadoutDefinition,
)
from chem_vault.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from chem_vault.application.screening.update_target import UpdateTarget
from chem_vault.application.screening.manage_run import ApproveRun, CompleteRun, RejectRun, StartRun
from chem_vault.application.screening.update_run import UpdateRun
from chem_vault.application.screening.molecule_activity_service import MoleculeActivityService
from chem_vault.application.screening.get_molecule_activity_detail import GetMoleculeActivityDetail
from chem_vault.application.screening.plate_setup import ParsePlateMapFile, SetUpRunPlate
from chem_vault.application.screening.import_run_readouts import ImportRunReadouts
from chem_vault.application.screening.import_run_file import (
    ImportRunFile,
    PreviewRunFile,
    RepreviewRunFile,
)
from chem_vault.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    DeleteRunImportTemplate,
    ListRunImportTemplates,
    UpdateRunImportTemplate,
)
from chem_vault.application.screening.get_compound_curves import GetCompoundCurves
from chem_vault.application.screening.get_protocol_activity import GetProtocolActivitySummary
from chem_vault.application.screening.get_protocol_stats import GetProtocolStats
from chem_vault.application.cdd_import.import_cdd_protocol import ImportCddProtocol
from chem_vault.application.cdd_import.list_cdd_protocols import ListCddProtocols
from chem_vault.application.cdd_import.force_fail_cdd_molecule_import import ForceFailCddMoleculeImport
from chem_vault.application.cdd_import.list_cdd_molecule_imports import ListCddMoleculeImports
from chem_vault.application.cdd_import.start_cdd_molecule_import import StartCddMoleculeImport
from chem_vault.application.cdd_import.force_fail_cdd_plate_import import ForceFailCddPlateImport
from chem_vault.application.cdd_import.list_cdd_plate_imports import ListCddPlateImports
from chem_vault.application.cdd_import.start_cdd_plate_import import StartCddPlateImport
from chem_vault.application.cdd_import.preview_cdd_protocol_import import PreviewCddProtocolImport
from chem_vault.application.workspace_config.create_data_source import CreateDataSource
from chem_vault.application.workspace_config.get_data_source import GetDataSource
from chem_vault.application.workspace_config.list_data_sources import ListDataSources
from chem_vault.application.workspace_config.update_data_source import UpdateDataSource
from chem_vault.application.workspace_config.delete_data_source import DeleteDataSource
from chem_vault.application.workspace_config.create_external_api_key import CreateExternalApiKey
from chem_vault.application.workspace_config.list_external_api_keys import ListExternalApiKeys
from chem_vault.application.workspace_config.update_external_api_key import UpdateExternalApiKey
from chem_vault.application.workspace_config.delete_external_api_key import DeleteExternalApiKey
from chem_vault.application.workspace_config.create_ontology_slot import CreateOntologySlot
from chem_vault.application.workspace_config.list_ontology_slots import ListOntologySlots
from chem_vault.application.workspace_config.update_ontology_slot import UpdateOntologySlot
from chem_vault.application.workspace_config.delete_ontology_slot import DeleteOntologySlot
from chem_vault.application.workspace_config.create_protocol_form import CreateProtocolForm as CreateProtocolFormUC
from chem_vault.application.workspace_config.list_protocol_forms import ListProtocolForms as ListProtocolFormsUC
from chem_vault.application.workspace_config.update_protocol_form import UpdateProtocolForm as UpdateProtocolFormUC
from chem_vault.application.workspace_config.delete_protocol_form import DeleteProtocolForm as DeleteProtocolFormUC
from chem_vault.application.screening.manage_ontology_annotations import (
    SetOntologyAnnotation,
    RemoveOntologyAnnotation,
)
from chem_vault.application.screening.search_ontology import SearchOntology
from chem_vault.application.workspace_config.update_workspace_settings import UpdateWorkspaceSettings
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.application.inventory.salt_matcher import SaltMatcher
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
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


def get_salt_matcher_uow(
    container: Annotated[Container, Depends(get_container)],
) -> tuple[SaltMatcher, AsyncUnitOfWork]:
    """Per-request ``SaltMatcher`` paired with its own ``AsyncUnitOfWork``.

    Returned as a tuple because the caller manages the UoW lifecycle —
    e.g. ``async with uow: ... await matcher.match_by_smiles(...)``. We
    can't bind the UoW into ``SaltMatcher`` at DI time and return just
    the matcher because the UoW must be entered/exited per call.
    """
    uow = AsyncUnitOfWork(container[async_sessionmaker])
    return SaltMatcher(SQLAlchemySaltEntryRepository(uow)), uow


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
UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
SessionFactoryDep = Annotated[async_sessionmaker, Depends(get_session_factory)]
SaltMatcherUoWDep = Annotated[
    tuple[SaltMatcher, AsyncUnitOfWork], Depends(get_salt_matcher_uow)
]
EventDispatcherDep = Annotated[EventDispatcher, Depends(get_event_dispatcher)]
AuditServiceDep = Annotated[AuditRecordingService, Depends(get_audit_service)]
GetPreferencesDep = Annotated[GetPreferences, Depends(get_preferences_query)]
UpdatePreferencesDep = Annotated[UpdatePreferences, Depends(get_preferences_command)]


# --- Generic use-case dependency factory ---
def _get_use_case(uc_type: type):  # noqa: ANN001
    def _dep(container: Annotated[Container, Depends(get_container)]):  # noqa: ANN001
        return container[uc_type]
    return _dep


# --- Infrastructure singletons exposed to routes ---
FingerprintRegistryDep = Annotated[
    FingerprintRegistry, Depends(_get_use_case(FingerprintRegistry))
]


# --- Admin dependencies ---
AdminHardDeleteDep = Annotated[AdminHardDelete, Depends(_get_use_case(AdminHardDelete))]
CascadePreviewDep = Annotated[CascadePreview, Depends(_get_use_case(CascadePreview))]
CascadeDeleteDep  = Annotated[CascadeDelete,  Depends(_get_use_case(CascadeDelete))]

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
CreateCustomFieldDep = Annotated[CreateCustomField, Depends(_get_use_case(CreateCustomField))]
ListCustomFieldsDep = Annotated[ListCustomFields, Depends(_get_use_case(ListCustomFields))]
UpdateCustomFieldDep = Annotated[UpdateCustomField, Depends(_get_use_case(UpdateCustomField))]
DeleteCustomFieldDep = Annotated[DeleteCustomField, Depends(_get_use_case(DeleteCustomField))]
CreateSaltEntryDep = Annotated[CreateSaltEntry, Depends(_get_use_case(CreateSaltEntry))]
ListSaltEntriesDep = Annotated[ListSaltEntries, Depends(_get_use_case(ListSaltEntries))]
UpdateSaltEntryDep = Annotated[UpdateSaltEntry, Depends(_get_use_case(UpdateSaltEntry))]
DeleteSaltEntryDep = Annotated[DeleteSaltEntry, Depends(_get_use_case(DeleteSaltEntry))]
CreateRegistrationFormDep = Annotated[CreateRegistrationForm, Depends(_get_use_case(CreateRegistrationForm))]
GetRegistrationFormDep = Annotated[GetRegistrationForm, Depends(_get_use_case(GetRegistrationForm))]
ListRegistrationFormsDep = Annotated[ListRegistrationForms, Depends(_get_use_case(ListRegistrationForms))]
UpdateRegistrationFormDep = Annotated[UpdateRegistrationForm, Depends(_get_use_case(UpdateRegistrationForm))]
DeleteRegistrationFormDep = Annotated[DeleteRegistrationForm, Depends(_get_use_case(DeleteRegistrationForm))]

# --- External API Keys dependencies ---
CreateExternalApiKeyDep = Annotated[CreateExternalApiKey, Depends(_get_use_case(CreateExternalApiKey))]
ListExternalApiKeysDep = Annotated[ListExternalApiKeys, Depends(_get_use_case(ListExternalApiKeys))]
UpdateExternalApiKeyDep = Annotated[UpdateExternalApiKey, Depends(_get_use_case(UpdateExternalApiKey))]
DeleteExternalApiKeyDep = Annotated[DeleteExternalApiKey, Depends(_get_use_case(DeleteExternalApiKey))]

# --- Data Source dependencies ---
CreateDataSourceDep = Annotated[CreateDataSource, Depends(_get_use_case(CreateDataSource))]
GetDataSourceDep = Annotated[GetDataSource, Depends(_get_use_case(GetDataSource))]
ListDataSourcesDep = Annotated[ListDataSources, Depends(_get_use_case(ListDataSources))]
UpdateDataSourceDep = Annotated[UpdateDataSource, Depends(_get_use_case(UpdateDataSource))]
DeleteDataSourceDep = Annotated[DeleteDataSource, Depends(_get_use_case(DeleteDataSource))]

# --- Ontology Slot dependencies ---
CreateOntologySlotDep = Annotated[CreateOntologySlot, Depends(_get_use_case(CreateOntologySlot))]
ListOntologySlotsDep = Annotated[ListOntologySlots, Depends(_get_use_case(ListOntologySlots))]
UpdateOntologySlotDep = Annotated[UpdateOntologySlot, Depends(_get_use_case(UpdateOntologySlot))]
DeleteOntologySlotDep = Annotated[DeleteOntologySlot, Depends(_get_use_case(DeleteOntologySlot))]

# --- Ontology Search + Annotation dependencies ---
SearchOntologyDep = Annotated[SearchOntology, Depends(_get_use_case(SearchOntology))]
SetOntologyAnnotationDep = Annotated[SetOntologyAnnotation, Depends(_get_use_case(SetOntologyAnnotation))]
RemoveOntologyAnnotationDep = Annotated[RemoveOntologyAnnotation, Depends(_get_use_case(RemoveOntologyAnnotation))]

# --- Protocol Form dependencies ---
CreateProtocolFormDep = Annotated[CreateProtocolFormUC, Depends(_get_use_case(CreateProtocolFormUC))]
ListProtocolFormsDep = Annotated[ListProtocolFormsUC, Depends(_get_use_case(ListProtocolFormsUC))]
UpdateProtocolFormDep = Annotated[UpdateProtocolFormUC, Depends(_get_use_case(UpdateProtocolFormUC))]
DeleteProtocolFormDep = Annotated[DeleteProtocolFormUC, Depends(_get_use_case(DeleteProtocolFormUC))]

# --- Chemical Registration dependencies ---
RegisterMoleculeDep = Annotated[RegisterMolecule, Depends(_get_use_case(RegisterMolecule))]
GetMoleculeDep = Annotated[GetMolecule, Depends(_get_use_case(GetMolecule))]
ListMoleculesDep = Annotated[ListMolecules, Depends(_get_use_case(ListMolecules))]
UpdateMoleculeDep = Annotated[UpdateMolecule, Depends(_get_use_case(UpdateMolecule))]
SearchMoleculesDep = Annotated[SearchMolecules, Depends(_get_use_case(SearchMolecules))]
DepictMoleculesDep = Annotated[DepictMolecules, Depends(_get_use_case(DepictMolecules))]
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
ConfirmDisclosureDep = Annotated[ConfirmDisclosure, Depends(_get_use_case(ConfirmDisclosure))]
RejectDisclosureDep = Annotated[RejectDisclosure, Depends(_get_use_case(RejectDisclosure))]
GetMergeImpactDep = Annotated[GetMergeImpact, Depends(_get_use_case(GetMergeImpact))]
BulkRegistrationServiceDep = Annotated[BulkRegistrationService, Depends(_get_use_case(BulkRegistrationService))]
StartBulkRegistrationDep = Annotated[
    StartBulkRegistration, Depends(_get_use_case(StartBulkRegistration))
]
GetBulkRegistrationRuntimeStatusDep = Annotated[
    GetBulkRegistrationRuntimeStatus,
    Depends(_get_use_case(GetBulkRegistrationRuntimeStatus)),
]
PreviewBulkRegistrationFileDep = Annotated[
    PreviewBulkRegistrationFile, Depends(_get_use_case(PreviewBulkRegistrationFile))
]
ListBulkRegistrationItemsDep = Annotated[
    ListBulkRegistrationItems, Depends(_get_use_case(ListBulkRegistrationItems))
]

# --- Inventory dependencies ---
CreateBatchDep = Annotated[CreateBatch, Depends(_get_use_case(CreateBatch))]
GetBatchDep = Annotated[GetBatch, Depends(_get_use_case(GetBatch))]
ListBatchesByMoleculeDep = Annotated[ListBatchesByMolecule, Depends(_get_use_case(ListBatchesByMolecule))]
ListBatchesGlobalDep = Annotated[ListBatchesGlobal, Depends(_get_use_case(ListBatchesGlobal))]
UpdateBatchDep = Annotated[UpdateBatch, Depends(_get_use_case(UpdateBatch))]
CreateSampleDep = Annotated[CreateSample, Depends(_get_use_case(CreateSample))]
GetSampleDep = Annotated[GetSample, Depends(_get_use_case(GetSample))]
ListSamplesByBatchDep = Annotated[ListSamplesByBatch, Depends(_get_use_case(ListSamplesByBatch))]
ListSamplesGlobalDep = Annotated[ListSamplesGlobal, Depends(_get_use_case(ListSamplesGlobal))]
AliquotSampleDep = Annotated[AliquotSample, Depends(_get_use_case(AliquotSample))]
MoveSampleDep = Annotated[MoveSample, Depends(_get_use_case(MoveSample))]
QuarantineSampleDep = Annotated[QuarantineSample, Depends(_get_use_case(QuarantineSample))]
ClearQuarantineSampleDep = Annotated[ClearQuarantineSample, Depends(_get_use_case(ClearQuarantineSample))]
DisposeSampleDep = Annotated[DisposeSample, Depends(_get_use_case(DisposeSample))]
CreateStorageLocationDep = Annotated[CreateStorageLocation, Depends(_get_use_case(CreateStorageLocation))]
ListStorageLocationsDep = Annotated[ListStorageLocations, Depends(_get_use_case(ListStorageLocations))]
GetStorageLocationChildrenDep = Annotated[GetStorageLocationChildren, Depends(_get_use_case(GetStorageLocationChildren))]
ListStorageLocationsWithCountsDep = Annotated[ListStorageLocationsWithCounts, Depends(_get_use_case(ListStorageLocationsWithCounts))]
GetInventorySummaryDep = Annotated[GetInventorySummary, Depends(_get_use_case(GetInventorySummary))]
UpdateStorageLocationDep = Annotated[UpdateStorageLocation, Depends(_get_use_case(UpdateStorageLocation))]
DeleteStorageLocationDep = Annotated[DeleteStorageLocation, Depends(_get_use_case(DeleteStorageLocation))]
RegisterPlateDep = Annotated[RegisterPlate, Depends(_get_use_case(RegisterPlate))]
GetPlateDep = Annotated[GetPlate, Depends(_get_use_case(GetPlate))]
ListPlatesDep = Annotated[ListPlates, Depends(_get_use_case(ListPlates))]
UpdatePlateDep = Annotated[UpdatePlate, Depends(_get_use_case(UpdatePlate))]
MapWellsDep = Annotated[MapWells, Depends(_get_use_case(MapWells))]
ChangeStatusDep = Annotated[ChangeStatus, Depends(_get_use_case(ChangeStatus))]
DerivePlateDep = Annotated[DerivePlate, Depends(_get_use_case(DerivePlate))]
ListChildrenDep = Annotated[ListChildren, Depends(_get_use_case(ListChildren))]
DeletePlateDep = Annotated[DeletePlate, Depends(_get_use_case(DeletePlate))]
PlateReadModelServiceDep = Annotated[PlateReadModelService, Depends(_get_use_case(PlateReadModelService))]

# --- Screening dependencies ---
CreateProtocolDep = Annotated[CreateProtocol, Depends(_get_use_case(CreateProtocol))]
GetProtocolDep = Annotated[GetProtocol, Depends(_get_use_case(GetProtocol))]
ListProtocolsDep = Annotated[ListProtocols, Depends(_get_use_case(ListProtocols))]
ListProtocolSummariesDep = Annotated[
    ListProtocolSummaries, Depends(_get_use_case(ListProtocolSummaries))
]
PublishProtocolDep = Annotated[PublishProtocol, Depends(_get_use_case(PublishProtocol))]
RetireProtocolDep = Annotated[RetireProtocol, Depends(_get_use_case(RetireProtocol))]
LockProtocolDep = Annotated[LockProtocol, Depends(_get_use_case(LockProtocol))]
UnlockProtocolDep = Annotated[UnlockProtocol, Depends(_get_use_case(UnlockProtocol))]
VersionProtocolDep = Annotated[VersionProtocol, Depends(_get_use_case(VersionProtocol))]
ListProtocolsByProjectDep = Annotated[ListProtocolsByProject, Depends(_get_use_case(ListProtocolsByProject))]
AddProtocolToProjectDep = Annotated[AddProtocolToProject, Depends(_get_use_case(AddProtocolToProject))]
RemoveProtocolFromProjectDep = Annotated[RemoveProtocolFromProject, Depends(_get_use_case(RemoveProtocolFromProject))]
UpdateProtocolDep = Annotated[UpdateProtocol, Depends(_get_use_case(UpdateProtocol))]
DeleteProtocolDep = Annotated[DeleteProtocol, Depends(_get_use_case(DeleteProtocol))]
AddReadoutDefinitionDep = Annotated[AddReadoutDefinition, Depends(_get_use_case(AddReadoutDefinition))]
RemoveReadoutDefinitionDep = Annotated[RemoveReadoutDefinition, Depends(_get_use_case(RemoveReadoutDefinition))]
UpdateReadoutDefinitionDep = Annotated[UpdateReadoutDefinition, Depends(_get_use_case(UpdateReadoutDefinition))]
AddConditionDefinitionDep = Annotated[AddConditionDefinition, Depends(_get_use_case(AddConditionDefinition))]
RemoveConditionDefinitionDep = Annotated[RemoveConditionDefinition, Depends(_get_use_case(RemoveConditionDefinition))]
UpdateConditionDefinitionDep = Annotated[UpdateConditionDefinition, Depends(_get_use_case(UpdateConditionDefinition))]
SetControlLayoutDep = Annotated[SetControlLayout, Depends(_get_use_case(SetControlLayout))]
RemoveControlLayoutDep = Annotated[RemoveControlLayout, Depends(_get_use_case(RemoveControlLayout))]
CreateTargetDep = Annotated[CreateTarget, Depends(_get_use_case(CreateTarget))]
GetTargetDep = Annotated[GetTarget, Depends(_get_use_case(GetTarget))]
ListTargetsDep = Annotated[ListTargets, Depends(_get_use_case(ListTargets))]
UpdateTargetDep = Annotated[UpdateTarget, Depends(_get_use_case(UpdateTarget))]
DeleteTargetDep = Annotated[DeleteTarget, Depends(_get_use_case(DeleteTarget))]
ConditionGroupingServiceDep = Annotated[ConditionGroupingService, Depends(_get_use_case(ConditionGroupingService))]
CreateRunDep = Annotated[CreateRun, Depends(_get_use_case(CreateRun))]
DeleteRunDep = Annotated[DeleteRun, Depends(_get_use_case(DeleteRun))]
ResetRunDataDep = Annotated[ResetRunData, Depends(_get_use_case(ResetRunData))]
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
RefitDoseResponseCurveDep = Annotated[RefitDoseResponseCurve, Depends(_get_use_case(RefitDoseResponseCurve))]
ClassifyDoseResponseCurveDep = Annotated[ClassifyDoseResponseCurve, Depends(_get_use_case(ClassifyDoseResponseCurve))]
MoleculeActivityServiceDep = Annotated[MoleculeActivityService, Depends(_get_use_case(MoleculeActivityService))]
GetMoleculeActivityDetailDep = Annotated[GetMoleculeActivityDetail, Depends(_get_use_case(GetMoleculeActivityDetail))]
ReadoutCalculationEngineDep = Annotated[ReadoutCalculationEngine, Depends(_get_use_case(ReadoutCalculationEngine))]
from chem_vault.application.screening.fit_dose_response import FitDoseResponseCurves
FitDoseResponseCurvesDep = Annotated[FitDoseResponseCurves, Depends(_get_use_case(FitDoseResponseCurves))]
GetProtocolStatsDep = Annotated[GetProtocolStats, Depends(_get_use_case(GetProtocolStats))]
GetProtocolActivitySummaryDep = Annotated[GetProtocolActivitySummary, Depends(_get_use_case(GetProtocolActivitySummary))]
GetCompoundCurvesDep = Annotated[GetCompoundCurves, Depends(_get_use_case(GetCompoundCurves))]

from chem_vault.application.screening.list_runs_with_counts import ListRunsWithCounts
ListRunsWithCountsDep = Annotated[ListRunsWithCounts, Depends(_get_use_case(ListRunsWithCounts))]
from chem_vault.application.screening.list_readout_data_enriched import ListReadoutDataEnriched
ListReadoutDataEnrichedDep = Annotated[ListReadoutDataEnriched, Depends(_get_use_case(ListReadoutDataEnriched))]
from chem_vault.application.screening.list_dose_response_enriched import ListDoseResponseEnriched
ListDoseResponseEnrichedDep = Annotated[ListDoseResponseEnriched, Depends(_get_use_case(ListDoseResponseEnriched))]
from chem_vault.application.screening.get_plate_map import GetPlateMap
GetPlateMapDep = Annotated[GetPlateMap, Depends(_get_use_case(GetPlateMap))]

# --- Compound Flag dependencies ---
ListCompoundFlagsDep = Annotated[ListCompoundFlags, Depends(_get_use_case(ListCompoundFlags))]
CreateCompoundFlagDep = Annotated[CreateCompoundFlag, Depends(_get_use_case(CreateCompoundFlag))]
DeleteCompoundFlagDep = Annotated[DeleteCompoundFlag, Depends(_get_use_case(DeleteCompoundFlag))]

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
GetProjectScopeStatsDep = Annotated[
    GetProjectScopeStats, Depends(_get_use_case(GetProjectScopeStats))
]
ComposeCollectionsDep = Annotated[ComposeCollections, Depends(_get_use_case(ComposeCollections))]
CreateCollectionDep = Annotated[CreateCollection, Depends(_get_use_case(CreateCollection))]
UpdateCollectionDep = Annotated[UpdateCollection, Depends(_get_use_case(UpdateCollection))]
DeleteCollectionDep = Annotated[DeleteCollection, Depends(_get_use_case(DeleteCollection))]
GetCollectionDep = Annotated[GetCollection, Depends(_get_use_case(GetCollection))]
ListCollectionsDep = Annotated[ListCollections, Depends(_get_use_case(ListCollections))]
AddMoleculesToCollectionDep = Annotated[AddMoleculesToCollection, Depends(_get_use_case(AddMoleculesToCollection))]
RemoveMoleculesFromCollectionDep = Annotated[RemoveMoleculesFromCollection, Depends(_get_use_case(RemoveMoleculesFromCollection))]
ListCollectionMoleculesDep = Annotated[ListCollectionMolecules, Depends(_get_use_case(ListCollectionMolecules))]
ListCollectionsForMoleculeDep = Annotated[ListCollectionsForMolecule, Depends(_get_use_case(ListCollectionsForMolecule))]
CreateSavedSearchDep = Annotated[CreateSavedSearch, Depends(_get_use_case(CreateSavedSearch))]
UpdateSavedSearchDep = Annotated[UpdateSavedSearch, Depends(_get_use_case(UpdateSavedSearch))]
DeleteSavedSearchDep = Annotated[DeleteSavedSearch, Depends(_get_use_case(DeleteSavedSearch))]
GetSavedSearchDep = Annotated[GetSavedSearch, Depends(_get_use_case(GetSavedSearch))]
ListSavedSearchesDep = Annotated[ListSavedSearches, Depends(_get_use_case(ListSavedSearches))]
ExecuteSearchDep = Annotated[ExecuteSearch, Depends(_get_use_case(ExecuteSearch))]
CountSearchDep = Annotated[CountSearch, Depends(_get_use_case(CountSearch))]
AddProjectMemberDep = Annotated[AddProjectMember, Depends(_get_use_case(AddProjectMember))]
RemoveProjectMemberDep = Annotated[RemoveProjectMember, Depends(_get_use_case(RemoveProjectMember))]
UpdateProjectMemberRoleDep = Annotated[UpdateProjectMemberRole, Depends(_get_use_case(UpdateProjectMemberRole))]
ListProjectMembersDep = Annotated[ListProjectMembers, Depends(_get_use_case(ListProjectMembers))]
AddMoleculeToProjectDep = Annotated[AddMoleculeToProject, Depends(_get_use_case(AddMoleculeToProject))]
RemoveMoleculeFromProjectDep = Annotated[RemoveMoleculeFromProject, Depends(_get_use_case(RemoveMoleculeFromProject))]
ListMoleculeProjectsDep = Annotated[ListMoleculeProjects, Depends(_get_use_case(ListMoleculeProjects))]

# --- Attachment dependencies ---
UploadAttachmentDep = Annotated[UploadAttachment, Depends(_get_use_case(UploadAttachment))]
DeleteAttachmentDep = Annotated[DeleteAttachment, Depends(_get_use_case(DeleteAttachment))]
ListAttachmentsDep = Annotated[ListAttachments, Depends(_get_use_case(ListAttachments))]
DownloadAttachmentDep = Annotated[DownloadAttachment, Depends(_get_use_case(DownloadAttachment))]

# --- Plate setup + readout import dependencies ---
ParsePlateMapFileDep = Annotated[ParsePlateMapFile, Depends(_get_use_case(ParsePlateMapFile))]
SetUpRunPlateDep = Annotated[SetUpRunPlate, Depends(_get_use_case(SetUpRunPlate))]
ImportRunReadoutsDep = Annotated[ImportRunReadouts, Depends(_get_use_case(ImportRunReadouts))]

# --- Long-format run-file import dependencies ---
PreviewRunFileDep = Annotated[PreviewRunFile, Depends(_get_use_case(PreviewRunFile))]
RepreviewRunFileDep = Annotated[RepreviewRunFile, Depends(_get_use_case(RepreviewRunFile))]
ImportRunFileDep = Annotated[ImportRunFile, Depends(_get_use_case(ImportRunFile))]
CreateRunImportTemplateDep = Annotated[CreateRunImportTemplate, Depends(_get_use_case(CreateRunImportTemplate))]
UpdateRunImportTemplateDep = Annotated[UpdateRunImportTemplate, Depends(_get_use_case(UpdateRunImportTemplate))]
DeleteRunImportTemplateDep = Annotated[DeleteRunImportTemplate, Depends(_get_use_case(DeleteRunImportTemplate))]
ListRunImportTemplatesDep = Annotated[ListRunImportTemplates, Depends(_get_use_case(ListRunImportTemplates))]

# --- Vault Import dependencies ---
ListCddProtocolsDep = Annotated[ListCddProtocols, Depends(_get_use_case(ListCddProtocols))]
PreviewCddProtocolImportDep = Annotated[PreviewCddProtocolImport, Depends(_get_use_case(PreviewCddProtocolImport))]
ImportCddProtocolDep = Annotated[ImportCddProtocol, Depends(_get_use_case(ImportCddProtocol))]
StartCddMoleculeImportDep = Annotated[StartCddMoleculeImport, Depends(_get_use_case(StartCddMoleculeImport))]
ListCddMoleculeImportsDep = Annotated[ListCddMoleculeImports, Depends(_get_use_case(ListCddMoleculeImports))]
ForceFailCddMoleculeImportDep = Annotated[ForceFailCddMoleculeImport, Depends(_get_use_case(ForceFailCddMoleculeImport))]
from chem_vault.application.cdd_import.get_cdd_molecule_import_status import (
    GetCddMoleculeImportStatusFromDb,
    SyncFailedCddMoleculeImport,
)
GetCddMoleculeImportStatusFromDbDep = Annotated[GetCddMoleculeImportStatusFromDb, Depends(_get_use_case(GetCddMoleculeImportStatusFromDb))]
SyncFailedCddMoleculeImportDep = Annotated[SyncFailedCddMoleculeImport, Depends(_get_use_case(SyncFailedCddMoleculeImport))]
GetCddMoleculeImportRuntimeStatusDep = Annotated[
    GetCddMoleculeImportRuntimeStatus,
    Depends(_get_use_case(GetCddMoleculeImportRuntimeStatus)),
]
CancelCddMoleculeImportDep = Annotated[
    CancelCddMoleculeImport, Depends(_get_use_case(CancelCddMoleculeImport))
]
StartCddPlateImportDep = Annotated[StartCddPlateImport, Depends(_get_use_case(StartCddPlateImport))]
ListCddPlateImportsDep = Annotated[ListCddPlateImports, Depends(_get_use_case(ListCddPlateImports))]
ForceFailCddPlateImportDep = Annotated[ForceFailCddPlateImport, Depends(_get_use_case(ForceFailCddPlateImport))]
from chem_vault.application.cdd_import.get_cdd_plate_import_status import (
    GetCddPlateImportStatusFromDb,
    SyncFailedCddPlateImport,
)
GetCddPlateImportStatusFromDbDep = Annotated[GetCddPlateImportStatusFromDb, Depends(_get_use_case(GetCddPlateImportStatusFromDb))]
SyncFailedCddPlateImportDep = Annotated[SyncFailedCddPlateImport, Depends(_get_use_case(SyncFailedCddPlateImport))]
GetCddPlateImportRuntimeStatusDep = Annotated[
    GetCddPlateImportRuntimeStatus,
    Depends(_get_use_case(GetCddPlateImportRuntimeStatus)),
]
CancelCddPlateImportDep = Annotated[
    CancelCddPlateImport, Depends(_get_use_case(CancelCddPlateImport))
]

# --- Dashboard dependencies ---
GetDashboardStatsDep = Annotated[GetDashboardStats, Depends(_get_use_case(GetDashboardStats))]

# --- Campaign dependencies ---
from chem_vault.application.research_organization.add_campaign_channel import AddCampaignChannel
from chem_vault.application.research_organization.add_result_row import AddResultRow
from chem_vault.application.research_organization.add_results_from_campaign import AddResultsFromCampaign as AddResultsFromCampaignUC
from chem_vault.application.research_organization.add_results_from_collection import AddResultsFromCollection as AddResultsFromCollectionUC
from chem_vault.application.research_organization.add_results_from_runs import AddResultsFromRuns as AddResultsFromRunsUC
from chem_vault.application.research_organization.preview_run_import import PreviewRunImport
from chem_vault.application.research_organization.close_campaign import CloseCampaign
from chem_vault.application.research_organization.create_campaign import CreateCampaign as CreateCampaignUC
from chem_vault.application.research_organization.get_published_campaign import GetPublishedCampaign
from chem_vault.application.research_organization.override_result_cell import OverrideResultCell
from chem_vault.application.research_organization.refresh_campaign_from_sources import RefreshFromSources
from chem_vault.application.research_organization.remove_campaign_channel import RemoveCampaignChannel
from chem_vault.application.research_organization.remove_result_row import RemoveResultRow

from chem_vault.application.research_organization.set_result_decision import SetResultDecision
from chem_vault.application.research_organization.bulk_set_result_decisions import (
    BulkSetResultDecisions,
)
from chem_vault.application.research_organization.supersede_campaign import SupersedeCampaign as SupersedeCampaignUC
from chem_vault.application.research_organization.recompute_channel import RecomputeChannel
from chem_vault.application.research_organization.update_campaign_channel import UpdateCampaignChannel
from chem_vault.application.research_organization.update_campaign_metadata import UpdateCampaignMetadata
from chem_vault.domain.research_organization.repository import CampaignRepository


def get_campaign_repo(container: Annotated[Container, Depends(get_container)]) -> CampaignRepository:
    """Campaign repository — used directly by list/get routes."""
    return container[CampaignRepository]


CampaignRepositoryDep = Annotated[CampaignRepository, Depends(get_campaign_repo)]

CreateCampaignDep = Annotated[CreateCampaignUC, Depends(_get_use_case(CreateCampaignUC))]
AddResultsFromCollectionDep = Annotated[AddResultsFromCollectionUC, Depends(_get_use_case(AddResultsFromCollectionUC))]
AddResultsFromCampaignDep = Annotated[AddResultsFromCampaignUC, Depends(_get_use_case(AddResultsFromCampaignUC))]
AddResultsFromRunsDep = Annotated[AddResultsFromRunsUC, Depends(_get_use_case(AddResultsFromRunsUC))]
PreviewRunImportDep = Annotated[PreviewRunImport, Depends(_get_use_case(PreviewRunImport))]
AddCampaignChannelDep = Annotated[AddCampaignChannel, Depends(_get_use_case(AddCampaignChannel))]
UpdateCampaignChannelDep = Annotated[UpdateCampaignChannel, Depends(_get_use_case(UpdateCampaignChannel))]
RemoveCampaignChannelDep = Annotated[RemoveCampaignChannel, Depends(_get_use_case(RemoveCampaignChannel))]
SetResultDecisionDep = Annotated[SetResultDecision, Depends(_get_use_case(SetResultDecision))]
BulkSetResultDecisionsDep = Annotated[BulkSetResultDecisions, Depends(_get_use_case(BulkSetResultDecisions))]
OverrideResultCellDep = Annotated[OverrideResultCell, Depends(_get_use_case(OverrideResultCell))]
AddResultRowDep = Annotated[AddResultRow, Depends(_get_use_case(AddResultRow))]
RemoveResultRowDep = Annotated[RemoveResultRow, Depends(_get_use_case(RemoveResultRow))]
RefreshFromSourcesDep = Annotated[RefreshFromSources, Depends(_get_use_case(RefreshFromSources))]
CloseCampaignDep = Annotated[CloseCampaign, Depends(_get_use_case(CloseCampaign))]
SupersedeCampaignDep = Annotated[SupersedeCampaignUC, Depends(_get_use_case(SupersedeCampaignUC))]
GetPublishedCampaignDep = Annotated[GetPublishedCampaign, Depends(_get_use_case(GetPublishedCampaign))]
RecomputeChannelDep = Annotated[RecomputeChannel, Depends(_get_use_case(RecomputeChannel))]
UpdateCampaignMetadataDep = Annotated[UpdateCampaignMetadata, Depends(_get_use_case(UpdateCampaignMetadata))]
