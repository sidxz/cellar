"""Screening (protocol/run/readout/dose-response) + compound-flag + plate-template deps."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from cellar.application.screening.classify_dose_response import ClassifyDoseResponseCurve
from cellar.application.screening.condition_grouping_service import ConditionGroupingService
from cellar.application.screening.create_compound_flag import CreateCompoundFlag
from cellar.application.screening.create_dose_response import CreateDoseResponseCurve
from cellar.application.screening.create_protocol import CreateProtocol
from cellar.application.screening.create_readout_data import CreateReadoutData
from cellar.application.screening.create_run import CreateRun
from cellar.application.screening.create_target import CreateTarget
from cellar.application.screening.delete_compound_flag import DeleteCompoundFlag
from cellar.application.screening.delete_run import DeleteRun
from cellar.application.screening.delete_target import DeleteTarget
from cellar.application.screening.fit_dose_response import FitDoseResponseCurves
from cellar.application.screening.get_collection_gap import (
    GetProtocolCollectionGap,
    GetRunCollectionGap,
)
from cellar.application.screening.get_compound_curves import GetCompoundCurves
from cellar.application.screening.get_curve_edit_history import GetCurveEditHistory
from cellar.application.screening.get_dose_response import ListDoseResponseByRun
from cellar.application.screening.get_molecule_activity_detail import GetMoleculeActivityDetail
from cellar.application.screening.get_molecule_test_counts import GetMoleculeTestCounts
from cellar.application.screening.get_plate_map import GetPlateMap
from cellar.application.screening.get_protocol import GetProtocol, ListProtocols
from cellar.application.screening.get_protocol_activity import GetProtocolActivitySummary
from cellar.application.screening.get_protocol_stats import GetProtocolStats
from cellar.application.screening.get_readout_data import ListReadoutDataByRun
from cellar.application.screening.get_run import GetRun, ListRunsByProtocol
from cellar.application.screening.get_target import GetTarget, ListTargets
from cellar.application.screening.import_run_readouts import ImportRunReadouts
from cellar.application.screening.import_summary_file import ImportSummaryFile
from cellar.application.screening.list_compound_flags import ListCompoundFlags
from cellar.application.screening.list_dose_response_enriched import ListDoseResponseEnriched
from cellar.application.screening.list_protocol_summaries import ListProtocolSummaries
from cellar.application.screening.list_readout_data_enriched import ListReadoutDataEnriched
from cellar.application.screening.list_runs_with_counts import ListRunsWithCounts
from cellar.application.screening.lock_protocol import LockProtocol, UnlockProtocol
from cellar.application.screening.lock_run import LockRun, UnlockRun
from cellar.application.screening.manage_condition_definitions import (
    AddConditionDefinition,
    RemoveConditionDefinition,
    UpdateConditionDefinition,
)
from cellar.application.screening.manage_control_layouts import (
    RemoveControlLayout,
    SetControlLayout,
)
from cellar.application.screening.manage_protocol import (
    AddProtocolTarget,
    AddProtocolToProject,
    DeleteProtocol,
    ListProtocolsByProject,
    PublishProtocol,
    RemoveProtocolFromProject,
    RemoveProtocolTarget,
    RetireProtocol,
    UpdateProtocol,
    VersionProtocol,
)
from cellar.application.screening.manage_readout_definitions import (
    AddReadoutDefinition,
    RemoveReadoutDefinition,
    UpdateReadoutDefinition,
)
from cellar.application.screening.manage_run import (
    ApproveRun,
    CompleteRun,
    RejectRun,
    StartRun,
)
from cellar.application.screening.manage_run_collections import (
    AddRunCollection,
    RemoveRunCollection,
)
from cellar.application.screening.manage_run_targets import (
    AddRunTarget,
    RemoveRunTarget,
)
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.application.screening.plate_setup import ParsePlateMapFile, SetUpRunPlate
from cellar.application.screening.plate_templates import (
    CreatePlateTemplate,
    DeletePlateTemplate,
    GetPlateTemplate,
    ListPlateTemplates,
    UpdatePlateTemplate,
)
from cellar.application.screening.preview_summary_file import PreviewSummaryFile
from cellar.application.screening.preview_summary_import import PreviewSummaryImport
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.screening.refit_dose_response import RefitDoseResponseCurve
from cellar.application.screening.refit_dose_response_preview import (
    RefitDoseResponseCurvePreview,
)
from cellar.application.screening.reset_run_data import ResetRunData
from cellar.application.screening.resolve_collection_coverage import (
    GetProtocolCollectionCoverage,
    ResolveRunCollections,
)
from cellar.application.screening.resolve_target_links import (
    GetProtocolTargets,
    ResolveProtocolTargets,
    ResolveRunTargets,
)
from cellar.application.screening.set_run_hit_criteria import (
    ResetRunHitCriteria,
    SetRunHitCriteria,
)
from cellar.application.screening.update_run import UpdateRun
from cellar.application.screening.update_target import UpdateTarget

from ._core import _get_use_case

__all__ = [
    "AddConditionDefinitionDep",
    "AddProtocolTargetDep",
    "AddProtocolToProjectDep",
    "AddReadoutDefinitionDep",
    "AddRunCollectionDep",
    "AddRunTargetDep",
    "ApproveRunDep",
    "BulkCreateReadoutDataDep",
    "ClassifyDoseResponseCurveDep",
    "CompleteRunDep",
    # Runs
    "ConditionGroupingServiceDep",
    "CreateCompoundFlagDep",
    "CreateDoseResponseCurveDep",
    # Plate templates
    "CreatePlateTemplateDep",
    # Screening — protocols
    "CreateProtocolDep",
    # Readouts + dose-response
    "CreateReadoutDataDep",
    "CreateRunDep",
    # Targets
    "CreateTargetDep",
    "DeleteCompoundFlagDep",
    "DeletePlateTemplateDep",
    "DeleteProtocolDep",
    "DeleteRunDep",
    "DeleteTargetDep",
    "FitDoseResponseCurvesDep",
    "GetCompoundCurvesDep",
    "GetCurveEditHistoryDep",
    "GetMoleculeActivityDetailDep",
    "GetMoleculeTestCountsDep",
    "GetPlateMapDep",
    "GetPlateTemplateDep",
    "GetProtocolActivitySummaryDep",
    "GetProtocolCollectionCoverageDep",
    "GetProtocolCollectionGapDep",
    "GetProtocolDep",
    "GetProtocolStatsDep",
    "GetProtocolTargetsDep",
    "GetRunCollectionGapDep",
    "GetRunDep",
    "GetTargetDep",
    "ImportRunReadoutsDep",
    "ImportSummaryFileDep",
    # Compound flags
    "ListCompoundFlagsDep",
    "ListDoseResponseByRunDep",
    "ListDoseResponseEnrichedDep",
    "ListPlateTemplatesDep",
    "ListProtocolSummariesDep",
    "ListProtocolsByProjectDep",
    "ListProtocolsDep",
    "ListReadoutDataByRunDep",
    "ListReadoutDataEnrichedDep",
    "ListRunsByProtocolDep",
    "ListRunsWithCountsDep",
    "ListTargetsDep",
    "LockProtocolDep",
    "LockRunDep",
    "MoleculeActivityServiceDep",
    # Plate setup + readout import
    "ParsePlateMapFileDep",
    "PreviewSummaryFileDep",
    "PreviewSummaryImportDep",
    "PublishProtocolDep",
    "ReadoutCalculationEngineDep",
    "RefitDoseResponseCurveDep",
    "RefitDoseResponseCurvePreviewDep",
    "RejectRunDep",
    "RemoveConditionDefinitionDep",
    "RemoveControlLayoutDep",
    "RemoveProtocolFromProjectDep",
    "RemoveProtocolTargetDep",
    "RemoveReadoutDefinitionDep",
    "RemoveRunCollectionDep",
    "RemoveRunTargetDep",
    "ResetRunDataDep",
    "ResetRunHitCriteriaDep",
    "ResolveProtocolTargetsDep",
    "ResolveRunCollectionsDep",
    "ResolveRunTargetsDep",
    "RetireProtocolDep",
    "SetControlLayoutDep",
    "SetRunHitCriteriaDep",
    "SetUpRunPlateDep",
    "StartRunDep",
    "UnlockProtocolDep",
    "UnlockRunDep",
    "UpdateConditionDefinitionDep",
    "UpdatePlateTemplateDep",
    "UpdateProtocolDep",
    "UpdateReadoutDefinitionDep",
    "UpdateRunDep",
    "UpdateTargetDep",
    "VersionProtocolDep",
]

# --- Screening dependencies ---
CreateProtocolDep = Annotated[CreateProtocol, Depends(_get_use_case(CreateProtocol))]
GetProtocolDep = Annotated[GetProtocol, Depends(_get_use_case(GetProtocol))]
ListProtocolsDep = Annotated[ListProtocols, Depends(_get_use_case(ListProtocols))]
ListProtocolSummariesDep = Annotated[
    ListProtocolSummaries, Depends(_get_use_case(ListProtocolSummaries))
]
PublishProtocolDep = Annotated[PublishProtocol, Depends(_get_use_case(PublishProtocol))]
RetireProtocolDep = Annotated[RetireProtocol, Depends(_get_use_case(RetireProtocol))]
LockProtocolDep = Annotated[LockProtocol, Depends(_get_use_case(LockProtocol))]
UnlockProtocolDep = Annotated[UnlockProtocol, Depends(_get_use_case(UnlockProtocol))]
VersionProtocolDep = Annotated[VersionProtocol, Depends(_get_use_case(VersionProtocol))]
ListProtocolsByProjectDep = Annotated[
    ListProtocolsByProject, Depends(_get_use_case(ListProtocolsByProject))
]
AddProtocolToProjectDep = Annotated[
    AddProtocolToProject, Depends(_get_use_case(AddProtocolToProject))
]
RemoveProtocolFromProjectDep = Annotated[
    RemoveProtocolFromProject, Depends(_get_use_case(RemoveProtocolFromProject))
]
AddProtocolTargetDep = Annotated[AddProtocolTarget, Depends(_get_use_case(AddProtocolTarget))]
RemoveProtocolTargetDep = Annotated[
    RemoveProtocolTarget, Depends(_get_use_case(RemoveProtocolTarget))
]
GetProtocolTargetsDep = Annotated[GetProtocolTargets, Depends(_get_use_case(GetProtocolTargets))]
ResolveProtocolTargetsDep = Annotated[
    ResolveProtocolTargets, Depends(_get_use_case(ResolveProtocolTargets))
]
ResolveRunTargetsDep = Annotated[ResolveRunTargets, Depends(_get_use_case(ResolveRunTargets))]
AddRunTargetDep = Annotated[AddRunTarget, Depends(_get_use_case(AddRunTarget))]
RemoveRunTargetDep = Annotated[RemoveRunTarget, Depends(_get_use_case(RemoveRunTarget))]
AddRunCollectionDep = Annotated[AddRunCollection, Depends(_get_use_case(AddRunCollection))]
RemoveRunCollectionDep = Annotated[
    RemoveRunCollection, Depends(_get_use_case(RemoveRunCollection))
]
ResolveRunCollectionsDep = Annotated[
    ResolveRunCollections, Depends(_get_use_case(ResolveRunCollections))
]
GetProtocolCollectionCoverageDep = Annotated[
    GetProtocolCollectionCoverage, Depends(_get_use_case(GetProtocolCollectionCoverage))
]
GetRunCollectionGapDep = Annotated[
    GetRunCollectionGap, Depends(_get_use_case(GetRunCollectionGap))
]
GetProtocolCollectionGapDep = Annotated[
    GetProtocolCollectionGap, Depends(_get_use_case(GetProtocolCollectionGap))
]
UpdateProtocolDep = Annotated[UpdateProtocol, Depends(_get_use_case(UpdateProtocol))]
DeleteProtocolDep = Annotated[DeleteProtocol, Depends(_get_use_case(DeleteProtocol))]
AddReadoutDefinitionDep = Annotated[
    AddReadoutDefinition, Depends(_get_use_case(AddReadoutDefinition))
]
RemoveReadoutDefinitionDep = Annotated[
    RemoveReadoutDefinition, Depends(_get_use_case(RemoveReadoutDefinition))
]
UpdateReadoutDefinitionDep = Annotated[
    UpdateReadoutDefinition, Depends(_get_use_case(UpdateReadoutDefinition))
]
AddConditionDefinitionDep = Annotated[
    AddConditionDefinition, Depends(_get_use_case(AddConditionDefinition))
]
RemoveConditionDefinitionDep = Annotated[
    RemoveConditionDefinition, Depends(_get_use_case(RemoveConditionDefinition))
]
UpdateConditionDefinitionDep = Annotated[
    UpdateConditionDefinition, Depends(_get_use_case(UpdateConditionDefinition))
]
SetControlLayoutDep = Annotated[SetControlLayout, Depends(_get_use_case(SetControlLayout))]
RemoveControlLayoutDep = Annotated[
    RemoveControlLayout, Depends(_get_use_case(RemoveControlLayout))
]
CreateTargetDep = Annotated[CreateTarget, Depends(_get_use_case(CreateTarget))]
GetTargetDep = Annotated[GetTarget, Depends(_get_use_case(GetTarget))]
ListTargetsDep = Annotated[ListTargets, Depends(_get_use_case(ListTargets))]
UpdateTargetDep = Annotated[UpdateTarget, Depends(_get_use_case(UpdateTarget))]
DeleteTargetDep = Annotated[DeleteTarget, Depends(_get_use_case(DeleteTarget))]
ConditionGroupingServiceDep = Annotated[
    ConditionGroupingService, Depends(_get_use_case(ConditionGroupingService))
]
CreateRunDep = Annotated[CreateRun, Depends(_get_use_case(CreateRun))]
DeleteRunDep = Annotated[DeleteRun, Depends(_get_use_case(DeleteRun))]
ResetRunDataDep = Annotated[ResetRunData, Depends(_get_use_case(ResetRunData))]
GetRunDep = Annotated[GetRun, Depends(_get_use_case(GetRun))]
ListRunsByProtocolDep = Annotated[ListRunsByProtocol, Depends(_get_use_case(ListRunsByProtocol))]
StartRunDep = Annotated[StartRun, Depends(_get_use_case(StartRun))]
CompleteRunDep = Annotated[CompleteRun, Depends(_get_use_case(CompleteRun))]
ApproveRunDep = Annotated[ApproveRun, Depends(_get_use_case(ApproveRun))]
RejectRunDep = Annotated[RejectRun, Depends(_get_use_case(RejectRun))]
LockRunDep = Annotated[LockRun, Depends(_get_use_case(LockRun))]
UpdateRunDep = Annotated[UpdateRun, Depends(_get_use_case(UpdateRun))]
UnlockRunDep = Annotated[UnlockRun, Depends(_get_use_case(UnlockRun))]
SetRunHitCriteriaDep = Annotated[SetRunHitCriteria, Depends(_get_use_case(SetRunHitCriteria))]
ResetRunHitCriteriaDep = Annotated[
    ResetRunHitCriteria, Depends(_get_use_case(ResetRunHitCriteria))
]
CreateReadoutDataDep = Annotated[CreateReadoutData, Depends(_get_use_case(CreateReadoutData))]
BulkCreateReadoutDataDep = Annotated[
    BulkCreateReadoutData, Depends(_get_use_case(BulkCreateReadoutData))
]
ListReadoutDataByRunDep = Annotated[
    ListReadoutDataByRun, Depends(_get_use_case(ListReadoutDataByRun))
]
CreateDoseResponseCurveDep = Annotated[
    CreateDoseResponseCurve, Depends(_get_use_case(CreateDoseResponseCurve))
]
ListDoseResponseByRunDep = Annotated[
    ListDoseResponseByRun, Depends(_get_use_case(ListDoseResponseByRun))
]
RefitDoseResponseCurveDep = Annotated[
    RefitDoseResponseCurve, Depends(_get_use_case(RefitDoseResponseCurve))
]
RefitDoseResponseCurvePreviewDep = Annotated[
    RefitDoseResponseCurvePreview,
    Depends(_get_use_case(RefitDoseResponseCurvePreview)),
]
ClassifyDoseResponseCurveDep = Annotated[
    ClassifyDoseResponseCurve, Depends(_get_use_case(ClassifyDoseResponseCurve))
]
GetCurveEditHistoryDep = Annotated[
    GetCurveEditHistory, Depends(_get_use_case(GetCurveEditHistory))
]
MoleculeActivityServiceDep = Annotated[
    MoleculeActivityService, Depends(_get_use_case(MoleculeActivityService))
]
GetMoleculeActivityDetailDep = Annotated[
    GetMoleculeActivityDetail, Depends(_get_use_case(GetMoleculeActivityDetail))
]
GetMoleculeTestCountsDep = Annotated[
    GetMoleculeTestCounts, Depends(_get_use_case(GetMoleculeTestCounts))
]
ReadoutCalculationEngineDep = Annotated[
    ReadoutCalculationEngine, Depends(_get_use_case(ReadoutCalculationEngine))
]
FitDoseResponseCurvesDep = Annotated[
    FitDoseResponseCurves, Depends(_get_use_case(FitDoseResponseCurves))
]
GetProtocolStatsDep = Annotated[GetProtocolStats, Depends(_get_use_case(GetProtocolStats))]
GetProtocolActivitySummaryDep = Annotated[
    GetProtocolActivitySummary, Depends(_get_use_case(GetProtocolActivitySummary))
]
GetCompoundCurvesDep = Annotated[GetCompoundCurves, Depends(_get_use_case(GetCompoundCurves))]
ListRunsWithCountsDep = Annotated[ListRunsWithCounts, Depends(_get_use_case(ListRunsWithCounts))]
ListReadoutDataEnrichedDep = Annotated[
    ListReadoutDataEnriched, Depends(_get_use_case(ListReadoutDataEnriched))
]
ListDoseResponseEnrichedDep = Annotated[
    ListDoseResponseEnriched, Depends(_get_use_case(ListDoseResponseEnriched))
]
GetPlateMapDep = Annotated[GetPlateMap, Depends(_get_use_case(GetPlateMap))]

# --- Compound Flag dependencies ---
ListCompoundFlagsDep = Annotated[ListCompoundFlags, Depends(_get_use_case(ListCompoundFlags))]
CreateCompoundFlagDep = Annotated[CreateCompoundFlag, Depends(_get_use_case(CreateCompoundFlag))]
DeleteCompoundFlagDep = Annotated[DeleteCompoundFlag, Depends(_get_use_case(DeleteCompoundFlag))]

# --- Plate Template dependencies ---
CreatePlateTemplateDep = Annotated[
    CreatePlateTemplate, Depends(_get_use_case(CreatePlateTemplate))
]
UpdatePlateTemplateDep = Annotated[
    UpdatePlateTemplate, Depends(_get_use_case(UpdatePlateTemplate))
]
DeletePlateTemplateDep = Annotated[
    DeletePlateTemplate, Depends(_get_use_case(DeletePlateTemplate))
]
GetPlateTemplateDep = Annotated[GetPlateTemplate, Depends(_get_use_case(GetPlateTemplate))]
ListPlateTemplatesDep = Annotated[ListPlateTemplates, Depends(_get_use_case(ListPlateTemplates))]

# --- Plate setup + readout import dependencies ---
ParsePlateMapFileDep = Annotated[ParsePlateMapFile, Depends(_get_use_case(ParsePlateMapFile))]
SetUpRunPlateDep = Annotated[SetUpRunPlate, Depends(_get_use_case(SetUpRunPlate))]
ImportRunReadoutsDep = Annotated[ImportRunReadouts, Depends(_get_use_case(ImportRunReadouts))]
PreviewSummaryFileDep = Annotated[PreviewSummaryFile, Depends(_get_use_case(PreviewSummaryFile))]
PreviewSummaryImportDep = Annotated[
    PreviewSummaryImport, Depends(_get_use_case(PreviewSummaryImport))
]
ImportSummaryFileDep = Annotated[ImportSummaryFile, Depends(_get_use_case(ImportSummaryFile))]
