"""External vault (CDD) import dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.cdd_import.cancel_cdd_molecule_import import CancelCddMoleculeImport
from cellar.application.cdd_import.cancel_cdd_plate_import import CancelCddPlateImport
from cellar.application.cdd_import.force_fail_cdd_molecule_import import (
    ForceFailCddMoleculeImport,
)
from cellar.application.cdd_import.force_fail_cdd_plate_import import ForceFailCddPlateImport
from cellar.application.cdd_import.get_cdd_molecule_import_runtime_status import (
    GetCddMoleculeImportRuntimeStatus,
)
from cellar.application.cdd_import.get_cdd_molecule_import_status import (
    GetCddMoleculeImportStatusFromDb,
    SyncFailedCddMoleculeImport,
)
from cellar.application.cdd_import.get_cdd_plate_import_runtime_status import (
    GetCddPlateImportRuntimeStatus,
)
from cellar.application.cdd_import.get_cdd_plate_import_status import (
    GetCddPlateImportStatusFromDb,
    SyncFailedCddPlateImport,
)
from cellar.application.cdd_import.import_cdd_protocol import ImportCddProtocol
from cellar.application.cdd_import.list_cdd_molecule_imports import ListCddMoleculeImports
from cellar.application.cdd_import.list_cdd_plate_imports import ListCddPlateImports
from cellar.application.cdd_import.list_cdd_protocols import ListCddProtocols
from cellar.application.cdd_import.preview_cdd_protocol_import import PreviewCddProtocolImport
from cellar.application.cdd_import.start_cdd_molecule_import import StartCddMoleculeImport
from cellar.application.cdd_import.start_cdd_plate_import import StartCddPlateImport

from ._core import _get_use_case

__all__ = [
    "CancelCddMoleculeImportDep",
    "CancelCddPlateImportDep",
    "ForceFailCddMoleculeImportDep",
    "ForceFailCddPlateImportDep",
    "GetCddMoleculeImportRuntimeStatusDep",
    "GetCddMoleculeImportStatusFromDbDep",
    "GetCddPlateImportRuntimeStatusDep",
    "GetCddPlateImportStatusFromDbDep",
    "ImportCddProtocolDep",
    "ListCddMoleculeImportsDep",
    "ListCddPlateImportsDep",
    "ListCddProtocolsDep",
    "PreviewCddProtocolImportDep",
    "StartCddMoleculeImportDep",
    "StartCddPlateImportDep",
    "SyncFailedCddMoleculeImportDep",
    "SyncFailedCddPlateImportDep",
]

ListCddProtocolsDep = Annotated[ListCddProtocols, Depends(_get_use_case(ListCddProtocols))]
PreviewCddProtocolImportDep = Annotated[
    PreviewCddProtocolImport, Depends(_get_use_case(PreviewCddProtocolImport))
]
ImportCddProtocolDep = Annotated[ImportCddProtocol, Depends(_get_use_case(ImportCddProtocol))]
StartCddMoleculeImportDep = Annotated[
    StartCddMoleculeImport, Depends(_get_use_case(StartCddMoleculeImport))
]
ListCddMoleculeImportsDep = Annotated[
    ListCddMoleculeImports, Depends(_get_use_case(ListCddMoleculeImports))
]
ForceFailCddMoleculeImportDep = Annotated[
    ForceFailCddMoleculeImport, Depends(_get_use_case(ForceFailCddMoleculeImport))
]
GetCddMoleculeImportStatusFromDbDep = Annotated[
    GetCddMoleculeImportStatusFromDb, Depends(_get_use_case(GetCddMoleculeImportStatusFromDb))
]
SyncFailedCddMoleculeImportDep = Annotated[
    SyncFailedCddMoleculeImport, Depends(_get_use_case(SyncFailedCddMoleculeImport))
]
GetCddMoleculeImportRuntimeStatusDep = Annotated[
    GetCddMoleculeImportRuntimeStatus,
    Depends(_get_use_case(GetCddMoleculeImportRuntimeStatus)),
]
CancelCddMoleculeImportDep = Annotated[
    CancelCddMoleculeImport, Depends(_get_use_case(CancelCddMoleculeImport))
]
StartCddPlateImportDep = Annotated[
    StartCddPlateImport, Depends(_get_use_case(StartCddPlateImport))
]
ListCddPlateImportsDep = Annotated[
    ListCddPlateImports, Depends(_get_use_case(ListCddPlateImports))
]
ForceFailCddPlateImportDep = Annotated[
    ForceFailCddPlateImport, Depends(_get_use_case(ForceFailCddPlateImport))
]
GetCddPlateImportStatusFromDbDep = Annotated[
    GetCddPlateImportStatusFromDb, Depends(_get_use_case(GetCddPlateImportStatusFromDb))
]
SyncFailedCddPlateImportDep = Annotated[
    SyncFailedCddPlateImport, Depends(_get_use_case(SyncFailedCddPlateImport))
]
GetCddPlateImportRuntimeStatusDep = Annotated[
    GetCddPlateImportRuntimeStatus,
    Depends(_get_use_case(GetCddPlateImportRuntimeStatus)),
]
CancelCddPlateImportDep = Annotated[
    CancelCddPlateImport, Depends(_get_use_case(CancelCddPlateImport))
]
