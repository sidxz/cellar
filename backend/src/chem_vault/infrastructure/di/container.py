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
from chem_vault.application.inventory.create_batch import CreateBatch
from chem_vault.application.inventory.create_sample import CreateSample
from chem_vault.application.inventory.get_batch import GetBatch, ListBatchesByMolecule
from chem_vault.application.inventory.get_sample import GetSample, ListSamplesByBatch
from chem_vault.application.inventory.manage_sample import AliquotSample, ClearQuarantineSample, DisposeSample, MoveSample, QuarantineSample
from chem_vault.application.inventory.delete_storage_location import DeleteStorageLocation
from chem_vault.application.inventory.manage_storage import (
    CreateStorageLocation,
    GetStorageLocationChildren,
    ListStorageLocations,
)
from chem_vault.application.inventory.update_storage_location import UpdateStorageLocation
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
from chem_vault.application.screening.manage_protocol import DeleteProtocol, PublishProtocol, RetireProtocol, UpdateProtocol, VersionProtocol
from chem_vault.application.screening.manage_readout_definitions import AddReadoutDefinition, RemoveReadoutDefinition
from chem_vault.application.screening.manage_run import ApproveRun, CompleteRun, RejectRun, StartRun
from chem_vault.application.screening.update_run import UpdateRun
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
from chem_vault.application.chemical_registration.search_molecules import SearchMolecules
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
from chem_vault.domain.chemical_registration.repository import BulkRegistrationRepository, MoleculeRelationshipRepository, MoleculeRepository
from chem_vault.domain.inventory.repository import BatchRepository, SampleRepository, StorageLocationRepository
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
    TargetRepository,
)
from chem_vault.domain.shared.user_preferences import UserPreferencesRepository
from chem_vault.domain.workspace_config.repository import (
    ControlledVocabularyRepository,
    OrganizationRepository,
    WorkspaceSettingsRepository,
)
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.messaging.merge_handlers import (
    BatchMergeSideEffect,
    DoseResponseCurveMergeSideEffect,
    MoleculeRelationshipMergeSideEffect,
    ReadoutDataMergeSideEffect,
)
from chem_vault.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from chem_vault.infrastructure.persistence.settings import DatabaseSettings
from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
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
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.storage_location_repository import (
    SQLAlchemyStorageLocationRepository,
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
        )

    container.define(DeleteVocabulary, _delete_vocabulary)

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
    container.define(GetMoleculeByIdentifier, _mol_query(GetMoleculeByIdentifier))
    container.define(AddIdentifier, _mol_cmd_no_proc(AddIdentifier))
    container.define(RemoveIdentifier, _mol_cmd_no_proc(RemoveIdentifier))
    container.define(ListIdentifiers, _mol_query(ListIdentifiers))

    def _search_molecules(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SearchMolecules(uow, SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])

    container.define(SearchMolecules, _search_molecules)

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

    # --- Merge & Disclosure ---
    container.define(
        MergeSideEffectRegistry,
        Singleton(lambda: MergeSideEffectRegistry([
            BatchMergeSideEffect(),
            ReadoutDataMergeSideEffect(),
            DoseResponseCurveMergeSideEffect(),
            MoleculeRelationshipMergeSideEffect(),
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
        return DisclosureService(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            structure_processor=c[StructureProcessorProtocol],
            merge_service=c[MergeService],
            dispatcher=c[EventDispatcher],
        )

    container.define(DisclosureService, _disclosure_service)

    def _disclosure_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow=uow,
                disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
                molecule_repo=SQLAlchemyMoleculeRepository(uow),
            )
        return _f

    container.define(GetDisclosure, _disclosure_query(GetDisclosure))
    container.define(ListDisclosures, _disclosure_query(ListDisclosures))

    def _list_disclosures_by_workspace(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDisclosuresByWorkspace(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
        )

    container.define(ListDisclosuresByWorkspace, _list_disclosures_by_workspace)

    def _resolve_conflict(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            merge_service=c[MergeService],
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
        )

    container.define(BulkRegistrationService, _bulk_registration_service)

    # --- Inventory ---
    def _batch_cmd(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateBatch(uow, SQLAlchemyBatchRepository(uow), SQLAlchemyMoleculeRepository(uow), c[EventDispatcher])

    def _batch_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyBatchRepository(uow))
        return _f

    container.define(CreateBatch, _batch_cmd)
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
    container.define(AddReadoutDefinition, _protocol_cmd(AddReadoutDefinition))
    container.define(RemoveReadoutDefinition, _protocol_cmd(RemoveReadoutDefinition))

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
        return CreateReadoutData(uow, SQLAlchemyReadoutDataRepository(uow), guard, c[EventDispatcher])

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
        return CreateDoseResponseCurve(uow, SQLAlchemyDoseResponseCurveRepository(uow), guard, c[EventDispatcher])

    def _dose_response_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyDoseResponseCurveRepository(uow))
        return _f

    container.define(CreateDoseResponseCurve, _dose_response_create)
    container.define(ListDoseResponseByRun, _dose_response_query(ListDoseResponseByRun))

    return container
