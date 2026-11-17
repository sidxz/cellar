"""Long-format run-file import dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.screening.flag_run_outliers import FlagRunOutliers
from cellar.application.screening.get_melting_analysis import GetMeltingAnalysis
from cellar.application.screening.get_peak_candidates import GetPeakCandidates
from cellar.application.screening.import_instrument_file import ImportInstrumentFile
from cellar.application.screening.import_run_file import (
    ImportRunFile,
    PreviewRunFile,
    RepreviewRunFile,
)
from cellar.application.screening.list_instrument_file_formats import ListInstrumentFileFormats
from cellar.application.screening.manage_melting_steps import (
    AddMeltingStep,
    AssignMeltingStep,
    ReviewMeltingStep,
)
from cellar.application.screening.preview_instrument_file import PreviewInstrumentFile
from cellar.application.screening.recompute_run import RecomputeRun
from cellar.application.screening.relabel_run_positions import RelabelRunPositions
from cellar.application.screening.resolve_layout_file import ResolveLayoutFile
from cellar.application.screening.resolve_position_labels import ResolvePositionLabels
from cellar.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    DeleteRunImportTemplate,
    ListRunImportTemplates,
    UpdateRunImportTemplate,
)

from ._core import _get_use_case

__all__ = [
    "AddMeltingStepDep",
    "AssignMeltingStepDep",
    "CreateRunImportTemplateDep",
    "DeleteRunImportTemplateDep",
    "FlagRunOutliersDep",
    "GetMeltingAnalysisDep",
    "GetPeakCandidatesDep",
    "ImportInstrumentFileDep",
    "ImportRunFileDep",
    "ListInstrumentFileFormatsDep",
    "ListRunImportTemplatesDep",
    "PreviewInstrumentFileDep",
    "PreviewRunFileDep",
    "RecomputeRunDep",
    "RelabelRunPositionsDep",
    "RepreviewRunFileDep",
    "ResolveLayoutFileDep",
    "ResolvePositionLabelsDep",
    "ReviewMeltingStepDep",
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
FlagRunOutliersDep = Annotated[FlagRunOutliers, Depends(_get_use_case(FlagRunOutliers))]
RecomputeRunDep = Annotated[RecomputeRun, Depends(_get_use_case(RecomputeRun))]
ResolveLayoutFileDep = Annotated[ResolveLayoutFile, Depends(_get_use_case(ResolveLayoutFile))]
ResolvePositionLabelsDep = Annotated[
    ResolvePositionLabels, Depends(_get_use_case(ResolvePositionLabels))
]
ListInstrumentFileFormatsDep = Annotated[
    ListInstrumentFileFormats, Depends(_get_use_case(ListInstrumentFileFormats))
]
GetMeltingAnalysisDep = Annotated[GetMeltingAnalysis, Depends(_get_use_case(GetMeltingAnalysis))]
GetPeakCandidatesDep = Annotated[GetPeakCandidates, Depends(_get_use_case(GetPeakCandidates))]
AddMeltingStepDep = Annotated[AddMeltingStep, Depends(_get_use_case(AddMeltingStep))]
ReviewMeltingStepDep = Annotated[ReviewMeltingStep, Depends(_get_use_case(ReviewMeltingStep))]
AssignMeltingStepDep = Annotated[AssignMeltingStep, Depends(_get_use_case(AssignMeltingStep))]
