"""Inventory bindings: batches, samples, storage, summary reader, sample requests,
shipments, synthesis requests, import templates, import plate data service.
"""

from __future__ import annotations

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.admin.admin_delete_registry import register_admin_delete
from cellar.application.inventory.batch_identifiers import (
    AddBatchIdentifier,
    ListBatchIdentifiers,
    RemoveBatchIdentifier,
)
from cellar.application.inventory.bulk_add_batch_identifiers import BulkAddBatchIdentifiers
from cellar.application.inventory.create_batch import CreateBatch
from cellar.application.inventory.create_sample import CreateSample
from cellar.application.inventory.delete_storage_location import DeleteStorageLocation
from cellar.application.inventory.ensure_batch_exists import EnsureBatchExists
from cellar.application.inventory.get_batch import GetBatch, ListBatchesByMolecule
from cellar.application.inventory.get_inventory_summary import GetInventorySummary
from cellar.application.inventory.get_sample import GetSample, ListSamplesByBatch
from cellar.application.inventory.import_plate_data import (
    ImportFileCache,
    ImportPlateDataService,
)
from cellar.application.inventory.import_templates import (
    CreateImportTemplate,
    DeleteImportTemplate,
    ListImportTemplates,
)
from cellar.application.inventory.inventory_summary_reader import InventorySummaryReader
from cellar.application.inventory.list_batches_global import ListBatchesGlobal
from cellar.application.inventory.list_samples_global import ListSamplesGlobal
from cellar.application.inventory.manage_sample import (
    AliquotSample,
    ClearQuarantineSample,
    DisposeSample,
    MoveSample,
    QuarantineSample,
)
from cellar.application.inventory.manage_storage import (
    CreateStorageLocation,
    GetStorageLocationChildren,
    ListStorageLocations,
    ListStorageLocationsWithCounts,
)
from cellar.application.inventory.org_plate_policy import GetOrgPlatePolicy, SetOrgPlatePolicy
from cellar.application.inventory.plate_groups import (
    AssignPlatesToGroup,
    CreatePlateGroup,
    DeletePlateGroup,
    GetGroupTree,
    MovePlateGroup,
    RemovePlatesFromGroup,
    UpdatePlateGroup,
)
from cellar.application.inventory.plate_loans import GetLoan, ListLoans, RequestPlateLoan
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.inventory.preview_shipment_import import PreviewShipmentImport
from cellar.application.inventory.sample_requests import (
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
from cellar.application.inventory.shipments import (
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
from cellar.application.inventory.sync_batch_identifier_mirrors import SyncBatchIdentifierMirrors
from cellar.application.inventory.synthesis_requests import (
    ApproveSynthesisRequest,
    AssignSynthesisRequest,
    CancelSynthesisRequest,
    CompleteSynthesis,
    CreateSynthesisRequest,
    DeleteSynthesisRequest,
    FailSynthesis,
    FlagInfeasible,
    FulfillSynthesisRequest,
    GetSynthesisRequest,
    ListSynthesisRequests,
    RejectSynthesisRequest,
    StartSynthesis,
    SubmitSynthesisRequest,
    UpdateSynthesisRequest,
)
from cellar.application.inventory.update_batch import UpdateBatch
from cellar.application.inventory.update_storage_location import UpdateStorageLocation
from cellar.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from cellar.application.screening.create_run import CreateRun
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.infrastructure.cache.in_memory_file_cache import InMemoryImportFileCache
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.import_template_repository import (
    SQLAlchemyImportTemplateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.inventory_summary_reader import (
    SQLAlchemyInventorySummaryReader,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.org_plate_policy_repository import (
    SQLAlchemyOrgPlatePolicyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.sample_repository import (
    SQLAlchemySampleRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.sample_request_repository import (
    SQLAlchemySampleRequestRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.shipment_repository import (
    SQLAlchemyShipmentRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.storage_location_repository import (
    SQLAlchemyStorageLocationRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_repository import (
    SQLAlchemySynthesisRequestRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.custom_field_definition_repository import (  # noqa: E501
    SQLAlchemyCustomFieldDefinitionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (  # noqa: E501
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_inventory(container: Container) -> None:
    # Force cascade rules to register at DI bootstrap.
    import cellar.infrastructure.cascade.rules_inventory  # noqa: F401

    # --- Batches ---
    def _batch_cmd(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        return CreateBatch(
            uow,
            batch_repo,
            SQLAlchemyMoleculeRepository(uow),
            c[EventDispatcher],
            validator,
            workspace_settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
            sync=sync,
        )

    def _batch_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyBatchRepository(uow))

        return _f

    def _update_batch(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return UpdateBatch(uow, SQLAlchemyBatchRepository(uow), c[EventDispatcher], validator)

    container.define(CreateBatch, _batch_cmd)
    container.define(UpdateBatch, _update_batch)
    container.define(GetBatch, _batch_query(GetBatch))
    container.define(ListBatchesByMolecule, _batch_query(ListBatchesByMolecule))
    container.define(ListBatchesGlobal, _batch_query(ListBatchesGlobal))

    def _add_batch_identifier(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddBatchIdentifier(uow, SQLAlchemyBatchRepository(uow), c[EventDispatcher])

    def _remove_batch_identifier(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveBatchIdentifier(uow, SQLAlchemyBatchRepository(uow), c[EventDispatcher])

    def _list_batch_identifiers(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListBatchIdentifiers(uow, SQLAlchemyBatchRepository(uow))

    def _ensure_batch_exists(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        return EnsureBatchExists(
            uow=uow,
            batch_repo=batch_repo,
            settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            sync=sync,
        )

    def _bulk_add_batch_identifiers(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return BulkAddBatchIdentifiers(
            uow=uow,
            batch_repo=SQLAlchemyBatchRepository(uow),
            settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
        )

    container.define(AddBatchIdentifier, _add_batch_identifier)
    container.define(RemoveBatchIdentifier, _remove_batch_identifier)
    container.define(ListBatchIdentifiers, _list_batch_identifiers)
    container.define(EnsureBatchExists, _ensure_batch_exists)
    container.define(BulkAddBatchIdentifiers, _bulk_add_batch_identifiers)

    # --- Samples ---
    def _sample_create(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateSample(
            uow,
            SQLAlchemyBatchRepository(uow),
            SQLAlchemySampleRepository(uow),
            SQLAlchemyMoleculeRepository(uow),
            c[EventDispatcher],
        )

    def _sample_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRepository(uow), c[EventDispatcher])

        return _f

    def _sample_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRepository(uow))

        return _f

    container.define(CreateSample, _sample_create)
    container.define(GetSample, _sample_query(GetSample))
    container.define(ListSamplesByBatch, _sample_query(ListSamplesByBatch))
    container.define(ListSamplesGlobal, _sample_query(ListSamplesGlobal))
    container.define(AliquotSample, _sample_cmd(AliquotSample))

    def _move_sample(c: Container):
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

    # --- Storage Locations ---
    def _storage_cmd(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateStorageLocation(
            uow, SQLAlchemyStorageLocationRepository(uow), c[EventDispatcher]
        )

    def _storage_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyStorageLocationRepository(uow))

        return _f

    def _storage_update(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdateStorageLocation(
            uow, SQLAlchemyStorageLocationRepository(uow), c[EventDispatcher]
        )

    def _storage_delete(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteStorageLocation(
            uow,
            SQLAlchemyStorageLocationRepository(uow),
            SQLAlchemySampleRepository(uow),
            c[EventDispatcher],
        )

    container.define(CreateStorageLocation, _storage_cmd)
    container.define(UpdateStorageLocation, _storage_update)
    container.define(DeleteStorageLocation, _storage_delete)
    container.define(ListStorageLocations, _storage_query(ListStorageLocations))
    container.define(GetStorageLocationChildren, _storage_query(GetStorageLocationChildren))
    container.define(
        ListStorageLocationsWithCounts, _storage_query(ListStorageLocationsWithCounts)
    )

    # --- Inventory Summary ---
    container.define(
        InventorySummaryReader,
        lambda c: SQLAlchemyInventorySummaryReader(c[async_sessionmaker]),
    )
    container.define(
        GetInventorySummary,
        lambda c: GetInventorySummary(reader=c[InventorySummaryReader]),
    )

    # --- Sample Requests ---
    def _sample_request_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRequestRepository(uow), c[EventDispatcher])

        return _f

    def _sample_request_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySampleRequestRepository(uow))

        return _f

    def _create_sample_request(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateSampleRequest(
            uow,
            SQLAlchemySampleRequestRepository(uow),
            c[EventDispatcher],
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    def _fulfill_sample_request(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FulfillSampleRequest(
            uow,
            SQLAlchemySampleRequestRepository(uow),
            c[EventDispatcher],
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
    def _shipment_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyShipmentRepository(uow), c[EventDispatcher])

        return _f

    def _shipment_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyShipmentRepository(uow))

        return _f

    def _create_shipment(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateShipment(
            uow,
            SQLAlchemyShipmentRepository(uow),
            c[EventDispatcher],
            sample_repo=SQLAlchemySampleRepository(uow),
        )

    container.define(CreateShipment, _create_shipment)
    container.define(GetShipment, _shipment_query(GetShipment))
    container.define(ListShipments, _shipment_query(ListShipments))
    container.define(ShipShipment, _shipment_cmd(ShipShipment))
    container.define(MarkShipmentInTransit, _shipment_cmd(MarkShipmentInTransit))
    container.define(DeliverShipment, _shipment_cmd(DeliverShipment))
    container.define(ReturnShipment, _shipment_cmd(ReturnShipment))

    def _add_shipment_item(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddShipmentItem(
            uow,
            SQLAlchemyShipmentRepository(uow),
            c[EventDispatcher],
            sample_repo=SQLAlchemySampleRepository(uow),
        )

    container.define(AddShipmentItem, _add_shipment_item)
    container.define(UpdateShipment, _shipment_cmd(UpdateShipment))
    container.define(DeleteShipment, _shipment_cmd(DeleteShipment))

    def _preview_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return PreviewShipmentImport(
            uow,
            SQLAlchemyMoleculeRepository(uow),
            SQLAlchemyBatchRepository(uow),
            SQLAlchemySampleRepository(uow),
        )

    container.define(PreviewShipmentImport, _preview_import)

    # --- Synthesis Requests ---
    def _synth_req_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRequestRepository(uow), c[EventDispatcher])

        return _f

    def _synth_req_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRequestRepository(uow))

        return _f

    container.define(CreateSynthesisRequest, _synth_req_cmd(CreateSynthesisRequest))
    container.define(SubmitSynthesisRequest, _synth_req_cmd(SubmitSynthesisRequest))
    container.define(ApproveSynthesisRequest, _synth_req_cmd(ApproveSynthesisRequest))
    container.define(RejectSynthesisRequest, _synth_req_cmd(RejectSynthesisRequest))
    container.define(AssignSynthesisRequest, _synth_req_cmd(AssignSynthesisRequest))
    container.define(StartSynthesis, _synth_req_cmd(StartSynthesis))
    container.define(FlagInfeasible, _synth_req_cmd(FlagInfeasible))
    container.define(CompleteSynthesis, _synth_req_cmd(CompleteSynthesis))

    def _fulfill_synth_req(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FulfillSynthesisRequest(
            uow,
            SQLAlchemySynthesisRequestRepository(uow),
            c[EventDispatcher],
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    container.define(FulfillSynthesisRequest, _fulfill_synth_req)
    container.define(FailSynthesis, _synth_req_cmd(FailSynthesis))
    container.define(CancelSynthesisRequest, _synth_req_cmd(CancelSynthesisRequest))
    container.define(GetSynthesisRequest, _synth_req_query(GetSynthesisRequest))
    container.define(ListSynthesisRequests, _synth_req_query(ListSynthesisRequests))
    container.define(UpdateSynthesisRequest, _synth_req_cmd(UpdateSynthesisRequest))
    container.define(DeleteSynthesisRequest, _synth_req_cmd(DeleteSynthesisRequest))

    # --- Import Templates ---
    def _import_tmpl_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyImportTemplateRepository(uow), c[EventDispatcher])

        return _f

    def _import_tmpl_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyImportTemplateRepository(uow))

        return _f

    container.define(CreateImportTemplate, _import_tmpl_cmd(CreateImportTemplate))
    container.define(ListImportTemplates, _import_tmpl_query(ListImportTemplates))
    container.define(DeleteImportTemplate, _import_tmpl_cmd(DeleteImportTemplate))

    # --- Import Plate Data Service ---
    # Bind the application Protocol to the in-memory implementation. Swap
    # to a Valkey-backed cache without changing application callers.
    container.define(ImportFileCache, Singleton(InMemoryImportFileCache))

    def _import_plate_data_service(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportPlateDataService(
            uow=uow,
            plate_repo=SQLAlchemyRegisteredPlateRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            cache=c[ImportFileCache],
            visibility=PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
            create_run=c[CreateRun],
            bulk_create_readout_data=c[BulkCreateReadoutData],
        )

    container.define(ImportPlateDataService, _import_plate_data_service)

    # --- Org Plate Policies ---
    def _get_org_plate_policy(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetOrgPlatePolicy(uow, SQLAlchemyOrgPlatePolicyRepository(uow))

    def _set_org_plate_policy(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetOrgPlatePolicy(uow, SQLAlchemyOrgPlatePolicyRepository(uow), c[EventDispatcher])

    container.define(GetOrgPlatePolicy, _get_org_plate_policy)
    container.define(SetOrgPlatePolicy, _set_org_plate_policy)

    # --- Plate Groups ---
    def _create_plate_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreatePlateGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _update_plate_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdatePlateGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _move_plate_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MovePlateGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _delete_plate_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeletePlateGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _get_group_tree(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetGroupTree(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _assign_plates_to_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AssignPlatesToGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            SQLAlchemyRegisteredPlateRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _remove_plates_from_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemovePlatesFromGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            SQLAlchemyRegisteredPlateRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    container.define(CreatePlateGroup, _create_plate_group)
    container.define(UpdatePlateGroup, _update_plate_group)
    container.define(MovePlateGroup, _move_plate_group)
    container.define(DeletePlateGroup, _delete_plate_group)
    container.define(GetGroupTree, _get_group_tree)
    container.define(AssignPlatesToGroup, _assign_plates_to_group)
    container.define(RemovePlatesFromGroup, _remove_plates_from_group)

    # --- Plate Loans ---
    def _request_plate_loan(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RequestPlateLoan(
            uow,
            SQLAlchemyPlateLoanRepository(uow),
            SQLAlchemyRegisteredPlateRepository(uow),
            SQLAlchemyPlateGroupRepository(uow),
            SQLAlchemyOrgPlatePolicyRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _list_loans(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListLoans(
            uow,
            SQLAlchemyPlateLoanRepository(uow),
            SQLAlchemyRegisteredPlateRepository(uow),
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    def _get_loan(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetLoan(
            uow,
            SQLAlchemyPlateLoanRepository(uow),
            SQLAlchemyRegisteredPlateRepository(uow),
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )

    container.define(RequestPlateLoan, _request_plate_loan)
    container.define(ListLoans, _list_loans)
    container.define(GetLoan, _get_loan)

    # --- Admin Hard-Delete Registry (Tier 1) ---
    register_admin_delete(
        entity_type="batch",
        table="batches",
        label_field="batch_number",
    )
    register_admin_delete(
        entity_type="sample",
        table="samples",
        label_field="barcode",
    )
    register_admin_delete(
        entity_type="shipment",
        table="shipments",
        label_field="tracking_number",
    )
    register_admin_delete(
        entity_type="synthesis_request",
        table="synthesis_requests",
        label_field=None,
    )


def build_inventory_admin_repos(uow) -> dict:
    """Build the repo map for inventory Tier-1 admin deletes."""
    from cellar.application.admin._adapter import RepoAdapter

    return {
        "batch": RepoAdapter(SQLAlchemyBatchRepository(uow), find="find_by_id_in_workspace"),
        "sample": RepoAdapter(SQLAlchemySampleRepository(uow), find="find_by_id_in_workspace"),
        "shipment": RepoAdapter(SQLAlchemyShipmentRepository(uow), find="find_by_id_in_workspace"),
        "synthesis_request": RepoAdapter(
            SQLAlchemySynthesisRequestRepository(uow), find="find_by_id_in_workspace"
        ),
    }
