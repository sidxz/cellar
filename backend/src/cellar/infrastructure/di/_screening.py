"""Screening & assay bindings: protocols, targets, runs, readout data, dose response,
plate templates, registered plates, read models, molecule activity, computation
primitives, plate map, fit curves, ontology search/annotations, import run readouts.
"""

from __future__ import annotations

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.admin.admin_delete_registry import register_admin_delete
from cellar.application.attachment.upload_attachment import UploadAttachment
from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.application.inventory.ensure_batch_exists import EnsureBatchExists
from cellar.application.inventory.export_plate_layout import ExportPlateLayout
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
from cellar.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from cellar.application.screening.classify_dose_response import ClassifyDoseResponseCurve
from cellar.application.screening.compound_curves_reader import CompoundCurvesReader
from cellar.application.screening.condition_grouping_service import ConditionGroupingService
from cellar.application.screening.create_compound_flag import CreateCompoundFlag
from cellar.application.screening.create_dose_response import CreateDoseResponseCurve
from cellar.application.screening.create_protocol import CreateProtocol
from cellar.application.screening.create_readout_data import CreateReadoutData
from cellar.application.screening.create_run import CreateRun
from cellar.application.screening.create_target import CreateTarget
from cellar.application.screening.cross_protocol_resolver import CrossProtocolResolver
from cellar.application.screening.delete_compound_flag import DeleteCompoundFlag
from cellar.application.screening.delete_run import DeleteRun
from cellar.application.screening.delete_target import DeleteTarget
from cellar.application.screening.dose_response_enriched_reader import (
    DoseResponseEnrichedReader,
)
from cellar.application.screening.fit_dose_response import FitDoseResponseCurves
from cellar.application.screening.get_collection_gap import (
    GetProtocolCollectionGap,
    GetRunCollectionGap,
)
from cellar.application.screening.get_compound_curves import GetCompoundCurves
from cellar.application.screening.get_curve_edit_history import GetCurveEditHistory
from cellar.application.screening.get_dose_response import ListDoseResponseByRun
from cellar.application.screening.get_dose_response_curves_batch import (
    GetDoseResponseCurvesBatch,
)
from cellar.application.screening.get_molecule_activity_detail import GetMoleculeActivityDetail
from cellar.application.screening.get_molecule_test_counts import GetMoleculeTestCounts
from cellar.application.screening.get_plate_map import GetPlateMap
from cellar.application.screening.find_similar_protocols import FindSimilarProtocols
from cellar.application.screening.get_protocol import GetProtocol, ListProtocols
from cellar.application.screening.get_protocol_activity import GetProtocolActivitySummary
from cellar.application.screening.get_protocol_stats import GetProtocolStats
from cellar.application.screening.get_readout_data import ListReadoutDataByRun
from cellar.application.screening.get_run import GetRun, ListRunsByProtocol
from cellar.application.screening.get_target import GetTarget, ListTargets
from cellar.application.screening.import_run_file import (
    ImportRunFile,
    InMemoryPreviewStore,
    PreviewRunFile,
    RepreviewRunFile,
)
from cellar.application.screening.import_run_readouts import ImportRunReadouts
from cellar.application.screening.import_summary_file import ImportSummaryFile
from cellar.application.screening.list_compound_flags import ListCompoundFlags
from cellar.application.screening.list_dose_response_enriched import ListDoseResponseEnriched
from cellar.application.screening.list_protocol_summaries import ListProtocolSummaries
from cellar.application.screening.list_readout_data_enriched import ListReadoutDataEnriched
from cellar.application.screening.list_runs_with_counts import ListRunsWithCounts
from cellar.application.screening.lock_protocol import (
    LockProtocol,
    UnlockProtocol,
)
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
from cellar.application.screening.manage_ontology_annotations import (
    RemoveOntologyAnnotation,
    SetOntologyAnnotation,
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
from cellar.application.screening.plate_map_reader import PlateMapReader
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
from cellar.application.screening.protocol_activity_reader import ProtocolActivityReader
from cellar.application.screening.protocol_stats_reader import ProtocolStatsReader
from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.application.screening.readout_data_enriched_reader import ReadoutDataEnrichedReader
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
from cellar.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    DeleteRunImportTemplate,
    ListRunImportTemplates,
    UpdateRunImportTemplate,
)
from cellar.application.screening.search_ontology import SearchOntology
from cellar.application.screening.set_run_hit_criteria import (
    ResetRunHitCriteria,
    SetRunHitCriteria,
)
from cellar.application.screening.update_run import UpdateRun
from cellar.application.screening.update_target import UpdateTarget
from cellar.application.shared.molecule_resolver import MoleculeResolver
from cellar.application.shared.parsers import TabularParser
from cellar.domain.audit_compliance.repository import AuditRepository
from cellar.domain.screening_assay.curve_fitting import CurveFittingService
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
from cellar.domain.screening_assay.formula_evaluator import FormulaEvaluator
from cellar.domain.screening_assay.plate_normalizer import PlateNormalizer
from cellar.domain.screening_assay.plate_quality import PlateQualityCalculator
from cellar.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator
from cellar.infrastructure.external.bioportal.client import BioPortalClient
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.parsers.tabular_file import TabularFileParser
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_read_model_reader import (
    SQLAlchemyPlateReadModelService,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.compound_curves_reader import (
    SQLAlchemyCompoundCurvesReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_repository import (
    SQLAlchemyCompoundFlagRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.coverage_query import (
    SQLAlchemyCollectionCoverageQuery,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_enriched_reader import (  # noqa: E501
    SQLAlchemyDoseResponseEnrichedReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.plate_map_reader import (
    SQLAlchemyPlateMapReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.plate_template_repository import (  # noqa: E501
    SQLAlchemyPlateTemplateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_activity_reader import (
    SQLAlchemyProtocolActivityReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_stats_reader import (
    SQLAlchemyProtocolStatsReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_enriched_reader import (  # noqa: E501
    SQLAlchemyReadoutDataEnrichedReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_import_template_repository import (  # noqa: E501
    SQLAlchemyRunImportTemplateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.target_repository import (
    SQLAlchemyTargetRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_screening(container: Container) -> None:
    # Force cascade rules to register at DI bootstrap.
    import cellar.infrastructure.cascade.rules_screening_assay  # noqa: F401

    # --- Protocol use cases ---
    def _protocol_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

        return _f

    def _protocol_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolRepository(uow))

        return _f

    def _find_similar_protocols(c: Container) -> FindSimilarProtocols:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FindSimilarProtocols(uow, SQLAlchemyProtocolRepository(uow))

    container.define(CreateProtocol, _protocol_cmd(CreateProtocol))
    container.define(GetProtocol, _protocol_query(GetProtocol))
    container.define(ListProtocols, _protocol_query(ListProtocols))
    container.define(FindSimilarProtocols, _find_similar_protocols)
    container.define(PublishProtocol, _protocol_cmd(PublishProtocol))
    container.define(RetireProtocol, _protocol_cmd(RetireProtocol))
    container.define(LockProtocol, _protocol_cmd(LockProtocol))
    container.define(UnlockProtocol, _protocol_cmd(UnlockProtocol))
    container.define(VersionProtocol, _protocol_cmd(VersionProtocol))
    container.define(UpdateProtocol, _protocol_cmd(UpdateProtocol))
    container.define(DeleteProtocol, _protocol_cmd(DeleteProtocol))
    container.define(ListProtocolsByProject, _protocol_query(ListProtocolsByProject))

    def _list_protocol_summaries(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListProtocolSummaries(
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
        )

    container.define(ListProtocolSummaries, _list_protocol_summaries)
    container.define(AddProtocolToProject, _protocol_cmd(AddProtocolToProject))
    container.define(RemoveProtocolFromProject, _protocol_cmd(RemoveProtocolFromProject))
    container.define(AddProtocolTarget, _protocol_cmd(AddProtocolTarget))
    container.define(RemoveProtocolTarget, _protocol_cmd(RemoveProtocolTarget))
    container.define(GetProtocolTargets, _protocol_query(GetProtocolTargets))
    container.define(ResolveProtocolTargets, _protocol_query(ResolveProtocolTargets))

    def _resolve_run_targets(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ResolveRunTargets(uow, SQLAlchemyRunRepository(uow))

    container.define(ResolveRunTargets, _resolve_run_targets)

    # --- Computation Primitives ---
    container.define(AstevalFormulaEvaluator, Singleton(AstevalFormulaEvaluator))
    container.define(FormulaEvaluator, lambda c: c[AstevalFormulaEvaluator])
    container.define(PlateNormalizer, Singleton(PlateNormalizer))
    container.define(ReplicateAggregator, Singleton(ReplicateAggregator))
    container.define(PlateQualityCalculator, Singleton(PlateQualityCalculator))
    container.define(TabularFileParser, Singleton(TabularFileParser))
    container.define(TabularParser, lambda c: c[TabularFileParser])
    container.define(ParsePlateMapFile, lambda c: ParsePlateMapFile(c[TabularParser]))

    def _add_readout_def(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddReadoutDefinition(
            uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher], c[FormulaEvaluator]
        )

    container.define(AddReadoutDefinition, _add_readout_def)
    container.define(RemoveReadoutDefinition, _protocol_cmd(RemoveReadoutDefinition))

    def _update_readout_def(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdateReadoutDefinition(
            uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher], c[FormulaEvaluator]
        )

    container.define(UpdateReadoutDefinition, _update_readout_def)

    container.define(AddConditionDefinition, _protocol_cmd(AddConditionDefinition))
    container.define(RemoveConditionDefinition, _protocol_cmd(RemoveConditionDefinition))
    container.define(UpdateConditionDefinition, _protocol_cmd(UpdateConditionDefinition))

    def _set_control_layout(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetControlLayout(
            uow,
            SQLAlchemyProtocolRepository(uow),
            c[EventDispatcher],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(SetControlLayout, _set_control_layout)
    container.define(RemoveControlLayout, _protocol_cmd(RemoveControlLayout))

    # --- Targets ---
    def _target_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTargetRepository(uow), c[EventDispatcher])

        return _f

    def _target_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTargetRepository(uow))

        return _f

    container.define(CreateTarget, _target_cmd(CreateTarget))
    container.define(UpdateTarget, _target_cmd(UpdateTarget))
    container.define(DeleteTarget, _target_cmd(DeleteTarget))
    container.define(GetTarget, _target_query(GetTarget))
    container.define(ListTargets, _target_query(ListTargets))

    # --- Compound Flags ---
    def _compound_flag_uc(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyCompoundFlagRepository(uow))

        return _f

    container.define(ListCompoundFlags, _compound_flag_uc(ListCompoundFlags))
    container.define(CreateCompoundFlag, _compound_flag_uc(CreateCompoundFlag))
    container.define(DeleteCompoundFlag, _compound_flag_uc(DeleteCompoundFlag))

    # --- Runs ---
    def _run_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunRepository(uow), c[EventDispatcher])

        return _f

    def _run_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunRepository(uow))

        return _f

    def _create_run(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateRun(
            uow,
            SQLAlchemyRunRepository(uow),
            SQLAlchemyProtocolRepository(uow),
            c[EventDispatcher],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(CreateRun, _create_run)

    def _delete_run(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteRun(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(DeleteRun, _delete_run)

    def _reset_run_data(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ResetRunData(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(ResetRunData, _reset_run_data)

    container.define(GetRun, _run_query(GetRun))
    container.define(ListRunsByProtocol, _run_query(ListRunsByProtocol))
    container.define(StartRun, _run_cmd(StartRun))
    container.define(CompleteRun, _run_cmd(CompleteRun))
    container.define(ApproveRun, _run_cmd(ApproveRun))
    container.define(RejectRun, _run_cmd(RejectRun))
    container.define(UpdateRun, _run_cmd(UpdateRun))
    container.define(LockRun, _run_cmd(LockRun))
    container.define(UnlockRun, _run_cmd(UnlockRun))
    container.define(SetRunHitCriteria, _run_cmd(SetRunHitCriteria))
    container.define(ResetRunHitCriteria, _run_cmd(ResetRunHitCriteria))
    container.define(AddRunTarget, _run_cmd(AddRunTarget))
    container.define(RemoveRunTarget, _run_cmd(RemoveRunTarget))
    container.define(AddRunCollection, _run_cmd(AddRunCollection))
    container.define(RemoveRunCollection, _run_cmd(RemoveRunCollection))

    def _resolve_run_collections(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ResolveRunCollections(uow, SQLAlchemyCollectionCoverageQuery(uow))

    container.define(ResolveRunCollections, _resolve_run_collections)

    def _protocol_collection_coverage(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetProtocolCollectionCoverage(
            uow, SQLAlchemyProtocolRepository(uow), SQLAlchemyCollectionCoverageQuery(uow)
        )

    container.define(GetProtocolCollectionCoverage, _protocol_collection_coverage)

    def _run_collection_gap(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetRunCollectionGap(
            uow, SQLAlchemyRunRepository(uow), SQLAlchemyCollectionCoverageQuery(uow)
        )

    container.define(GetRunCollectionGap, _run_collection_gap)

    def _protocol_collection_gap(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetProtocolCollectionGap(
            uow, SQLAlchemyProtocolRepository(uow), SQLAlchemyCollectionCoverageQuery(uow)
        )

    container.define(GetProtocolCollectionGap, _protocol_collection_gap)

    def _list_runs_with_counts(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRunsWithCounts(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            coverage_reader=SQLAlchemyCollectionCoverageQuery(uow),
        )

    container.define(ListRunsWithCounts, _list_runs_with_counts)

    # --- Readout Data ---
    def _readout_create(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return CreateReadoutData(
            uow, SQLAlchemyReadoutDataRepository(uow), guard, c[EventDispatcher], run_repo=run_repo
        )

    def _readout_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyReadoutDataRepository(uow))

        return _f

    def _readout_bulk_create(c: Container):
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

    container.define(
        ReadoutDataEnrichedReader,
        lambda c: SQLAlchemyReadoutDataEnrichedReader(c[async_sessionmaker]),
    )

    def _readout_enriched(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListReadoutDataEnriched(
            uow, SQLAlchemyReadoutDataRepository(uow), c[ReadoutDataEnrichedReader]
        )

    container.define(ListReadoutDataEnriched, _readout_enriched)

    # --- Dose Response ---
    def _dose_response_create(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return CreateDoseResponseCurve(
            uow,
            SQLAlchemyDoseResponseCurveRepository(uow),
            guard,
            c[EventDispatcher],
            run_repo=run_repo,
        )

    def _dose_response_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyDoseResponseCurveRepository(uow))

        return _f

    container.define(CreateDoseResponseCurve, _dose_response_create)
    container.define(ListDoseResponseByRun, _dose_response_query(ListDoseResponseByRun))
    container.define(GetDoseResponseCurvesBatch, _dose_response_query(GetDoseResponseCurvesBatch))

    container.define(
        DoseResponseEnrichedReader,
        lambda c: SQLAlchemyDoseResponseEnrichedReader(c[async_sessionmaker]),
    )

    def _dose_response_enriched(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDoseResponseEnriched(
            uow,
            SQLAlchemyDoseResponseCurveRepository(uow),
            c[DoseResponseEnrichedReader],
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(ListDoseResponseEnriched, _dose_response_enriched)

    def _fit_dose_response_curves(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FitDoseResponseCurves(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            curve_fitter=c[CurveFittingService],
        )

    container.define(FitDoseResponseCurves, _fit_dose_response_curves)

    def _refit_dose_response_curve(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        return RefitDoseResponseCurve(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            curve_fitter=c[CurveFittingService],
            guard=DataLockGuard(run_repo),
            audit=c[AuditRecordingService],
        )

    container.define(RefitDoseResponseCurve, _refit_dose_response_curve)

    def _refit_dose_response_curve_preview(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RefitDoseResponseCurvePreview(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            curve_fitter=c[CurveFittingService],
        )

    container.define(RefitDoseResponseCurvePreview, _refit_dose_response_curve_preview)

    def _classify_dose_response_curve(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ClassifyDoseResponseCurve(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        )

    container.define(ClassifyDoseResponseCurve, _classify_dose_response_curve)

    def _get_curve_edit_history(c: Container):
        return GetCurveEditHistory(audit_repository=c[AuditRepository])

    container.define(GetCurveEditHistory, _get_curve_edit_history)

    # --- Plate Map + Fit Curves for Run ---
    container.define(
        PlateMapReader,
        lambda c: SQLAlchemyPlateMapReader(c[async_sessionmaker]),
    )

    def _get_plate_map(c: Container):
        return GetPlateMap(reader=c[PlateMapReader])

    container.define(GetPlateMap, _get_plate_map)

    # --- Plate Templates ---
    def _pt_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyPlateTemplateRepository(uow), c[EventDispatcher])

        return _f

    def _pt_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyPlateTemplateRepository(uow))

        return _f

    container.define(CreatePlateTemplate, _pt_cmd(CreatePlateTemplate))
    container.define(UpdatePlateTemplate, _pt_cmd(UpdatePlateTemplate))
    container.define(DeletePlateTemplate, _pt_cmd(DeletePlateTemplate))
    container.define(GetPlateTemplate, _pt_query(GetPlateTemplate))
    container.define(ListPlateTemplates, _pt_query(ListPlateTemplates))

    # --- Readout Calculation Engine + Plate Setup ---
    def _readout_calc_engine(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ReadoutCalculationEngine(
            uow=uow,
            formula_evaluator=c[FormulaEvaluator],
            plate_normalizer=c[PlateNormalizer],
            replicate_aggregator=c[ReplicateAggregator],
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            dispatcher=c[EventDispatcher],
            fit_dose_response=c[FitDoseResponseCurves],
            plate_quality=c[PlateQualityCalculator],
        )

    container.define(ReadoutCalculationEngine, _readout_calc_engine)

    def _set_up_run_plate(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        resolver = MoleculeResolver(
            SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol]
        )
        return SetUpRunPlate(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            molecule_resolver=resolver,
            dispatcher=c[EventDispatcher],
        )

    container.define(SetUpRunPlate, _set_up_run_plate)

    def _import_run_readouts(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportRunReadouts(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            parser=c[TabularParser],
        )

    container.define(ImportRunReadouts, _import_run_readouts)

    # --- Run-file import (long format) ---
    container[InMemoryPreviewStore] = Singleton(lambda: InMemoryPreviewStore())

    def _preview_run_file(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return PreviewRunFile(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            preview_store=c[InMemoryPreviewStore],
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
            parser=c[TabularParser],
            ensure_batch_exists=c[EnsureBatchExists],
        )

    container.define(PreviewRunFile, _preview_run_file)

    def _repreview_run_file(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RepreviewRunFile(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            preview_store=c[InMemoryPreviewStore],
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(RepreviewRunFile, _repreview_run_file)

    def _import_run_file(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportRunFile(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            preview_store=c[InMemoryPreviewStore],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
            upload_attachment=c[UploadAttachment],
            dispatcher=c[EventDispatcher],
            calculation_engine=c[ReadoutCalculationEngine],
            ensure_batch_exists=c[EnsureBatchExists],
        )

    container.define(ImportRunFile, _import_run_file)

    # --- Summary-file import (wide format) ---
    def _preview_summary_file(c: Container):
        # The use case owns + enters this read UoW (mirrors PreviewRunFile),
        # giving its repos an active session for the request.
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return PreviewSummaryFile(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            parser=c[TabularParser],
        )

    container.define(PreviewSummaryFile, _preview_summary_file)

    def _import_summary_file(c: Container):
        # The use case owns + enters this read UoW for run/protocol/snapshot
        # reads; ``bulk_uc`` resolves its own write UoW (it commits + closes its
        # session), so they are NOT shared.
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ImportSummaryFile(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            parser=c[TabularParser],
            bulk_uc=c[BulkCreateReadoutData],
        )

    container.define(ImportSummaryFile, _import_summary_file)

    def _preview_summary_import(c: Container):
        # Dry-run forecast: owns + enters its own read UoW (no bulk_uc, no
        # writes). Mirrors ``_import_summary_file`` minus the bulk write path.
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return PreviewSummaryImport(
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            parser=c[TabularParser],
            uow=uow,
        )

    container.define(PreviewSummaryImport, _preview_summary_import)

    # --- Run import templates (CRUD) ---
    def _run_import_template_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunImportTemplateRepository(uow), c[EventDispatcher])

        return _f

    def _list_run_import_templates(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRunImportTemplates(uow, SQLAlchemyRunImportTemplateRepository(uow))

    container.define(CreateRunImportTemplate, _run_import_template_cmd(CreateRunImportTemplate))
    container.define(UpdateRunImportTemplate, _run_import_template_cmd(UpdateRunImportTemplate))
    container.define(DeleteRunImportTemplate, _run_import_template_cmd(DeleteRunImportTemplate))
    container.define(ListRunImportTemplates, _list_run_import_templates)

    def _cross_protocol_resolver(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CrossProtocolResolver(
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
        )

    container.define(CrossProtocolResolver, _cross_protocol_resolver)

    def _condition_grouping_service(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ConditionGroupingService(
            uow=uow,
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(ConditionGroupingService, _condition_grouping_service)

    # --- Registered Plates ---
    def _reg_plate_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegisteredPlateRepository(uow), c[EventDispatcher])

        return _f

    def _reg_plate_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegisteredPlateRepository(uow))

        return _f

    def _map_wells(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MapWells(
            uow,
            SQLAlchemyRegisteredPlateRepository(uow),
            SQLAlchemyBatchRepository(uow),
            c[EventDispatcher],
        )

    container.define(RegisterPlate, _reg_plate_cmd(RegisterPlate))
    container.define(UpdatePlate, _reg_plate_cmd(UpdatePlate))
    container.define(MapWells, _map_wells)
    container.define(ChangeStatus, _reg_plate_cmd(ChangeStatus))
    container.define(DerivePlate, _reg_plate_cmd(DerivePlate))
    container.define(GetPlate, _reg_plate_query(GetPlate))
    container.define(ListPlates, _reg_plate_query(ListPlates))
    container.define(ListChildren, _reg_plate_query(ListChildren))

    def _export_plate_layout(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ExportPlateLayout(
            uow,
            SQLAlchemyRegisteredPlateRepository(uow),
            SQLAlchemyBatchRepository(uow),
        )

    container.define(ExportPlateLayout, _export_plate_layout)

    def _delete_reg_plate(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeletePlate(uow, SQLAlchemyRegisteredPlateRepository(uow), c[EventDispatcher])

    container.define(DeletePlate, _delete_reg_plate)

    # --- Plate Read Model ---
    container.define(
        PlateReadModelService,
        lambda c: SQLAlchemyPlateReadModelService(c[async_sessionmaker]),
    )

    # --- Screening Read Models ---
    container.define(
        ProtocolActivityReader,
        lambda c: SQLAlchemyProtocolActivityReader(c[async_sessionmaker]),
    )
    container.define(
        GetProtocolActivitySummary,
        lambda c: GetProtocolActivitySummary(reader=c[ProtocolActivityReader]),
    )

    container.define(
        CompoundCurvesReader,
        lambda c: SQLAlchemyCompoundCurvesReader(c[async_sessionmaker]),
    )

    def _get_compound_curves(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetCompoundCurves(
            reader=c[CompoundCurvesReader],
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(GetCompoundCurves, _get_compound_curves)

    container.define(
        ProtocolStatsReader,
        lambda c: SQLAlchemyProtocolStatsReader(c[async_sessionmaker]),
    )
    container.define(
        GetProtocolStats,
        lambda c: GetProtocolStats(reader=c[ProtocolStatsReader]),
    )

    # --- Molecule Activity Service ---
    def _molecule_activity_service(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MoleculeActivityService(
            uow=uow,
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
        )

    container.define(MoleculeActivityService, _molecule_activity_service)

    def _get_molecule_activity_detail(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetMoleculeActivityDetail(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
        )

    container.define(GetMoleculeActivityDetail, _get_molecule_activity_detail)

    def _get_molecule_test_counts(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetMoleculeTestCounts(
            uow=uow,
            dr_curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        )

    container.define(GetMoleculeTestCounts, _get_molecule_test_counts)

    # --- Ontology Search & Annotations ---
    container.define(BioPortalClient, lambda c: BioPortalClient(c[SecretProvider]))
    container.define(SearchOntology, lambda c: SearchOntology(c[BioPortalClient]))

    def _set_ontology_annotation(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetOntologyAnnotation(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

    def _remove_ontology_annotation(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveOntologyAnnotation(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

    container.define(SetOntologyAnnotation, _set_ontology_annotation)
    container.define(RemoveOntologyAnnotation, _remove_ontology_annotation)

    # --- Admin Hard-Delete Registry (Tier 1) ---
    register_admin_delete(
        entity_type="protocol",
        table="protocols",
        label_field="name",
    )
    register_admin_delete(
        entity_type="run",
        table="runs",
        label_field="notes",
    )
    register_admin_delete(
        entity_type="plate_template",
        table="plate_templates",
        label_field="name",
    )
    register_admin_delete(
        entity_type="run_import_template",
        table="run_import_templates",
        label_field="name",
    )


def build_screening_admin_repos(uow) -> dict:
    """Build the repo map for screening Tier-1 admin deletes."""
    from cellar.application.admin._adapter import RepoAdapter

    return {
        "protocol": RepoAdapter(SQLAlchemyProtocolRepository(uow), find="find_by_id_in_workspace"),
        "run": RepoAdapter(SQLAlchemyRunRepository(uow), find="find_by_id_in_workspace"),
        "plate_template": RepoAdapter(
            SQLAlchemyPlateTemplateRepository(uow), find="find_by_id_in_workspace"
        ),
        "run_import_template": RepoAdapter(
            SQLAlchemyRunImportTemplateRepository(uow), find="find_by_id_in_workspace"
        ),
    }
