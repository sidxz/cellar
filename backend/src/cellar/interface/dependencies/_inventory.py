"""Inventory + plate-import-pipeline dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.inventory.batch_identifiers import (
    AddBatchIdentifier,
    ListBatchIdentifiers,
    RemoveBatchIdentifier,
)
from cellar.application.inventory.bulk_add_batch_identifiers import BulkAddBatchIdentifiers
from cellar.application.inventory.collection_plate_groups import ListPlateGroupsForCollection
from cellar.application.inventory.comments import AddComment, ListComments
from cellar.application.inventory.create_batch import CreateBatch
from cellar.application.inventory.create_sample import CreateSample
from cellar.application.inventory.delete_storage_location import DeleteStorageLocation
from cellar.application.inventory.export_plate_layout import ExportPlateLayout
from cellar.application.inventory.get_batch import GetBatch, ListBatchesByMolecule
from cellar.application.inventory.get_inventory_summary import GetInventorySummary
from cellar.application.inventory.get_plate_insights import GetPlateInsights
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
from cellar.application.inventory.kiosk import ConfirmScan, ResolveScan
from cellar.application.inventory.kiosk_devices import (
    CreateKioskDevice,
    ListKioskDevices,
    RevokeKioskDevice,
)
from cellar.application.inventory.list_batches_global import ListBatchesGlobal
from cellar.application.inventory.list_runs_for_plate import ListRunsForPlate
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
    GetPlateGroup,
    MovePlateGroup,
    RemovePlatesFromGroup,
    UpdatePlateGroup,
)
from cellar.application.inventory.plate_loans import (
    ApproveLoanItems,
    CancelLoanItems,
    ConfirmLoanCheckout,
    ConfirmLoanReturn,
    DenyLoanItems,
    GetLoan,
    ListLoans,
    RequestLoanReturn,
    RequestPlateLoan,
)
from cellar.application.inventory.plate_read_model import PlateReadModelService
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.inventory.registered_plates import (
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
from cellar.application.inventory.update_batch import UpdateBatch
from cellar.application.inventory.update_storage_location import UpdateStorageLocation
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

from ._core import _get_use_case, get_container

__all__ = [
    "AddBatchIdentifierDep",
    "AddCommentDep",
    "AliquotSampleDep",
    "ApproveLoanItemsDep",
    "AssignPlatesToGroupDep",
    "BulkAddBatchIdentifiersDep",
    "CancelLoanItemsDep",
    "ChangeStatusDep",
    "ClearQuarantineSampleDep",
    "ConfirmLoanCheckoutDep",
    "ConfirmLoanReturnDep",
    "ConfirmScanDep",
    # Inventory
    "CreateBatchDep",
    "CreateImportTemplateDep",
    "CreateKioskDeviceDep",
    "CreatePlateGroupDep",
    "CreateSampleDep",
    "CreateStorageLocationDep",
    "DeleteImportTemplateDep",
    "DeletePlateDep",
    "DeletePlateGroupDep",
    "DeleteStorageLocationDep",
    "DenyLoanItemsDep",
    "DerivePlateDep",
    "DisposeSampleDep",
    "ExportPlateLayoutDep",
    "GetBatchDep",
    "GetGroupTreeDep",
    "GetInventorySummaryDep",
    "GetLoanDep",
    "GetOrgPlatePolicyDep",
    "GetPlateDep",
    "GetPlateGroupDep",
    "GetPlateInsightsDep",
    "GetSampleDep",
    "GetStorageLocationChildrenDep",
    # Plate-import pipeline
    "ImportFileCacheDep",
    "ImportPlateDataServiceDep",
    "ListBatchIdentifiersDep",
    "ListBatchesByMoleculeDep",
    "ListBatchesGlobalDep",
    "ListChildrenDep",
    "ListCommentsDep",
    "ListImportTemplatesDep",
    "ListKioskDevicesDep",
    "ListLoansDep",
    "ListPlateGroupsForCollectionDep",
    "ListPlatesDep",
    "ListRunsForPlateDep",
    "ListSamplesByBatchDep",
    "ListSamplesGlobalDep",
    "ListStorageLocationsDep",
    "ListStorageLocationsWithCountsDep",
    "MapWellsDep",
    "MovePlateGroupDep",
    "MoveSampleDep",
    "PlateReadModelServiceDep",
    "PlateVisibilityUoWDep",
    "QuarantineSampleDep",
    "RegisterPlateDep",
    "RemoveBatchIdentifierDep",
    "RemovePlatesFromGroupDep",
    "RequestLoanReturnDep",
    "RequestPlateLoanDep",
    "ResolveScanDep",
    "RevokeKioskDeviceDep",
    "SetOrgPlatePolicyDep",
    "UpdateBatchDep",
    "UpdatePlateDep",
    "UpdatePlateGroupDep",
    "UpdateStorageLocationDep",
]

# --- Inventory dependencies ---
CreateBatchDep = Annotated[CreateBatch, Depends(_get_use_case(CreateBatch))]
GetBatchDep = Annotated[GetBatch, Depends(_get_use_case(GetBatch))]
ListBatchesByMoleculeDep = Annotated[
    ListBatchesByMolecule, Depends(_get_use_case(ListBatchesByMolecule))
]
ListBatchesGlobalDep = Annotated[ListBatchesGlobal, Depends(_get_use_case(ListBatchesGlobal))]
UpdateBatchDep = Annotated[UpdateBatch, Depends(_get_use_case(UpdateBatch))]
AddBatchIdentifierDep = Annotated[AddBatchIdentifier, Depends(_get_use_case(AddBatchIdentifier))]
RemoveBatchIdentifierDep = Annotated[
    RemoveBatchIdentifier, Depends(_get_use_case(RemoveBatchIdentifier))
]
ListBatchIdentifiersDep = Annotated[
    ListBatchIdentifiers, Depends(_get_use_case(ListBatchIdentifiers))
]
BulkAddBatchIdentifiersDep = Annotated[
    BulkAddBatchIdentifiers, Depends(_get_use_case(BulkAddBatchIdentifiers))
]
CreateSampleDep = Annotated[CreateSample, Depends(_get_use_case(CreateSample))]
GetSampleDep = Annotated[GetSample, Depends(_get_use_case(GetSample))]
ListSamplesByBatchDep = Annotated[ListSamplesByBatch, Depends(_get_use_case(ListSamplesByBatch))]
ListSamplesGlobalDep = Annotated[ListSamplesGlobal, Depends(_get_use_case(ListSamplesGlobal))]
AliquotSampleDep = Annotated[AliquotSample, Depends(_get_use_case(AliquotSample))]
MoveSampleDep = Annotated[MoveSample, Depends(_get_use_case(MoveSample))]
QuarantineSampleDep = Annotated[QuarantineSample, Depends(_get_use_case(QuarantineSample))]
ClearQuarantineSampleDep = Annotated[
    ClearQuarantineSample, Depends(_get_use_case(ClearQuarantineSample))
]
DisposeSampleDep = Annotated[DisposeSample, Depends(_get_use_case(DisposeSample))]
CreateStorageLocationDep = Annotated[
    CreateStorageLocation, Depends(_get_use_case(CreateStorageLocation))
]
ListStorageLocationsDep = Annotated[
    ListStorageLocations, Depends(_get_use_case(ListStorageLocations))
]
GetStorageLocationChildrenDep = Annotated[
    GetStorageLocationChildren, Depends(_get_use_case(GetStorageLocationChildren))
]
ListStorageLocationsWithCountsDep = Annotated[
    ListStorageLocationsWithCounts, Depends(_get_use_case(ListStorageLocationsWithCounts))
]
GetInventorySummaryDep = Annotated[
    GetInventorySummary, Depends(_get_use_case(GetInventorySummary))
]
GetPlateInsightsDep = Annotated[GetPlateInsights, Depends(_get_use_case(GetPlateInsights))]
GetOrgPlatePolicyDep = Annotated[GetOrgPlatePolicy, Depends(_get_use_case(GetOrgPlatePolicy))]
SetOrgPlatePolicyDep = Annotated[SetOrgPlatePolicy, Depends(_get_use_case(SetOrgPlatePolicy))]
UpdateStorageLocationDep = Annotated[
    UpdateStorageLocation, Depends(_get_use_case(UpdateStorageLocation))
]
DeleteStorageLocationDep = Annotated[
    DeleteStorageLocation, Depends(_get_use_case(DeleteStorageLocation))
]
RegisterPlateDep = Annotated[RegisterPlate, Depends(_get_use_case(RegisterPlate))]
GetPlateDep = Annotated[GetPlate, Depends(_get_use_case(GetPlate))]
ListPlatesDep = Annotated[ListPlates, Depends(_get_use_case(ListPlates))]
UpdatePlateDep = Annotated[UpdatePlate, Depends(_get_use_case(UpdatePlate))]
MapWellsDep = Annotated[MapWells, Depends(_get_use_case(MapWells))]
ChangeStatusDep = Annotated[ChangeStatus, Depends(_get_use_case(ChangeStatus))]
DerivePlateDep = Annotated[DerivePlate, Depends(_get_use_case(DerivePlate))]
ListChildrenDep = Annotated[ListChildren, Depends(_get_use_case(ListChildren))]
ListRunsForPlateDep = Annotated[ListRunsForPlate, Depends(_get_use_case(ListRunsForPlate))]
DeletePlateDep = Annotated[DeletePlate, Depends(_get_use_case(DeletePlate))]
ExportPlateLayoutDep = Annotated[ExportPlateLayout, Depends(_get_use_case(ExportPlateLayout))]
PlateReadModelServiceDep = Annotated[
    PlateReadModelService, Depends(_get_use_case(PlateReadModelService))
]


def get_plate_visibility_uow(
    container: Annotated[Container, Depends(get_container)],
) -> tuple[PlateVisibilityService, AsyncUnitOfWork]:
    """Per-request ``PlateVisibilityService`` paired with its own ``AsyncUnitOfWork``.

    Same shape as ``SaltMatcherUoWDep`` — the service's repo needs an active
    session, but the read-model callers that need it (e.g. the molecule→plates
    route) aren't use-case objects that own a uow lifecycle themselves, so the
    caller enters/exits the uow around the ``excluded_org_ids``/
    ``borrowed_plate_ids`` calls. Wired with the loan repo so that route can
    apply the spec §5 loan clause too.
    """
    uow = AsyncUnitOfWork(container[async_sessionmaker])
    return (
        PlateVisibilityService(container[OrgDirectoryPort], SQLAlchemyPlateLoanRepository(uow)),
        uow,
    )


PlateVisibilityUoWDep = Annotated[
    tuple[PlateVisibilityService, AsyncUnitOfWork], Depends(get_plate_visibility_uow)
]

# --- Plate Group dependencies ---
CreatePlateGroupDep = Annotated[CreatePlateGroup, Depends(_get_use_case(CreatePlateGroup))]
UpdatePlateGroupDep = Annotated[UpdatePlateGroup, Depends(_get_use_case(UpdatePlateGroup))]
MovePlateGroupDep = Annotated[MovePlateGroup, Depends(_get_use_case(MovePlateGroup))]
DeletePlateGroupDep = Annotated[DeletePlateGroup, Depends(_get_use_case(DeletePlateGroup))]
GetGroupTreeDep = Annotated[GetGroupTree, Depends(_get_use_case(GetGroupTree))]
GetPlateGroupDep = Annotated[GetPlateGroup, Depends(_get_use_case(GetPlateGroup))]
ListPlateGroupsForCollectionDep = Annotated[
    ListPlateGroupsForCollection, Depends(_get_use_case(ListPlateGroupsForCollection))
]
AssignPlatesToGroupDep = Annotated[
    AssignPlatesToGroup, Depends(_get_use_case(AssignPlatesToGroup))
]
RemovePlatesFromGroupDep = Annotated[
    RemovePlatesFromGroup, Depends(_get_use_case(RemovePlatesFromGroup))
]

# --- Plate Loan dependencies ---
RequestPlateLoanDep = Annotated[RequestPlateLoan, Depends(_get_use_case(RequestPlateLoan))]
ListLoansDep = Annotated[ListLoans, Depends(_get_use_case(ListLoans))]
GetLoanDep = Annotated[GetLoan, Depends(_get_use_case(GetLoan))]
ApproveLoanItemsDep = Annotated[ApproveLoanItems, Depends(_get_use_case(ApproveLoanItems))]
DenyLoanItemsDep = Annotated[DenyLoanItems, Depends(_get_use_case(DenyLoanItems))]
ConfirmLoanCheckoutDep = Annotated[
    ConfirmLoanCheckout, Depends(_get_use_case(ConfirmLoanCheckout))
]
RequestLoanReturnDep = Annotated[RequestLoanReturn, Depends(_get_use_case(RequestLoanReturn))]
ConfirmLoanReturnDep = Annotated[ConfirmLoanReturn, Depends(_get_use_case(ConfirmLoanReturn))]
CancelLoanItemsDep = Annotated[CancelLoanItems, Depends(_get_use_case(CancelLoanItems))]

# --- Kiosk Device dependencies ---
CreateKioskDeviceDep = Annotated[CreateKioskDevice, Depends(_get_use_case(CreateKioskDevice))]
ListKioskDevicesDep = Annotated[ListKioskDevices, Depends(_get_use_case(ListKioskDevices))]
RevokeKioskDeviceDep = Annotated[RevokeKioskDevice, Depends(_get_use_case(RevokeKioskDevice))]

# --- Comment dependencies ---
AddCommentDep = Annotated[AddComment, Depends(_get_use_case(AddComment))]
ListCommentsDep = Annotated[ListComments, Depends(_get_use_case(ListComments))]

# --- Kiosk scan/confirm dependencies ---
ResolveScanDep = Annotated[ResolveScan, Depends(_get_use_case(ResolveScan))]
ConfirmScanDep = Annotated[ConfirmScan, Depends(_get_use_case(ConfirmScan))]

# --- Plate-import pipeline dependencies ---
ImportFileCacheDep = Annotated[ImportFileCache, Depends(_get_use_case(ImportFileCache))]
ImportPlateDataServiceDep = Annotated[
    ImportPlateDataService, Depends(_get_use_case(ImportPlateDataService))
]
CreateImportTemplateDep = Annotated[
    CreateImportTemplate, Depends(_get_use_case(CreateImportTemplate))
]
ListImportTemplatesDep = Annotated[
    ListImportTemplates, Depends(_get_use_case(ListImportTemplates))
]
DeleteImportTemplateDep = Annotated[
    DeleteImportTemplate, Depends(_get_use_case(DeleteImportTemplate))
]
