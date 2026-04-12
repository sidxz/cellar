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
from chem_vault.application.audit.query_audit import GetAuditOperation, ListAuditOperations
from chem_vault.application.chemical_registration.bulk_registration_service import BulkRegistrationService
from chem_vault.application.chemical_registration.synthesis_routes import (
    AddReactionStep,
    CreateSynthesisRoute,
    DeleteSynthesisRoute,
    DeprecateSynthesisRoute,
    GetSynthesisRoute,
    ListSynthesisRoutesByMolecule,
    RecordStepOutcome,
    RemoveReactionStep,
    SetPreferredRoute,
    UpdateSynthesisRoute,
    ValidateSynthesisRoute,
)
from chem_vault.application.inventory.create_batch import CreateBatch
from chem_vault.application.inventory.create_sample import CreateSample
from chem_vault.application.inventory.salt_matcher import SaltMatcher
from chem_vault.application.inventory.sample_requests import (
    ApproveSampleRequest,
    CancelSampleRequest,
    CreateSampleRequest,
    FulfillSampleRequest,
    GetSampleRequest,
    ListSampleRequests,
    RejectSampleRequest,
    StartPreparingSampleRequest,
    UpdateSampleRequest,
)
from chem_vault.application.inventory.preview_shipment_import import PreviewShipmentImport
from chem_vault.application.inventory.shipments import (
    AddShipmentItem,
    CreateShipment,
    DeleteShipment,
    DeliverShipment,
    GetShipment,
    ListShipments,
    MarkShipmentInTransit,
    ReturnShipment,
    ShipShipment,
    UpdateShipment,
)
from chem_vault.application.inventory.synthesis_requests import (
    ApproveSynthesisRequest as ApproveSynthReq,
    AssignSynthesisRequest as AssignSynthReq,
    CancelSynthesisRequest as CancelSynthReq,
    CompleteSynthesis,
    CreateSynthesisRequest as CreateSynthReq,
    DeleteSynthesisRequest as DeleteSynthReq,
    FailSynthesis,
    FlagInfeasible,
    FulfillSynthesisRequest as FulfillSynthReq,
    GetSynthesisRequest as GetSynthReq,
    ListSynthesisRequests as ListSynthReqs,
    RejectSynthesisRequest as RejectSynthReq,
    StartSynthesis,
    SubmitSynthesisRequest as SubmitSynthReq,
    UpdateSynthesisRequest as UpdateSynthReq,
)
from chem_vault.application.inventory.get_batch import GetBatch, ListBatchesByMolecule
from chem_vault.application.inventory.get_sample import GetSample, ListSamplesByBatch
from chem_vault.application.inventory.manage_sample import AliquotSample, ClearQuarantineSample, DisposeSample, MoveSample, QuarantineSample
from chem_vault.application.inventory.delete_storage_location import DeleteStorageLocation
from chem_vault.application.inventory.manage_storage import (
    CreateStorageLocation,
    GetStorageLocationChildren,
    ListStorageLocations,
)
from chem_vault.application.inventory.update_batch import UpdateBatch
from chem_vault.application.inventory.update_storage_location import UpdateStorageLocation
from chem_vault.application.screening.plate_templates import (
    CreatePlateTemplate,
    DeletePlateTemplate,
    GetPlateTemplate,
    ListPlateTemplates,
    UpdatePlateTemplate,
)
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
from chem_vault.application.inventory.plate_read_model import PlateReadModelService
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.plate_read_model_reader import SQLAlchemyPlateReadModelService
from chem_vault.application.inventory.import_templates import (
    CreateImportTemplate,
    DeleteImportTemplate,
    ListImportTemplates,
)
from chem_vault.application.inventory.import_plate_data import ImportFileCache, ImportPlateDataService
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.import_template_repository import (
    SQLAlchemyImportTemplateRepository,
)
from chem_vault.application.screening.create_dose_response import CreateDoseResponseCurve
from chem_vault.application.screening.create_protocol import CreateProtocol
from chem_vault.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from chem_vault.application.screening.create_readout_data import CreateReadoutData
from chem_vault.application.screening.create_run import CreateRun
from chem_vault.application.screening.create_target import CreateTarget
from chem_vault.application.screening.delete_target import DeleteTarget
from chem_vault.application.screening.get_dose_response import ListDoseResponseByRun
from chem_vault.application.screening.get_protocol import GetProtocol, ListProtocols
from chem_vault.application.screening.get_readout_data import ListReadoutDataByRun
from chem_vault.application.screening.get_run import GetRun, ListRunsByProtocol
from chem_vault.application.screening.get_target import GetTarget, ListTargets
from chem_vault.application.screening.lock_run import LockRun, UnlockRun
from chem_vault.application.screening.update_target import UpdateTarget
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
from chem_vault.application.screening.manage_readout_definitions import AddReadoutDefinition, RemoveReadoutDefinition
from chem_vault.application.screening.manage_run import ApproveRun, CompleteRun, RejectRun, StartRun
from chem_vault.application.screening.update_run import UpdateRun
from chem_vault.application.screening.molecule_activity_service import MoleculeActivityService
from chem_vault.application.chemical_registration.disclosure_service import DisclosureService
from chem_vault.application.chemical_registration.get_disclosure import GetDisclosure
from chem_vault.application.chemical_registration.identifiers import (
    AddIdentifier,
    ListIdentifiers,
    RemoveIdentifier,
)
from chem_vault.application.chemical_registration.create_relationship import CreateRelationship
from chem_vault.application.chemical_registration.delete_relationship import DeleteRelationship
from chem_vault.application.chemical_registration.get_merge_history import GetMergeHistory
from chem_vault.application.chemical_registration.get_molecule import GetMolecule
from chem_vault.application.chemical_registration.get_molecule_by_identifier import GetMoleculeByIdentifier
from chem_vault.application.chemical_registration.list_relationships import ListRelationships
from chem_vault.application.chemical_registration.list_disclosures import ListDisclosures
from chem_vault.application.chemical_registration.list_disclosures_by_workspace import ListDisclosuresByWorkspace
from chem_vault.application.chemical_registration.list_molecules import ListMolecules
from chem_vault.application.chemical_registration.merge_service import MergeService
from chem_vault.application.chemical_registration.merge_side_effect_registry import MergeSideEffectRegistry
from chem_vault.application.chemical_registration.register_molecule import RegisterMolecule
from chem_vault.application.chemical_registration.resolve_disclosure_conflict import ResolveDisclosureConflict
from chem_vault.application.chemical_registration.export_sdf import ExportMoleculesSDF
from chem_vault.application.chemical_registration.search_molecules import SearchMolecules
from chem_vault.application.chemical_registration.update_molecule import UpdateMolecule
from chem_vault.application.user.get_preferences import GetPreferences
from chem_vault.application.user.update_preferences import UpdatePreferences
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.application.workspace_config.create_organization import CreateOrganization
from chem_vault.application.workspace_config.create_custom_field import CreateCustomField
from chem_vault.application.workspace_config.list_custom_fields import ListCustomFields
from chem_vault.application.workspace_config.update_custom_field import UpdateCustomField
from chem_vault.application.workspace_config.delete_custom_field import DeleteCustomField
from chem_vault.application.workspace_config.custom_field_validator import CustomFieldValidator
from chem_vault.application.workspace_config.create_salt_entry import CreateSaltEntry
from chem_vault.application.workspace_config.list_salt_entries import ListSaltEntries
from chem_vault.application.workspace_config.update_salt_entry import UpdateSaltEntry
from chem_vault.application.workspace_config.delete_salt_entry import DeleteSaltEntry
from chem_vault.application.workspace_config.create_registration_form import CreateRegistrationForm
from chem_vault.application.workspace_config.update_registration_form import UpdateRegistrationForm
from chem_vault.application.workspace_config.delete_registration_form import DeleteRegistrationForm
from chem_vault.application.workspace_config.get_registration_form import GetRegistrationForm
from chem_vault.application.workspace_config.list_registration_forms import ListRegistrationForms
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
from chem_vault.domain.chemical_registration.repository import BulkRegistrationRepository, MoleculeRelationshipRepository, MoleculeRepository, SynthesisRouteRepository
from chem_vault.domain.inventory.repository import BatchRepository, SampleRepository, SampleRequestRepository, ShipmentRepository, StorageLocationRepository, SynthesisRequestRepository
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    PlateTemplateRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
    TargetRepository,
)
from chem_vault.domain.shared.user_preferences import UserPreferencesRepository
from chem_vault.domain.workspace_config.repository import (
    ControlledVocabularyRepository,
    CustomFieldDefinitionRepository,
    OrganizationRepository,
    WorkspaceSettingsRepository,
)
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.application.research_organization.archive_project import ArchiveProject
from chem_vault.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    ListCollectionMolecules,
    RemoveMoleculesFromCollection,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.collection_merge_side_effect import CollectionMergeSideEffect
from chem_vault.application.research_organization.compose_collections import ComposeCollections
from chem_vault.application.research_organization.create_collection import CreateCollection
from chem_vault.application.research_organization.execute_search import ExecuteSearch
from chem_vault.application.research_organization.create_project import CreateProject
from chem_vault.application.research_organization.create_saved_search import CreateSavedSearch
from chem_vault.application.research_organization.delete_collection import DeleteCollection
from chem_vault.application.research_organization.delete_saved_search import DeleteSavedSearch
from chem_vault.application.research_organization.get_collection import GetCollection, ListCollections
from chem_vault.application.research_organization.get_collections_for_molecule import ListCollectionsForMolecule
from chem_vault.application.research_organization.get_project import GetProject, ListProjects
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
from chem_vault.application.shared.molecule_resolver import MoleculeResolver
from chem_vault.infrastructure.messaging.merge_handlers import (
    BatchMergeSideEffect,
    DoseResponseCurveMergeSideEffect,
    MoleculeRelationshipMergeSideEffect,
    ReadoutDataMergeSideEffect,
    SynthesisRouteMergeSideEffect,
)
from chem_vault.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from chem_vault.infrastructure.persistence.settings import DatabaseSettings
from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.project_member_repository import (
    SQLAlchemyProjectMemberRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.saved_search_repository import (
    SQLAlchemySavedSearchRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_disclosure_repository import (
    SQLAlchemyBulkDisclosureRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_repository import (
    SQLAlchemyBulkRegistrationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.sample_repository import (
    SQLAlchemySampleRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.sample_request_repository import (
    SQLAlchemySampleRequestRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.shipment_repository import (
    SQLAlchemyShipmentRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.storage_location_repository import (
    SQLAlchemyStorageLocationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_repository import (
    SQLAlchemySynthesisRequestRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.plate_template_repository import (
    SQLAlchemyPlateTemplateRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.target_repository import (
    SQLAlchemyTargetRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_request_repository import (
    SQLAlchemyDisclosureRequestRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.merge_event_repository import (
    SQLAlchemyMergeEventRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_relationship_repository import (
    SQLAlchemyMoleculeRelationshipRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.synthesis_route_repository import (
    SQLAlchemySynthesisRouteRepository,
)
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.infrastructure.rdkit.structure_processor import StructureProcessor
from chem_vault.domain.screening_assay.curve_fitting import CurveFittingService
from chem_vault.infrastructure.lmfit.curve_fitter import LmfitCurveFitter
from chem_vault.application.screening.fit_dose_response import FitDoseResponseCurves
from chem_vault.application.screening.refit_dose_response import RefitDoseResponseCurve
from chem_vault.application.screening.classify_dose_response import ClassifyDoseResponseCurve
from chem_vault.infrastructure.persistence.sqlalchemy.user_preferences_repository import (
    SQLAlchemyUserPreferencesRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (
    SQLAlchemyControlledVocabularyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.custom_field_definition_repository import (
    SQLAlchemyCustomFieldDefinitionRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.registration_form_repository import (
    SQLAlchemyRegistrationFormRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.organization_repository import (
    SQLAlchemyOrganizationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.application.attachment.upload_attachment import UploadAttachment
from chem_vault.application.attachment.delete_attachment import DeleteAttachment
from chem_vault.application.attachment.list_attachments import ListAttachments
from chem_vault.application.attachment.download_attachment import DownloadAttachment
from chem_vault.infrastructure.persistence.sqlalchemy.attachment.attachment_merge_side_effect import AttachmentMergeSideEffect
from chem_vault.infrastructure.persistence.sqlalchemy.attachment.attachment_repository import SQLAlchemyAttachmentRepository
from chem_vault.infrastructure.storage.fsspec_client import FsspecStorageClient, StorageSettings


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
    container.define(
        ListAuditOperations,
        lambda c: ListAuditOperations(c[AuditRepository]),
    )
    container.define(
        GetAuditOperation,
        lambda c: GetAuditOperation(c[AuditRepository]),
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
    def _delete_vocabulary(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteVocabulary(
            uow,
            SQLAlchemyControlledVocabularyRepository(uow),
            SQLAlchemyWorkspaceSettingsRepository(uow),
            c[EventDispatcher],
        )

    container.define(DeleteVocabulary, _delete_vocabulary)

    # --- Custom Field Definitions ---
    # NOTE: CustomFieldValidator is NOT registered as a standalone singleton.
    # It must share the same UoW as the calling use case, so it is created
    # inline in each use case factory (see _mol_cmd, _update_molecule, etc.).

    def _cfd_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow), dispatcher=c[EventDispatcher])
        return _f

    def _cfd_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return _f

    def _delete_custom_field(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteCustomField(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow), dispatcher=c[EventDispatcher])

    container.define(CreateCustomField, _cfd_cmd(CreateCustomField))
    container.define(UpdateCustomField, _cfd_cmd(UpdateCustomField))
    container.define(ListCustomFields, _cfd_query(ListCustomFields))
    container.define(DeleteCustomField, _delete_custom_field)

    # --- Salt Catalog ---
    def _salt_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySaltEntryRepository(uow), c[EventDispatcher])
        return _f

    def _salt_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySaltEntryRepository(uow))
        return _f

    def _delete_salt_entry(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteSaltEntry(uow, SQLAlchemySaltEntryRepository(uow), c[EventDispatcher])

    container.define(CreateSaltEntry, _salt_cmd(CreateSaltEntry))
    container.define(UpdateSaltEntry, _salt_cmd(UpdateSaltEntry))
    container.define(ListSaltEntries, _salt_query(ListSaltEntries))
    container.define(DeleteSaltEntry, _delete_salt_entry)

    # --- Registration Forms ---

    def _regform_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegistrationFormRepository(uow), c[EventDispatcher])
        return _f

    def _regform_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegistrationFormRepository(uow))
        return _f

    def _delete_registration_form(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteRegistrationForm(uow, SQLAlchemyRegistrationFormRepository(uow), c[EventDispatcher])

    container.define(CreateRegistrationForm, _regform_cmd(CreateRegistrationForm))
    container.define(UpdateRegistrationForm, _regform_cmd(UpdateRegistrationForm))
    container.define(GetRegistrationForm, _regform_query(GetRegistrationForm))
    container.define(ListRegistrationForms, _regform_query(ListRegistrationForms))
    container.define(DeleteRegistrationForm, _delete_registration_form)

    # --- Chemical Registration ---
    container.define(StructureProcessor, Singleton(StructureProcessor))
    container.define(StructureProcessorProtocol, lambda c: c[StructureProcessor])

    # --- Curve Fitting ---
    container.define(LmfitCurveFitter, Singleton(LmfitCurveFitter))
    container.define(CurveFittingService, lambda c: c[LmfitCurveFitter])

    def _mol_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
            return uc_cls(uow, SQLAlchemyMoleculeRepository(uow), c[EventDispatcher], c[StructureProcessorProtocol], validator)
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

    def _update_molecule(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return UpdateMolecule(uow, SQLAlchemyMoleculeRepository(uow), c[EventDispatcher], validator)

    container.define(UpdateMolecule, _update_molecule)
    container.define(GetMolecule, _mol_query(GetMolecule))
    container.define(ListMolecules, _mol_query(ListMolecules))
    container.define(GetMoleculeByIdentifier, _mol_query(GetMoleculeByIdentifier))
    container.define(AddIdentifier, _mol_cmd_no_proc(AddIdentifier))
    container.define(RemoveIdentifier, _mol_cmd_no_proc(RemoveIdentifier))
    container.define(ListIdentifiers, _mol_query(ListIdentifiers))

    def _search_molecules(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SearchMolecules(uow, SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])

    container.define(SearchMolecules, _search_molecules)

    def _export_sdf(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ExportMoleculesSDF(uow, SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])

    container.define(ExportMoleculesSDF, _export_sdf)

    # --- Molecule Relationships ---
    def _rel_cmd(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateRelationship(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            relationship_repo=SQLAlchemyMoleculeRelationshipRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _rel_query(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRelationships(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            relationship_repo=SQLAlchemyMoleculeRelationshipRepository(uow),
        )

    def _rel_delete(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteRelationship(
            uow=uow,
            relationship_repo=SQLAlchemyMoleculeRelationshipRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(CreateRelationship, _rel_cmd)
    container.define(ListRelationships, _rel_query)
    container.define(DeleteRelationship, _rel_delete)

    # --- File Storage (singleton) ---
    storage_settings = StorageSettings()
    storage_client = FsspecStorageClient(storage_settings)
    container.define(FsspecStorageClient, Singleton(lambda: storage_client))

    # --- Merge & Disclosure ---
    container.define(
        MergeSideEffectRegistry,
        Singleton(lambda: MergeSideEffectRegistry([
            BatchMergeSideEffect(),
            ReadoutDataMergeSideEffect(),
            DoseResponseCurveMergeSideEffect(),
            MoleculeRelationshipMergeSideEffect(),
            SynthesisRouteMergeSideEffect(),
            CollectionMergeSideEffect(),
            AttachmentMergeSideEffect(storage_client),
        ])),
    )

    def _merge_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MergeService(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )

    container.define(MergeService, _merge_service)

    def _disclosure_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        # MergeService must share the same UoW as DisclosureService because
        # merge_in_transaction() expects the caller to manage the transaction.
        merge_svc = MergeService(
            uow=uow,
            molecule_repo=mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )
        return DisclosureService(
            uow=uow,
            molecule_repo=mol_repo,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            structure_processor=c[StructureProcessorProtocol],
            merge_service=merge_svc,
            dispatcher=c[EventDispatcher],
        )

    container.define(DisclosureService, _disclosure_service)

    def _get_disclosure(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetDisclosure(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
        )

    container.define(GetDisclosure, _get_disclosure)

    def _list_disclosures(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDisclosures(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
        )

    container.define(ListDisclosures, _list_disclosures)

    def _list_disclosures_by_workspace(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDisclosuresByWorkspace(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
        )

    container.define(ListDisclosuresByWorkspace, _list_disclosures_by_workspace)

    def _resolve_conflict(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        # MergeService must share the same UoW — merge_in_transaction
        # expects the caller to manage the transaction.
        merge_svc = MergeService(
            uow=uow,
            molecule_repo=mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )
        return ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            molecule_repo=mol_repo,
            merge_service=merge_svc,
            structure_processor=c[StructureProcessorProtocol],
            dispatcher=c[EventDispatcher],
        )

    container.define(ResolveDisclosureConflict, _resolve_conflict)

    def _merge_history(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetMergeHistory(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
        )

    container.define(GetMergeHistory, _merge_history)

    # --- Bulk Registration ---
    def _bulk_registration_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return BulkRegistrationService(
            uow=uow,
            bulk_reg_repo=SQLAlchemyBulkRegistrationRepository(uow),
            mol_repo=SQLAlchemyMoleculeRepository(uow),
            dispatcher=c[EventDispatcher],
            structure_processor=c[StructureProcessorProtocol],
            salt_matcher=SaltMatcher(SQLAlchemySaltEntryRepository(uow)),
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    container.define(BulkRegistrationService, _bulk_registration_service)

    # --- Synthesis Routes ---
    def _synth_route_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRouteRepository(uow), c[EventDispatcher])
        return _f

    def _synth_route_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRouteRepository(uow))
        return _f

    def _create_synth_route(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateSynthesisRoute(
            uow, SQLAlchemySynthesisRouteRepository(uow),
            SQLAlchemyMoleculeRepository(uow), c[EventDispatcher],
        )

    container.define(CreateSynthesisRoute, _create_synth_route)
    container.define(GetSynthesisRoute, _synth_route_query(GetSynthesisRoute))
    container.define(ListSynthesisRoutesByMolecule, _synth_route_query(ListSynthesisRoutesByMolecule))
    container.define(AddReactionStep, _synth_route_cmd(AddReactionStep))
    container.define(RecordStepOutcome, _synth_route_cmd(RecordStepOutcome))
    container.define(ValidateSynthesisRoute, _synth_route_cmd(ValidateSynthesisRoute))
    container.define(SetPreferredRoute, _synth_route_cmd(SetPreferredRoute))
    container.define(DeprecateSynthesisRoute, _synth_route_cmd(DeprecateSynthesisRoute))
    container.define(UpdateSynthesisRoute, _synth_route_cmd(UpdateSynthesisRoute))
    container.define(DeleteSynthesisRoute, _synth_route_cmd(DeleteSynthesisRoute))
    container.define(RemoveReactionStep, _synth_route_cmd(RemoveReactionStep))

    # --- Inventory ---
    def _batch_cmd(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return CreateBatch(uow, SQLAlchemyBatchRepository(uow), SQLAlchemyMoleculeRepository(uow), c[EventDispatcher], validator)

    def _batch_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyBatchRepository(uow))
        return _f

    def _update_batch(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return UpdateBatch(uow, SQLAlchemyBatchRepository(uow), c[EventDispatcher], validator)

    container.define(CreateBatch, _batch_cmd)
    container.define(UpdateBatch, _update_batch)
    container.define(GetBatch, _batch_query(GetBatch))
    container.define(ListBatchesByMolecule, _batch_query(ListBatchesByMolecule))

    def _sample_create(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateSample(
            uow,
            SQLAlchemyBatchRepository(uow),
            SQLAlchemySampleRepository(uow),
            SQLAlchemyMoleculeRepository(uow),
            c[EventDispatcher],
        )

    def _sample_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRepository(uow), c[EventDispatcher])
        return _f

    def _sample_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRepository(uow))
        return _f

    container.define(CreateSample, _sample_create)
    container.define(GetSample, _sample_query(GetSample))
    container.define(ListSamplesByBatch, _sample_query(ListSamplesByBatch))
    container.define(AliquotSample, _sample_cmd(AliquotSample))
    def _move_sample(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MoveSample(
            uow,
            SQLAlchemySampleRepository(uow),
            SQLAlchemyStorageLocationRepository(uow),
            c[EventDispatcher],
        )

    container.define(MoveSample, _move_sample)
    container.define(QuarantineSample, _sample_cmd(QuarantineSample))
    container.define(ClearQuarantineSample, _sample_cmd(ClearQuarantineSample))
    container.define(DisposeSample, _sample_cmd(DisposeSample))

    def _storage_cmd(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateStorageLocation(uow, SQLAlchemyStorageLocationRepository(uow), c[EventDispatcher])

    def _storage_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyStorageLocationRepository(uow))
        return _f

    def _storage_update(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdateStorageLocation(uow, SQLAlchemyStorageLocationRepository(uow), c[EventDispatcher])

    def _storage_delete(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteStorageLocation(
            uow, SQLAlchemyStorageLocationRepository(uow), SQLAlchemySampleRepository(uow), c[EventDispatcher]
        )

    container.define(CreateStorageLocation, _storage_cmd)
    container.define(UpdateStorageLocation, _storage_update)
    container.define(DeleteStorageLocation, _storage_delete)
    container.define(ListStorageLocations, _storage_query(ListStorageLocations))
    container.define(GetStorageLocationChildren, _storage_query(GetStorageLocationChildren))

    # --- Sample Requests ---
    def _sample_request_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRequestRepository(uow), c[EventDispatcher])
        return _f

    def _sample_request_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRequestRepository(uow))
        return _f

    def _create_sample_request(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateSampleRequest(
            uow, SQLAlchemySampleRequestRepository(uow), c[EventDispatcher],
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    def _fulfill_sample_request(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FulfillSampleRequest(
            uow, SQLAlchemySampleRequestRepository(uow), c[EventDispatcher],
            sample_repo=SQLAlchemySampleRepository(uow),
        )

    container.define(CreateSampleRequest, _create_sample_request)
    container.define(GetSampleRequest, _sample_request_query(GetSampleRequest))
    container.define(ListSampleRequests, _sample_request_query(ListSampleRequests))
    container.define(ApproveSampleRequest, _sample_request_cmd(ApproveSampleRequest))
    container.define(RejectSampleRequest, _sample_request_cmd(RejectSampleRequest))
    container.define(FulfillSampleRequest, _fulfill_sample_request)
    container.define(CancelSampleRequest, _sample_request_cmd(CancelSampleRequest))
    container.define(StartPreparingSampleRequest, _sample_request_cmd(StartPreparingSampleRequest))
    container.define(UpdateSampleRequest, _sample_request_cmd(UpdateSampleRequest))

    # --- Shipments ---
    def _shipment_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyShipmentRepository(uow), c[EventDispatcher])
        return _f

    def _shipment_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyShipmentRepository(uow))
        return _f

    def _create_shipment(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateShipment(
            uow, SQLAlchemyShipmentRepository(uow), c[EventDispatcher],
            sample_repo=SQLAlchemySampleRepository(uow),
        )

    container.define(CreateShipment, _create_shipment)
    container.define(GetShipment, _shipment_query(GetShipment))
    container.define(ListShipments, _shipment_query(ListShipments))
    container.define(ShipShipment, _shipment_cmd(ShipShipment))
    container.define(MarkShipmentInTransit, _shipment_cmd(MarkShipmentInTransit))
    container.define(DeliverShipment, _shipment_cmd(DeliverShipment))
    container.define(ReturnShipment, _shipment_cmd(ReturnShipment))
    def _add_shipment_item(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddShipmentItem(
            uow, SQLAlchemyShipmentRepository(uow), c[EventDispatcher],
            sample_repo=SQLAlchemySampleRepository(uow),
        )

    container.define(AddShipmentItem, _add_shipment_item)
    container.define(UpdateShipment, _shipment_cmd(UpdateShipment))
    container.define(DeleteShipment, _shipment_cmd(DeleteShipment))

    def _preview_import(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return PreviewShipmentImport(
            uow,
            SQLAlchemyMoleculeRepository(uow),
            SQLAlchemyBatchRepository(uow),
            SQLAlchemySampleRepository(uow),
        )

    container.define(PreviewShipmentImport, _preview_import)

    # --- Synthesis Requests ---
    def _synth_req_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRequestRepository(uow), c[EventDispatcher])
        return _f

    def _synth_req_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRequestRepository(uow))
        return _f

    container.define(CreateSynthReq, _synth_req_cmd(CreateSynthReq))
    container.define(SubmitSynthReq, _synth_req_cmd(SubmitSynthReq))
    container.define(ApproveSynthReq, _synth_req_cmd(ApproveSynthReq))
    container.define(RejectSynthReq, _synth_req_cmd(RejectSynthReq))
    container.define(AssignSynthReq, _synth_req_cmd(AssignSynthReq))
    container.define(StartSynthesis, _synth_req_cmd(StartSynthesis))
    container.define(FlagInfeasible, _synth_req_cmd(FlagInfeasible))
    container.define(CompleteSynthesis, _synth_req_cmd(CompleteSynthesis))
    def _fulfill_synth_req(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FulfillSynthReq(
            uow, SQLAlchemySynthesisRequestRepository(uow), c[EventDispatcher],
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    container.define(FulfillSynthReq, _fulfill_synth_req)
    container.define(FailSynthesis, _synth_req_cmd(FailSynthesis))
    container.define(CancelSynthReq, _synth_req_cmd(CancelSynthReq))
    container.define(GetSynthReq, _synth_req_query(GetSynthReq))
    container.define(ListSynthReqs, _synth_req_query(ListSynthReqs))
    container.define(UpdateSynthReq, _synth_req_cmd(UpdateSynthReq))
    container.define(DeleteSynthReq, _synth_req_cmd(DeleteSynthReq))

    # --- Screening ---
    def _protocol_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])
        return _f

    def _protocol_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolRepository(uow))
        return _f

    container.define(CreateProtocol, _protocol_cmd(CreateProtocol))
    container.define(GetProtocol, _protocol_query(GetProtocol))
    container.define(ListProtocols, _protocol_query(ListProtocols))
    container.define(PublishProtocol, _protocol_cmd(PublishProtocol))
    container.define(RetireProtocol, _protocol_cmd(RetireProtocol))
    container.define(VersionProtocol, _protocol_cmd(VersionProtocol))
    container.define(UpdateProtocol, _protocol_cmd(UpdateProtocol))
    container.define(DeleteProtocol, _protocol_cmd(DeleteProtocol))
    container.define(ListProtocolsByProject, _protocol_query(ListProtocolsByProject))
    container.define(AddProtocolToProject, _protocol_cmd(AddProtocolToProject))
    container.define(RemoveProtocolFromProject, _protocol_cmd(RemoveProtocolFromProject))

    def _add_readout_def(c):  # type: ignore[no-untyped-def]
        from chem_vault.domain.screening_assay.formula_evaluator import FormulaEvaluator as FE
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddReadoutDefinition(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher], c[FE])

    container.define(AddReadoutDefinition, _add_readout_def)
    container.define(RemoveReadoutDefinition, _protocol_cmd(RemoveReadoutDefinition))

    from chem_vault.application.screening.manage_condition_definitions import (
        AddConditionDefinition,
        RemoveConditionDefinition,
    )
    from chem_vault.application.screening.manage_control_layouts import (
        RemoveControlLayout,
        SetControlLayout,
    )
    container.define(AddConditionDefinition, _protocol_cmd(AddConditionDefinition))
    container.define(RemoveConditionDefinition, _protocol_cmd(RemoveConditionDefinition))
    def _set_control_layout(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetControlLayout(
            uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(SetControlLayout, _set_control_layout)
    container.define(RemoveControlLayout, _protocol_cmd(RemoveControlLayout))

    def _target_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTargetRepository(uow), c[EventDispatcher])
        return _f

    def _target_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTargetRepository(uow))
        return _f

    container.define(CreateTarget, _target_cmd(CreateTarget))
    container.define(UpdateTarget, _target_cmd(UpdateTarget))
    container.define(DeleteTarget, _target_cmd(DeleteTarget))
    container.define(GetTarget, _target_query(GetTarget))
    container.define(ListTargets, _target_query(ListTargets))

    def _run_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunRepository(uow), c[EventDispatcher])
        return _f

    def _run_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunRepository(uow))
        return _f

    def _create_run(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateRun(
            uow,
            SQLAlchemyRunRepository(uow),
            SQLAlchemyProtocolRepository(uow),
            c[EventDispatcher],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(CreateRun, _create_run)
    container.define(GetRun, _run_query(GetRun))
    container.define(ListRunsByProtocol, _run_query(ListRunsByProtocol))
    container.define(StartRun, _run_cmd(StartRun))
    container.define(CompleteRun, _run_cmd(CompleteRun))
    container.define(ApproveRun, _run_cmd(ApproveRun))
    container.define(RejectRun, _run_cmd(RejectRun))
    container.define(UpdateRun, _run_cmd(UpdateRun))
    container.define(LockRun, _run_cmd(LockRun))
    container.define(UnlockRun, _run_cmd(UnlockRun))

    def _readout_create(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return CreateReadoutData(uow, SQLAlchemyReadoutDataRepository(uow), guard, c[EventDispatcher], run_repo=run_repo)

    def _readout_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyReadoutDataRepository(uow))
        return _f

    def _readout_bulk_create(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return BulkCreateReadoutData(
            uow,
            SQLAlchemyReadoutDataRepository(uow),
            guard,
            c[EventDispatcher],
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            run_repo=run_repo,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(CreateReadoutData, _readout_create)
    container.define(BulkCreateReadoutData, _readout_bulk_create)
    container.define(ListReadoutDataByRun, _readout_query(ListReadoutDataByRun))

    def _dose_response_create(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return CreateDoseResponseCurve(uow, SQLAlchemyDoseResponseCurveRepository(uow), guard, c[EventDispatcher], run_repo=run_repo)

    def _dose_response_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyDoseResponseCurveRepository(uow))
        return _f

    container.define(CreateDoseResponseCurve, _dose_response_create)
    container.define(ListDoseResponseByRun, _dose_response_query(ListDoseResponseByRun))

    def _fit_dose_response_curves(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FitDoseResponseCurves(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            curve_fitter=c[CurveFittingService],
        )

    container.define(FitDoseResponseCurves, _fit_dose_response_curves)

    def _refit_dose_response_curve(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RefitDoseResponseCurve(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            curve_fitter=c[CurveFittingService],
        )

    container.define(RefitDoseResponseCurve, _refit_dose_response_curve)

    def _classify_dose_response_curve(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ClassifyDoseResponseCurve(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        )

    container.define(ClassifyDoseResponseCurve, _classify_dose_response_curve)

    # --- Plate Templates ---
    def _pt_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyPlateTemplateRepository(uow), c[EventDispatcher])
        return _f

    def _pt_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyPlateTemplateRepository(uow))
        return _f

    container.define(CreatePlateTemplate, _pt_cmd(CreatePlateTemplate))
    container.define(UpdatePlateTemplate, _pt_cmd(UpdatePlateTemplate))
    container.define(DeletePlateTemplate, _pt_cmd(DeletePlateTemplate))
    container.define(GetPlateTemplate, _pt_query(GetPlateTemplate))
    container.define(ListPlateTemplates, _pt_query(ListPlateTemplates))

    # --- Computation Services ---
    from chem_vault.domain.screening_assay.formula_evaluator import FormulaEvaluator
    from chem_vault.domain.screening_assay.plate_normalizer import PlateNormalizer
    from chem_vault.domain.screening_assay.replicate_aggregator import ReplicateAggregator
    from chem_vault.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator
    from chem_vault.application.screening.readout_calculation_engine import ReadoutCalculationEngine
    from chem_vault.application.screening.cross_protocol_resolver import CrossProtocolResolver
    from chem_vault.application.screening.condition_grouping_service import ConditionGroupingService
    from chem_vault.domain.screening_assay.plate_quality import PlateQualityCalculator
    from chem_vault.application.screening.plate_setup import ParsePlateMapFile, SetUpRunPlate
    from chem_vault.application.screening.import_run_readouts import ImportRunReadouts

    container.define(AstevalFormulaEvaluator, Singleton(AstevalFormulaEvaluator))
    container.define(FormulaEvaluator, lambda c: c[AstevalFormulaEvaluator])
    container.define(PlateNormalizer, Singleton(PlateNormalizer))
    container.define(ReplicateAggregator, Singleton(ReplicateAggregator))
    container.define(PlateQualityCalculator, Singleton(PlateQualityCalculator))
    container.define(ParsePlateMapFile, Singleton(ParsePlateMapFile))

    def _readout_calc_engine(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ReadoutCalculationEngine(
            uow=uow,
            formula_evaluator=c[FormulaEvaluator],
            plate_normalizer=c[PlateNormalizer],
            replicate_aggregator=c[ReplicateAggregator],
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            fit_dose_response=c[FitDoseResponseCurves],
            plate_quality=c[PlateQualityCalculator],
        )

    container.define(ReadoutCalculationEngine, _readout_calc_engine)

    def _set_up_run_plate(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        from chem_vault.application.shared.molecule_resolver import MoleculeResolver
        resolver = MoleculeResolver(SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])
        return SetUpRunPlate(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            molecule_resolver=resolver,
            dispatcher=c[EventDispatcher],
        )

    container.define(SetUpRunPlate, _set_up_run_plate)

    def _import_run_readouts(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportRunReadouts(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    container.define(ImportRunReadouts, _import_run_readouts)

    def _cross_protocol_resolver(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CrossProtocolResolver(
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
        )

    container.define(CrossProtocolResolver, _cross_protocol_resolver)

    def _condition_grouping_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ConditionGroupingService(
            uow=uow,
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(ConditionGroupingService, _condition_grouping_service)

    # --- Registered Plates ---
    def _reg_plate_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegisteredPlateRepository(uow), c[EventDispatcher])
        return _f

    def _reg_plate_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegisteredPlateRepository(uow))
        return _f

    def _map_wells(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MapWells(
            uow,
            SQLAlchemyRegisteredPlateRepository(uow),
            SQLAlchemyBatchRepository(uow),
            c[EventDispatcher],
        )

    container.define(RegisterPlate, _reg_plate_cmd(RegisterPlate))
    container.define(UpdatePlate, _reg_plate_cmd(UpdatePlate))
    container.define(MapWells, _map_wells)
    container.define(ChangeStatus, _reg_plate_cmd(ChangeStatus))
    container.define(DerivePlate, _reg_plate_cmd(DerivePlate))
    container.define(GetPlate, _reg_plate_query(GetPlate))
    container.define(ListPlates, _reg_plate_query(ListPlates))
    container.define(ListChildren, _reg_plate_query(ListChildren))

    def _delete_reg_plate(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeletePlate(uow, SQLAlchemyRegisteredPlateRepository(uow), c[EventDispatcher])

    container.define(DeletePlate, _delete_reg_plate)

    # --- Plate Read Model ---
    container.define(
        PlateReadModelService,
        lambda c: SQLAlchemyPlateReadModelService(c[async_sessionmaker]()),
    )

    # --- Research Organization ---
    def _project_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProjectRepository(uow), c[EventDispatcher])
        return _f

    def _project_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProjectRepository(uow))
        return _f

    def _create_project(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateProject(
            uow,
            SQLAlchemyProjectRepository(uow),
            c[EventDispatcher],
            member_repo=SQLAlchemyProjectMemberRepository(uow),
        )

    container.define(CreateProject, _create_project)
    container.define(UpdateProject, _project_cmd(UpdateProject))
    container.define(ArchiveProject, _project_cmd(ArchiveProject))
    container.define(GetProject, _project_query(GetProject))
    container.define(ListProjects, _project_query(ListProjects))

    # -- Project member management --
    def _member_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyProjectRepository(uow),
                SQLAlchemyProjectMemberRepository(uow),
                c[EventDispatcher],
            )
        return _f

    def _member_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyProjectRepository(uow),
                SQLAlchemyProjectMemberRepository(uow),
            )
        return _f

    container.define(AddProjectMember, _member_cmd(AddProjectMember))
    container.define(RemoveProjectMember, _member_cmd(RemoveProjectMember))
    container.define(UpdateProjectMemberRole, _member_cmd(UpdateProjectMemberRole))
    container.define(ListProjectMembers, _member_query(ListProjectMembers))

    # -- Molecule-project association --
    def _mol_project_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyProjectRepository(uow),
                SQLAlchemyMoleculeRepository(uow),
                SQLAlchemyProjectMemberRepository(uow),
                c[EventDispatcher],
            )
        return _f

    container.define(AddMoleculeToProject, _mol_project_cmd(AddMoleculeToProject))
    container.define(RemoveMoleculeFromProject, _mol_project_cmd(RemoveMoleculeFromProject))

    def _list_mol_projects(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListMoleculeProjects(uow, SQLAlchemyMoleculeRepository(uow))

    container.define(ListMoleculeProjects, _list_mol_projects)

    def _collection_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyCollectionRepository(uow), c[EventDispatcher])
        return _f

    def _collection_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyCollectionRepository(uow))
        return _f

    def _delete_collection(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteCollection(uow, SQLAlchemyCollectionRepository(uow), c[EventDispatcher])

    container.define(CreateCollection, _collection_cmd(CreateCollection))
    container.define(ComposeCollections, _collection_cmd(ComposeCollections))
    container.define(UpdateCollection, _collection_cmd(UpdateCollection))
    container.define(DeleteCollection, _delete_collection)
    container.define(GetCollection, _collection_query(GetCollection))
    container.define(ListCollections, _collection_query(ListCollections))
    container.define(ListCollectionMolecules, _collection_query(ListCollectionMolecules))
    container.define(ListCollectionsForMolecule, _collection_query(ListCollectionsForMolecule))

    def _add_molecules(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        resolver = MoleculeResolver(SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])
        return AddMoleculesToCollection(
            uow, SQLAlchemyCollectionRepository(uow), resolver, c[EventDispatcher],
        )

    def _remove_molecules(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveMoleculesFromCollection(
            uow, SQLAlchemyCollectionRepository(uow), c[EventDispatcher],
        )

    container.define(AddMoleculesToCollection, _add_molecules)
    container.define(RemoveMoleculesFromCollection, _remove_molecules)

    def _ss_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySavedSearchRepository(uow), c[EventDispatcher])
        return _f

    def _ss_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySavedSearchRepository(uow))
        return _f

    def _delete_saved_search(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteSavedSearch(uow, SQLAlchemySavedSearchRepository(uow), c[EventDispatcher])

    container.define(CreateSavedSearch, _ss_cmd(CreateSavedSearch))
    container.define(UpdateSavedSearch, _ss_cmd(UpdateSavedSearch))
    container.define(DeleteSavedSearch, _delete_saved_search)
    container.define(GetSavedSearch, _ss_query(GetSavedSearch))
    container.define(ListSavedSearches, _ss_query(ListSavedSearches))

    # --- Molecule Activity Service ---
    def _molecule_activity_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MoleculeActivityService(
            uow=uow,
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(MoleculeActivityService, _molecule_activity_service)

    # --- Execute Search ---
    def _execute_search(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ExecuteSearch(
            uow,
            SQLAlchemyMoleculeRepository(uow),
            SQLAlchemySavedSearchRepository(uow),
            activity_service=MoleculeActivityService(
                uow=uow,
                readout_repo=SQLAlchemyReadoutDataRepository(uow),
                curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
                protocol_repo=SQLAlchemyProtocolRepository(uow),
            ),
        )

    container.define(ExecuteSearch, _execute_search)

    # --- Import Templates ---
    def _import_tmpl_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyImportTemplateRepository(uow), c[EventDispatcher])
        return _f

    def _import_tmpl_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyImportTemplateRepository(uow))
        return _f

    container.define(CreateImportTemplate, _import_tmpl_cmd(CreateImportTemplate))
    container.define(ListImportTemplates, _import_tmpl_query(ListImportTemplates))
    container.define(DeleteImportTemplate, _import_tmpl_cmd(DeleteImportTemplate))

    # --- Import Plate Data Service ---
    container.define(ImportFileCache, Singleton(ImportFileCache))

    def _import_plate_data_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportPlateDataService(
            uow=uow,
            plate_repo=SQLAlchemyRegisteredPlateRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            cache=c[ImportFileCache],
            create_run=c[CreateRun],
            bulk_create_readout_data=c[BulkCreateReadoutData],
        )

    container.define(ImportPlateDataService, _import_plate_data_service)

    # --- File Attachments ---
    def _attach_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyAttachmentRepository(uow), c[FsspecStorageClient], c[EventDispatcher])
        return _f

    def _attach_query_with_storage(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyAttachmentRepository(uow), c[FsspecStorageClient])
        return _f

    def _attach_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyAttachmentRepository(uow))
        return _f

    container.define(UploadAttachment, _attach_cmd(UploadAttachment))
    container.define(DeleteAttachment, _attach_cmd(DeleteAttachment))
    container.define(ListAttachments, _attach_query(ListAttachments))
    container.define(DownloadAttachment, _attach_query_with_storage(DownloadAttachment))

    # --- Dashboard ---
    from chem_vault.application.dashboard.get_dashboard_stats import GetDashboardStats
    from chem_vault.infrastructure.persistence.sqlalchemy.dashboard_reader import SQLAlchemyDashboardReader

    container.define(
        GetDashboardStats,
        lambda c: GetDashboardStats(SQLAlchemyDashboardReader(c[async_sessionmaker])),
    )

    # --- External API Keys ---
    from chem_vault.application.workspace_config.create_external_api_key import CreateExternalApiKey
    from chem_vault.application.workspace_config.list_external_api_keys import ListExternalApiKeys
    from chem_vault.application.workspace_config.update_external_api_key import UpdateExternalApiKey
    from chem_vault.application.workspace_config.delete_external_api_key import DeleteExternalApiKey
    from chem_vault.application.workspace_config.get_external_api_key_secret import GetExternalApiKeySecret
    from chem_vault.domain.shared.secret_provider import SecretProvider
    from chem_vault.infrastructure.secrets.env_provider import EnvSecretProvider
    from chem_vault.infrastructure.secrets.chain_provider import ChainSecretProvider
    from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.external_api_key_repository import (
        SQLAlchemyExternalApiKeyRepository,
    )

    def _build_secret_provider() -> SecretProvider:
        """Build secret provider chain: Infisical (if configured) → env vars."""
        import os
        providers: list = []

        infisical_token = os.environ.get("INFISICAL_TOKEN")
        infisical_project = os.environ.get("INFISICAL_PROJECT_ID")
        infisical_url = os.environ.get("INFISICAL_BASE_URL", "http://localhost:8089")

        if infisical_token and infisical_project:
            from chem_vault.infrastructure.secrets.infisical_provider import InfisicalSecretProvider
            providers.append(InfisicalSecretProvider(
                base_url=infisical_url,
                token=infisical_token,
                project_id=infisical_project,
            ))

        providers.append(EnvSecretProvider())
        return ChainSecretProvider(*providers)

    container.define(SecretProvider, Singleton(_build_secret_provider))

    def _apikey_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyExternalApiKeyRepository(uow), c[EventDispatcher], c[SecretProvider])
        return _f

    def _apikey_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyExternalApiKeyRepository(uow))
        return _f

    container.define(CreateExternalApiKey, _apikey_cmd(CreateExternalApiKey))
    container.define(UpdateExternalApiKey, _apikey_cmd(UpdateExternalApiKey))
    container.define(DeleteExternalApiKey, _apikey_cmd(DeleteExternalApiKey))
    container.define(ListExternalApiKeys, _apikey_query(ListExternalApiKeys))
    container.define(GetExternalApiKeySecret, lambda c: GetExternalApiKeySecret(c[SecretProvider]))

    # --- Ontology Slot Definitions ---
    from chem_vault.application.workspace_config.create_ontology_slot import CreateOntologySlot
    from chem_vault.application.workspace_config.list_ontology_slots import ListOntologySlots
    from chem_vault.application.workspace_config.update_ontology_slot import UpdateOntologySlot
    from chem_vault.application.workspace_config.delete_ontology_slot import DeleteOntologySlot
    from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.ontology_slot_definition_repository import (
        SQLAlchemyOntologySlotDefinitionRepository,
    )

    def _slot_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOntologySlotDefinitionRepository(uow), c[EventDispatcher])
        return _f

    def _slot_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOntologySlotDefinitionRepository(uow))
        return _f

    container.define(CreateOntologySlot, _slot_cmd(CreateOntologySlot))
    container.define(UpdateOntologySlot, _slot_cmd(UpdateOntologySlot))
    container.define(DeleteOntologySlot, _slot_cmd(DeleteOntologySlot))
    container.define(ListOntologySlots, _slot_query(ListOntologySlots))

    # --- Ontology Search ---
    from chem_vault.application.screening.search_ontology import SearchOntology
    from chem_vault.infrastructure.external.bioportal.client import BioPortalClient

    container.define(BioPortalClient, lambda c: BioPortalClient(c[SecretProvider]))
    container.define(SearchOntology, lambda c: SearchOntology(c[BioPortalClient]))

    # --- Ontology Annotations on Protocols ---
    from chem_vault.application.screening.manage_ontology_annotations import (
        SetOntologyAnnotation,
        RemoveOntologyAnnotation,
    )

    def _set_ontology_annotation(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetOntologyAnnotation(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

    def _remove_ontology_annotation(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveOntologyAnnotation(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

    container.define(SetOntologyAnnotation, _set_ontology_annotation)
    container.define(RemoveOntologyAnnotation, _remove_ontology_annotation)

    # --- Protocol Forms ---
    from chem_vault.application.workspace_config.create_protocol_form import CreateProtocolForm
    from chem_vault.application.workspace_config.list_protocol_forms import ListProtocolForms
    from chem_vault.application.workspace_config.update_protocol_form import UpdateProtocolForm
    from chem_vault.application.workspace_config.delete_protocol_form import DeleteProtocolForm
    from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.protocol_form_repository import (
        SQLAlchemyProtocolFormRepository,
    )

    def _pf_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolFormRepository(uow), c[EventDispatcher])
        return _f

    def _pf_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolFormRepository(uow))
        return _f

    container.define(CreateProtocolForm, _pf_cmd(CreateProtocolForm))
    container.define(UpdateProtocolForm, _pf_cmd(UpdateProtocolForm))
    container.define(DeleteProtocolForm, _pf_cmd(DeleteProtocolForm))
    container.define(ListProtocolForms, _pf_query(ListProtocolForms))

    # --- CDD Import ---
    import httpx

    from chem_vault.application.cdd_import.import_cdd_protocol import ImportCddProtocol
    from chem_vault.application.cdd_import.list_cdd_protocols import ListCddProtocols
    from chem_vault.application.cdd_import.preview_cdd_protocol_import import PreviewCddProtocolImport
    from chem_vault.infrastructure.cdd.client import CddVaultClient

    _httpx_client = httpx.AsyncClient()
    container.define(httpx.AsyncClient, Singleton(lambda: _httpx_client))
    container.define(CddVaultClient, Singleton(lambda: CddVaultClient(_httpx_client)))

    def _cdd_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                gateway=c[CddVaultClient],
                secret_provider=c[SecretProvider],
                settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
                api_key_repo=SQLAlchemyExternalApiKeyRepository(uow),
                uow=uow,
            )
        return _f

    def _cdd_import_cmd(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportCddProtocol(
            gateway=c[CddVaultClient],
            secret_provider=c[SecretProvider],
            settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
            api_key_repo=SQLAlchemyExternalApiKeyRepository(uow),
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(ListCddProtocols, _cdd_query(ListCddProtocols))
    container.define(PreviewCddProtocolImport, _cdd_query(PreviewCddProtocolImport))
    container.define(ImportCddProtocol, _cdd_import_cmd)

    return container
