"""Screening & assay bindings: protocols, targets, runs, readout data, dose response,
plate templates, registered plates, read models, molecule activity, computation
primitives, plate map, fit curves, ontology search/annotations, import run readouts.
"""

from __future__ import annotations

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.attachment.upload_attachment import UploadAttachment
from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.inventory.plate_read_model import PlateReadModelService
from chem_vault.application.inventory.registered_plates import (
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
from chem_vault.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from chem_vault.application.screening.classify_dose_response import ClassifyDoseResponseCurve
from chem_vault.application.screening.compound_curves_reader import CompoundCurvesReader
from chem_vault.application.screening.condition_grouping_service import ConditionGroupingService
from chem_vault.application.screening.create_compound_flag import CreateCompoundFlag
from chem_vault.application.screening.create_dose_response import CreateDoseResponseCurve
from chem_vault.application.screening.create_protocol import CreateProtocol
from chem_vault.application.screening.create_readout_data import CreateReadoutData
from chem_vault.application.screening.create_run import CreateRun
from chem_vault.application.screening.delete_run import DeleteRun
from chem_vault.application.screening.reset_run_data import ResetRunData
from chem_vault.application.screening.create_target import CreateTarget
from chem_vault.application.screening.cross_protocol_resolver import CrossProtocolResolver
from chem_vault.application.screening.delete_compound_flag import DeleteCompoundFlag
from chem_vault.application.screening.delete_target import DeleteTarget
from chem_vault.application.screening.dose_response_enriched_reader import (
    DoseResponseEnrichedReader,
)
from chem_vault.application.screening.fit_dose_response import FitDoseResponseCurves
from chem_vault.application.screening.get_compound_curves import GetCompoundCurves
from chem_vault.application.screening.get_dose_response import ListDoseResponseByRun
from chem_vault.application.screening.get_molecule_activity_detail import GetMoleculeActivityDetail
from chem_vault.application.screening.get_plate_map import GetPlateMap
from chem_vault.application.screening.get_protocol import GetProtocol, ListProtocols
from chem_vault.application.screening.get_protocol_activity import GetProtocolActivitySummary
from chem_vault.application.screening.get_protocol_stats import GetProtocolStats
from chem_vault.application.screening.get_readout_data import ListReadoutDataByRun
from chem_vault.application.screening.get_run import GetRun, ListRunsByProtocol
from chem_vault.application.screening.get_target import GetTarget, ListTargets
from chem_vault.application.screening.import_run_file import (
    ImportRunFile,
    InMemoryPreviewStore,
    PreviewRunFile,
)
from chem_vault.application.screening.import_run_readouts import ImportRunReadouts
from chem_vault.application.screening.list_compound_flags import ListCompoundFlags
from chem_vault.application.screening.list_dose_response_enriched import ListDoseResponseEnriched
from chem_vault.application.screening.list_readout_data_enriched import ListReadoutDataEnriched
from chem_vault.application.screening.list_runs_with_counts import ListRunsWithCounts
from chem_vault.application.screening.lock_run import LockRun, UnlockRun
from chem_vault.application.screening.manage_condition_definitions import (
    AddConditionDefinition,
    RemoveConditionDefinition,
    UpdateConditionDefinition,
)
from chem_vault.application.screening.manage_control_layouts import (
    RemoveControlLayout,
    SetControlLayout,
)
from chem_vault.application.screening.manage_ontology_annotations import (
    RemoveOntologyAnnotation,
    SetOntologyAnnotation,
)
from chem_vault.application.screening.lock_protocol import (
    LockProtocol,
    UnlockProtocol,
)
from chem_vault.application.screening.manage_protocol import (
    AddProtocolToProject,
    DeleteProtocol,
    ListProtocolsByProject,
    PublishProtocol,
    RemoveProtocolFromProject,
    RetireProtocol,
    UpdateProtocol,
    VersionProtocol,
)
from chem_vault.application.screening.manage_readout_definitions import (
    AddReadoutDefinition,
    RemoveReadoutDefinition,
    UpdateReadoutDefinition,
)
from chem_vault.application.screening.manage_run import (
    ApproveRun,
    CompleteRun,
    RejectRun,
    StartRun,
)
from chem_vault.application.screening.molecule_activity_service import MoleculeActivityService
from chem_vault.application.screening.plate_map_reader import PlateMapReader
from chem_vault.application.screening.plate_setup import ParsePlateMapFile, SetUpRunPlate
from chem_vault.application.screening.plate_templates import (
    CreatePlateTemplate,
    DeletePlateTemplate,
    GetPlateTemplate,
    ListPlateTemplates,
    UpdatePlateTemplate,
)
from chem_vault.application.screening.protocol_activity_reader import ProtocolActivityReader
from chem_vault.application.screening.protocol_stats_reader import ProtocolStatsReader
from chem_vault.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from chem_vault.application.screening.readout_data_enriched_reader import ReadoutDataEnrichedReader
from chem_vault.application.screening.refit_dose_response import RefitDoseResponseCurve
from chem_vault.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    DeleteRunImportTemplate,
    ListRunImportTemplates,
    UpdateRunImportTemplate,
)
from chem_vault.application.screening.search_ontology import SearchOntology
from chem_vault.application.screening.update_run import UpdateRun
from chem_vault.application.screening.update_target import UpdateTarget
from chem_vault.application.shared.molecule_resolver import MoleculeResolver
from chem_vault.application.shared.parsers import TabularParser
from chem_vault.domain.screening_assay.curve_fitting import CurveFittingService
from chem_vault.domain.screening_assay.data_lock_guard import DataLockGuard
from chem_vault.domain.screening_assay.formula_evaluator import FormulaEvaluator
from chem_vault.domain.screening_assay.plate_normalizer import PlateNormalizer
from chem_vault.domain.screening_assay.plate_quality import PlateQualityCalculator
from chem_vault.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator
from chem_vault.infrastructure.parsers.tabular_file import TabularFileParser
from chem_vault.infrastructure.external.bioportal.client import BioPortalClient
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.plate_read_model_reader import (
    SQLAlchemyPlateReadModelService,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_curves_reader import (
    SQLAlchemyCompoundCurvesReader,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_repository import (
    SQLAlchemyCompoundFlagRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_enriched_reader import (
    SQLAlchemyDoseResponseEnrichedReader,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.plate_map_reader import (
    SQLAlchemyPlateMapReader,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.plate_template_repository import (
    SQLAlchemyPlateTemplateRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_activity_reader import (
    SQLAlchemyProtocolActivityReader,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_stats_reader import (
    SQLAlchemyProtocolStatsReader,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_enriched_reader import (
    SQLAlchemyReadoutDataEnrichedReader,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.run_import_template_repository import (
    SQLAlchemyRunImportTemplateRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.target_repository import (
    SQLAlchemyTargetRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_screening(container: Container) -> None:
    # --- Protocol use cases ---
    def _protocol_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])
        return _f

    def _protocol_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolRepository(uow))
        return _f

    container.define(CreateProtocol, _protocol_cmd(CreateProtocol))
    container.define(GetProtocol, _protocol_query(GetProtocol))
    container.define(ListProtocols, _protocol_query(ListProtocols))
    container.define(PublishProtocol, _protocol_cmd(PublishProtocol))
    container.define(RetireProtocol, _protocol_cmd(RetireProtocol))
    container.define(LockProtocol, _protocol_cmd(LockProtocol))
    container.define(UnlockProtocol, _protocol_cmd(UnlockProtocol))
    container.define(VersionProtocol, _protocol_cmd(VersionProtocol))
    container.define(UpdateProtocol, _protocol_cmd(UpdateProtocol))
    container.define(DeleteProtocol, _protocol_cmd(DeleteProtocol))
    container.define(ListProtocolsByProject, _protocol_query(ListProtocolsByProject))
    container.define(AddProtocolToProject, _protocol_cmd(AddProtocolToProject))
    container.define(RemoveProtocolFromProject, _protocol_cmd(RemoveProtocolFromProject))

    # --- Computation Primitives ---
    container.define(AstevalFormulaEvaluator, Singleton(AstevalFormulaEvaluator))
    container.define(FormulaEvaluator, lambda c: c[AstevalFormulaEvaluator])
    container.define(PlateNormalizer, Singleton(PlateNormalizer))
    container.define(ReplicateAggregator, Singleton(ReplicateAggregator))
    container.define(PlateQualityCalculator, Singleton(PlateQualityCalculator))
    container.define(TabularFileParser, Singleton(TabularFileParser))
    container.define(TabularParser, lambda c: c[TabularFileParser])
    container.define(ParsePlateMapFile, lambda c: ParsePlateMapFile(c[TabularParser]))

    def _add_readout_def(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddReadoutDefinition(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher], c[FormulaEvaluator])

    container.define(AddReadoutDefinition, _add_readout_def)
    container.define(RemoveReadoutDefinition, _protocol_cmd(RemoveReadoutDefinition))

    def _update_readout_def(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdateReadoutDefinition(
            uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher], c[FormulaEvaluator]
        )

    container.define(UpdateReadoutDefinition, _update_readout_def)

    container.define(AddConditionDefinition, _protocol_cmd(AddConditionDefinition))
    container.define(RemoveConditionDefinition, _protocol_cmd(RemoveConditionDefinition))
    container.define(UpdateConditionDefinition, _protocol_cmd(UpdateConditionDefinition))

    def _set_control_layout(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetControlLayout(
            uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(SetControlLayout, _set_control_layout)
    container.define(RemoveControlLayout, _protocol_cmd(RemoveControlLayout))

    # --- Targets ---
    def _target_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTargetRepository(uow), c[EventDispatcher])
        return _f

    def _target_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTargetRepository(uow))
        return _f

    container.define(CreateTarget, _target_cmd(CreateTarget))
    container.define(UpdateTarget, _target_cmd(UpdateTarget))
    container.define(DeleteTarget, _target_cmd(DeleteTarget))
    container.define(GetTarget, _target_query(GetTarget))
    container.define(ListTargets, _target_query(ListTargets))

    # --- Compound Flags ---
    def _compound_flag_uc(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyCompoundFlagRepository(uow))
        return _f

    container.define(ListCompoundFlags, _compound_flag_uc(ListCompoundFlags))
    container.define(CreateCompoundFlag, _compound_flag_uc(CreateCompoundFlag))
    container.define(DeleteCompoundFlag, _compound_flag_uc(DeleteCompoundFlag))

    # --- Runs ---
    def _run_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunRepository(uow), c[EventDispatcher])
        return _f

    def _run_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunRepository(uow))
        return _f

    def _create_run(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateRun(
            uow,
            SQLAlchemyRunRepository(uow),
            SQLAlchemyProtocolRepository(uow),
            c[EventDispatcher],
            plate_template_repo=SQLAlchemyPlateTemplateRepository(uow),
        )

    container.define(CreateRun, _create_run)

    def _delete_run(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteRun(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(DeleteRun, _delete_run)

    def _reset_run_data(c):  # type: ignore[no-untyped-def]
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

    def _list_runs_with_counts(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRunsWithCounts(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
        )

    container.define(ListRunsWithCounts, _list_runs_with_counts)

    # --- Readout Data ---
    def _readout_create(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return CreateReadoutData(uow, SQLAlchemyReadoutDataRepository(uow), guard, c[EventDispatcher], run_repo=run_repo)

    def _readout_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyReadoutDataRepository(uow))
        return _f

    def _readout_bulk_create(c):  # type: ignore[no-untyped-def]
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

    def _readout_enriched(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListReadoutDataEnriched(
            uow, SQLAlchemyReadoutDataRepository(uow), c[ReadoutDataEnrichedReader]
        )

    container.define(ListReadoutDataEnriched, _readout_enriched)

    # --- Dose Response ---
    def _dose_response_create(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        run_repo = SQLAlchemyRunRepository(uow)
        guard = DataLockGuard(run_repo)
        return CreateDoseResponseCurve(uow, SQLAlchemyDoseResponseCurveRepository(uow), guard, c[EventDispatcher], run_repo=run_repo)

    def _dose_response_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyDoseResponseCurveRepository(uow))
        return _f

    container.define(CreateDoseResponseCurve, _dose_response_create)
    container.define(ListDoseResponseByRun, _dose_response_query(ListDoseResponseByRun))

    container.define(
        DoseResponseEnrichedReader,
        lambda c: SQLAlchemyDoseResponseEnrichedReader(c[async_sessionmaker]),
    )

    def _dose_response_enriched(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDoseResponseEnriched(
            uow,
            SQLAlchemyDoseResponseCurveRepository(uow),
            c[DoseResponseEnrichedReader],
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(ListDoseResponseEnriched, _dose_response_enriched)

    def _fit_dose_response_curves(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FitDoseResponseCurves(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            curve_fitter=c[CurveFittingService],
        )

    container.define(FitDoseResponseCurves, _fit_dose_response_curves)

    def _refit_dose_response_curve(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RefitDoseResponseCurve(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            curve_fitter=c[CurveFittingService],
        )

    container.define(RefitDoseResponseCurve, _refit_dose_response_curve)

    def _classify_dose_response_curve(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ClassifyDoseResponseCurve(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
        )

    container.define(ClassifyDoseResponseCurve, _classify_dose_response_curve)

    # --- Plate Map + Fit Curves for Run ---
    container.define(
        PlateMapReader,
        lambda c: SQLAlchemyPlateMapReader(c[async_sessionmaker]),
    )

    def _get_plate_map(c):  # type: ignore[no-untyped-def]
        return GetPlateMap(reader=c[PlateMapReader])

    container.define(GetPlateMap, _get_plate_map)

    # --- Plate Templates ---
    def _pt_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyPlateTemplateRepository(uow), c[EventDispatcher])
        return _f

    def _pt_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyPlateTemplateRepository(uow))
        return _f

    container.define(CreatePlateTemplate, _pt_cmd(CreatePlateTemplate))
    container.define(UpdatePlateTemplate, _pt_cmd(UpdatePlateTemplate))
    container.define(DeletePlateTemplate, _pt_cmd(DeletePlateTemplate))
    container.define(GetPlateTemplate, _pt_query(GetPlateTemplate))
    container.define(ListPlateTemplates, _pt_query(ListPlateTemplates))

    # --- Readout Calculation Engine + Plate Setup ---
    def _readout_calc_engine(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ReadoutCalculationEngine(
            uow=uow,
            formula_evaluator=c[FormulaEvaluator],
            plate_normalizer=c[PlateNormalizer],
            replicate_aggregator=c[ReplicateAggregator],
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            fit_dose_response=c[FitDoseResponseCurves],
            plate_quality=c[PlateQualityCalculator],
        )

    container.define(ReadoutCalculationEngine, _readout_calc_engine)

    def _set_up_run_plate(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        resolver = MoleculeResolver(SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])
        return SetUpRunPlate(
            uow=uow,
            run_repo=SQLAlchemyRunRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
            molecule_resolver=resolver,
            dispatcher=c[EventDispatcher],
        )

    container.define(SetUpRunPlate, _set_up_run_plate)

    def _import_run_readouts(c):  # type: ignore[no-untyped-def]
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

    def _preview_run_file(c):  # type: ignore[no-untyped-def]
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
        )

    container.define(PreviewRunFile, _preview_run_file)

    def _import_run_file(c):  # type: ignore[no-untyped-def]
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
        )

    container.define(ImportRunFile, _import_run_file)

    # --- Run import templates (CRUD) ---
    def _run_import_template_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRunImportTemplateRepository(uow), c[EventDispatcher])
        return _f

    def _list_run_import_templates(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRunImportTemplates(uow, SQLAlchemyRunImportTemplateRepository(uow))

    container.define(CreateRunImportTemplate, _run_import_template_cmd(CreateRunImportTemplate))
    container.define(UpdateRunImportTemplate, _run_import_template_cmd(UpdateRunImportTemplate))
    container.define(DeleteRunImportTemplate, _run_import_template_cmd(DeleteRunImportTemplate))
    container.define(ListRunImportTemplates, _list_run_import_templates)

    def _cross_protocol_resolver(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CrossProtocolResolver(
            uow=uow,
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
        )

    container.define(CrossProtocolResolver, _cross_protocol_resolver)

    def _condition_grouping_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ConditionGroupingService(
            uow=uow,
            readout_data_repo=SQLAlchemyReadoutDataRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(ConditionGroupingService, _condition_grouping_service)

    # --- Registered Plates ---
    def _reg_plate_cmd(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegisteredPlateRepository(uow), c[EventDispatcher])
        return _f

    def _reg_plate_query(uc_cls):  # type: ignore[no-untyped-def]
        def _f(c):  # type: ignore[no-untyped-def]
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegisteredPlateRepository(uow))
        return _f

    def _map_wells(c):  # type: ignore[no-untyped-def]
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

    def _delete_reg_plate(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeletePlate(uow, SQLAlchemyRegisteredPlateRepository(uow), c[EventDispatcher])

    container.define(DeletePlate, _delete_reg_plate)

    # --- Plate Read Model ---
    container.define(
        PlateReadModelService,
        lambda c: SQLAlchemyPlateReadModelService(c[async_sessionmaker]()),
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
    def _get_compound_curves(c):  # type: ignore[no-untyped-def]
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
    def _molecule_activity_service(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MoleculeActivityService(
            uow=uow,
            readout_repo=SQLAlchemyReadoutDataRepository(uow),
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(MoleculeActivityService, _molecule_activity_service)

    def _get_molecule_activity_detail(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetMoleculeActivityDetail(
            uow=uow,
            curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
        )

    container.define(GetMoleculeActivityDetail, _get_molecule_activity_detail)

    # --- Ontology Search & Annotations ---
    container.define(BioPortalClient, lambda c: BioPortalClient(c[SecretProvider]))
    container.define(SearchOntology, lambda c: SearchOntology(c[BioPortalClient]))

    def _set_ontology_annotation(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetOntologyAnnotation(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

    def _remove_ontology_annotation(c):  # type: ignore[no-untyped-def]
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveOntologyAnnotation(uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher])

    container.define(SetOntologyAnnotation, _set_ontology_annotation)
    container.define(RemoveOntologyAnnotation, _remove_ontology_annotation)
