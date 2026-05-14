"""SQLAlchemy implementation of ProtocolActivityReader."""

from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.screening.protocol_activity_reader import (
    BestParamsRow,
    DRAggRow,
    MoleculeBaseRow,
    NumericReadoutRow,
    ProtocolActivityData,
    ProtocolRow,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeIdentifierModel,
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
)


class SQLAlchemyProtocolActivityReader:
    """Infrastructure-layer read model for protocol activity queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_activity_data(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        valid_statuses: tuple[str, ...],
    ) -> ProtocolActivityData:
        ws = workspace_id
        pid = protocol_id

        async with self._session_factory() as session:
            # ----------------------------------------------------------
            # Load protocol
            # ----------------------------------------------------------
            protocol_stmt = select(ProtocolModel).where(
                ProtocolModel.id == pid,
                ProtocolModel.workspace_id == ws,
            )
            protocol_model = (await session.execute(protocol_stmt)).scalar_one_or_none()

            if protocol_model is None:
                return ProtocolActivityData(protocol=None)

            protocol = ProtocolRow(
                id=protocol_model.id,
                readout_definitions=list(protocol_model.readout_definitions),
            )

            # ----------------------------------------------------------
            # Query 1: Molecule base — all molecules with readout data
            #          OR dose-response curves
            # ----------------------------------------------------------
            # Source A: molecules from readout data
            rd_mols = (
                select(
                    ReadoutDataModel.molecule_id,
                    func.count(distinct(ReadoutDataModel.run_id)).label("run_count"),
                    func.max(RunModel.run_date).label("last_tested"),
                )
                .select_from(ReadoutDataModel)
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                    ReadoutDataModel.molecule_id.isnot(None),
                )
                .group_by(ReadoutDataModel.molecule_id)
            )

            # Source B: molecules from dose-response curves only
            drc_mols = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    func.count(distinct(DoseResponseCurveModel.run_id)).label("run_count"),
                    func.max(RunModel.run_date).label("last_tested"),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                )
                .group_by(DoseResponseCurveModel.molecule_id)
            )

            # Merge: take max run_count and latest date per molecule
            combined = union_all(rd_mols, drc_mols).subquery("combined")
            mol_stmt = (
                select(
                    combined.c.molecule_id,
                    MoleculeModel.name.label("molecule_name"),
                    MoleculeModel.registration_number,
                    MoleculeModel.smiles,
                    func.max(combined.c.run_count).label("run_count"),
                    func.max(combined.c.last_tested).label("last_tested"),
                )
                .join(MoleculeModel, combined.c.molecule_id == MoleculeModel.id)
                .group_by(
                    combined.c.molecule_id,
                    MoleculeModel.name,
                    MoleculeModel.registration_number,
                    MoleculeModel.smiles,
                )
            )
            raw_mol_rows = (await session.execute(mol_stmt)).all()

            molecule_rows = [
                MoleculeBaseRow(
                    molecule_id=r.molecule_id,
                    molecule_name=r.molecule_name,
                    registration_number=r.registration_number,
                    smiles=r.smiles,
                    run_count=r.run_count,
                    last_tested=r.last_tested,
                )
                for r in raw_mol_rows
            ]

            # Batch-load synonyms for all molecules
            mol_ids = [r.molecule_id for r in molecule_rows]
            synonym_map: dict[uuid.UUID, list[str]] = {}
            if mol_ids:
                syn_stmt = select(
                    MoleculeIdentifierModel.molecule_id,
                    MoleculeIdentifierModel.identifier,
                ).where(
                    MoleculeIdentifierModel.molecule_id.in_(mol_ids),
                    MoleculeIdentifierModel.identifier_type == "custom",
                )
                syn_rows = (await session.execute(syn_stmt)).all()
                for sr in syn_rows:
                    synonym_map.setdefault(sr.molecule_id, []).append(sr.identifier)

            if not molecule_rows:
                return ProtocolActivityData(
                    protocol=protocol,
                    molecule_rows=[],
                    synonym_map={},
                    numeric_rows=[],
                    dr_agg_rows=[],
                    best_params_rows=[],
                )

            # ----------------------------------------------------------
            # Query 2: Numeric readout aggregation (non-DR)
            # ----------------------------------------------------------
            numeric_stmt = (
                select(
                    ReadoutDataModel.molecule_id,
                    ReadoutDefinitionModel.name.label("readout_name"),
                    func.max(ReadoutDataModel.value_numeric).label("best"),
                    func.avg(ReadoutDataModel.value_numeric).label("mean"),
                    func.count(ReadoutDataModel.value_numeric).label("n"),
                    func.stddev_samp(ReadoutDataModel.value_numeric).label("sd"),
                )
                .select_from(ReadoutDataModel)
                .join(
                    ReadoutDefinitionModel,
                    ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
                )
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                    ReadoutDefinitionModel.data_type != "dose_response",
                    ReadoutDataModel.molecule_id.isnot(None),
                    ReadoutDataModel.value_numeric.isnot(None),
                    ReadoutDataModel.is_outlier == False,  # noqa: E712
                )
                .group_by(ReadoutDataModel.molecule_id, ReadoutDefinitionModel.name)
            )
            raw_numeric_rows = (await session.execute(numeric_stmt)).all()

            numeric_rows = [
                NumericReadoutRow(
                    molecule_id=r.molecule_id,
                    readout_name=r.readout_name,
                    best=r.best,
                    mean=r.mean,
                    n=r.n,
                    sd=r.sd,
                )
                for r in raw_numeric_rows
            ]

            # ----------------------------------------------------------
            # Query 3a: DR aggregation — geo mean + min per readout-def.
            # Grouping by curve_type would collapse multi-DR protocols
            # (target IC50 + counter-screen IC50 share curve_type='ic50');
            # the readout-def is the precise column identity.
            # ----------------------------------------------------------
            dr_agg_stmt = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.readout_definition_id,
                    func.min(DoseResponseCurveModel.fitted_value).label("best"),
                    func.exp(func.avg(func.ln(DoseResponseCurveModel.fitted_value))).label(
                        "geo_mean"
                    ),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                    DoseResponseCurveModel.curve_class != "inactive",
                    DoseResponseCurveModel.fitted_value > 0,
                )
                .group_by(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.readout_definition_id,
                )
            )
            raw_dr_agg_rows = (await session.execute(dr_agg_stmt)).all()

            dr_agg_rows = [
                DRAggRow(
                    molecule_id=r.molecule_id,
                    readout_definition_id=r.readout_definition_id,
                    best=r.best,
                    geo_mean=r.geo_mean,
                )
                for r in raw_dr_agg_rows
            ]

            # ----------------------------------------------------------
            # Query 3b: Best curve params — MIN fitted_value per molecule
            # ----------------------------------------------------------
            ranked_sub = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.readout_definition_id,
                    DoseResponseCurveModel.curve_class,
                    DoseResponseCurveModel.hill_slope,
                    DoseResponseCurveModel.top,
                    DoseResponseCurveModel.bottom,
                    DoseResponseCurveModel.fitted_value,
                    DoseResponseCurveModel.r_squared,
                    DoseResponseCurveModel.raw_data,
                    BatchModel.batch_number,
                    func.row_number()
                    .over(
                        partition_by=[
                            DoseResponseCurveModel.molecule_id,
                            DoseResponseCurveModel.readout_definition_id,
                        ],
                        order_by=DoseResponseCurveModel.fitted_value.asc(),
                    )
                    .label("rn"),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .outerjoin(BatchModel, DoseResponseCurveModel.batch_id == BatchModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(valid_statuses),
                    DoseResponseCurveModel.curve_class != "inactive",
                    DoseResponseCurveModel.fitted_value > 0,
                )
                .subquery()
            )
            best_params_stmt = select(ranked_sub).where(ranked_sub.c.rn == 1)
            raw_best_params_rows = (await session.execute(best_params_stmt)).all()

            best_params_rows = [
                BestParamsRow(
                    molecule_id=r.molecule_id,
                    readout_definition_id=r.readout_definition_id,
                    curve_class=r.curve_class,
                    hill_slope=r.hill_slope,
                    top=r.top,
                    bottom=r.bottom,
                    fitted_value=r.fitted_value,
                    r_squared=r.r_squared,
                    raw_data=r.raw_data,
                    batch_number=r.batch_number,
                )
                for r in raw_best_params_rows
            ]

        return ProtocolActivityData(
            protocol=protocol,
            molecule_rows=molecule_rows,
            synonym_map=synonym_map,
            numeric_rows=numeric_rows,
            dr_agg_rows=dr_agg_rows,
            best_params_rows=best_params_rows,
        )
