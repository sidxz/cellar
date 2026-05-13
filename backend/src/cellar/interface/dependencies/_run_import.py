"""Long-format run-file import dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.screening.import_run_file import (
    ImportRunFile,
    PreviewRunFile,
    RepreviewRunFile,
)
from cellar.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    DeleteRunImportTemplate,
    ListRunImportTemplates,
    UpdateRunImportTemplate,
)

from ._core import _get_use_case

__all__ = [
    "PreviewRunFileDep",
    "RepreviewRunFileDep",
    "ImportRunFileDep",
    "CreateRunImportTemplateDep",
    "UpdateRunImportTemplateDep",
    "DeleteRunImportTemplateDep",
    "ListRunImportTemplatesDep",
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
