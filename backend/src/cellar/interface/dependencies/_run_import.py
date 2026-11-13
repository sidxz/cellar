"""Long-format run-file import dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.screening.import_instrument_file import ImportInstrumentFile
from cellar.application.screening.import_run_file import (
    ImportRunFile,
    PreviewRunFile,
    RepreviewRunFile,
)
from cellar.application.screening.preview_instrument_file import PreviewInstrumentFile
from cellar.application.screening.relabel_run_positions import RelabelRunPositions
from cellar.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    DeleteRunImportTemplate,
    ListRunImportTemplates,
    UpdateRunImportTemplate,
)

from ._core import _get_use_case

__all__ = [
    "CreateRunImportTemplateDep",
    "DeleteRunImportTemplateDep",
    "ImportInstrumentFileDep",
    "ImportRunFileDep",
    "ListRunImportTemplatesDep",
    "PreviewInstrumentFileDep",
    "PreviewRunFileDep",
    "RelabelRunPositionsDep",
    "RepreviewRunFileDep",
    "UpdateRunImportTemplateDep",
]

PreviewRunFileDep = Annotated[PreviewRunFile, Depends(_get_use_case(PreviewRunFile))]
RepreviewRunFileDep = Annotated[RepreviewRunFile, Depends(_get_use_case(RepreviewRunFile))]
ImportRunFileDep = Annotated[ImportRunFile, Depends(_get_use_case(ImportRunFile))]
CreateRunImportTemplateDep = Annotated[
    CreateRunImportTemplate, Depends(_get_use_case(CreateRunImportTemplate))
]
UpdateRunImportTemplateDep = Annotated[
    UpdateRunImportTemplate, Depends(_get_use_case(UpdateRunImportTemplate))
]
DeleteRunImportTemplateDep = Annotated[
    DeleteRunImportTemplate, Depends(_get_use_case(DeleteRunImportTemplate))
]
ListRunImportTemplatesDep = Annotated[
    ListRunImportTemplates, Depends(_get_use_case(ListRunImportTemplates))
]
PreviewInstrumentFileDep = Annotated[
    PreviewInstrumentFile, Depends(_get_use_case(PreviewInstrumentFile))
]
ImportInstrumentFileDep = Annotated[
    ImportInstrumentFile, Depends(_get_use_case(ImportInstrumentFile))
]
RelabelRunPositionsDep = Annotated[
    RelabelRunPositions, Depends(_get_use_case(RelabelRunPositions))
]
