"""Export use-case dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.export.cancel_export import CancelExport
from cellar.application.export.get_export_status import GetExportStatus
from cellar.application.export.list_exports import ListExports
from cellar.application.export.prepare_export_download import PrepareExportDownload
from cellar.application.export.start_export import StartExport
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient

from ._core import _get_use_case

__all__ = [
    "CancelExportDep",
    "GetExportStatusDep",
    "ListExportsDep",
    "PrepareExportDownloadDep",
    "StartExportDep",
    "StorageDep",
]

StartExportDep = Annotated[StartExport, Depends(_get_use_case(StartExport))]
GetExportStatusDep = Annotated[GetExportStatus, Depends(_get_use_case(GetExportStatus))]
CancelExportDep = Annotated[CancelExport, Depends(_get_use_case(CancelExport))]
ListExportsDep = Annotated[ListExports, Depends(_get_use_case(ListExports))]
StorageDep = Annotated[FsspecStorageClient, Depends(_get_use_case(FsspecStorageClient))]
PrepareExportDownloadDep = Annotated[
    PrepareExportDownload, Depends(_get_use_case(PrepareExportDownload))
]
