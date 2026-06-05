"""Inventory + plate-import-pipeline dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.inventory.batch_identifiers import (
    AddBatchIdentifier,
    ListBatchIdentifiers,
    RemoveBatchIdentifier,
)
from cellar.application.inventory.bulk_add_batch_identifiers import BulkAddBatchIdentifiers
from cellar.application.inventory.create_batch import CreateBatch
from cellar.application.inventory.create_sample import CreateSample
from cellar.application.inventory.delete_storage_location import DeleteStorageLocation
from cellar.application.inventory.export_plate_layout import ExportPlateLayout
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
from cellar.application.inventory.plate_read_model import PlateReadModelService
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

from ._core import _get_use_case

__all__ = [
    "AddBatchIdentifierDep",
    "AliquotSampleDep",
    "BulkAddBatchIdentifiersDep",
    "ChangeStatusDep",
    "ClearQuarantineSampleDep",
    # Inventory
    "CreateBatchDep",
    "CreateImportTemplateDep",
    "CreateSampleDep",
    "CreateStorageLocationDep",
    "DeleteImportTemplateDep",
    "DeletePlateDep",
    "DeleteStorageLocationDep",
    "DerivePlateDep",
    "DisposeSampleDep",
    "ExportPlateLayoutDep",
    "GetBatchDep",
    "GetInventorySummaryDep",
    "GetPlateDep",
    "GetSampleDep",
    "GetStorageLocationChildrenDep",
    # Plate-import pipeline
    "ImportFileCacheDep",
    "ImportPlateDataServiceDep",
    "ListBatchIdentifiersDep",
    "ListBatchesByMoleculeDep",
    "ListBatchesGlobalDep",
    "ListChildrenDep",
    "ListImportTemplatesDep",
    "ListPlatesDep",
    "ListSamplesByBatchDep",
    "ListSamplesGlobalDep",
    "ListStorageLocationsDep",
    "ListStorageLocationsWithCountsDep",
    "MapWellsDep",
    "MoveSampleDep",
    "PlateReadModelServiceDep",
    "QuarantineSampleDep",
    "RegisterPlateDep",
    "RemoveBatchIdentifierDep",
    "UpdateBatchDep",
    "UpdatePlateDep",
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
DeletePlateDep = Annotated[DeletePlate, Depends(_get_use_case(DeletePlate))]
ExportPlateLayoutDep = Annotated[ExportPlateLayout, Depends(_get_use_case(ExportPlateLayout))]
PlateReadModelServiceDep = Annotated[
    PlateReadModelService, Depends(_get_use_case(PlateReadModelService))
]

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
