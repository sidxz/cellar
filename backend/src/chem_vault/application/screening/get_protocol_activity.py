"""GetProtocolActivitySummary query — multi-readout compound-centric results.

Returns ALL aggregatable readouts per compound in a single response,
with scientifically correct aggregation:
  - Numeric readouts: arithmetic mean + max (higher-is-better)
  - Dose-response readouts: geometric mean + min fitted_value (lower-is-better),
    plus best curve params (hill_slope, top, bottom, r_squared)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success
from sqlalchemy import distinct, func, select

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

VALID_STATUSES = ("completed", "approved")
_AGGREGATABLE_DATA_TYPES = {"numeric", "dose_response"}


@dataclass(frozen=True, kw_only=True)
class ActivitySummaryQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True)
class CurveParams:
    hill_slope: float
    top: float
    bottom: float
    fitted_value: float
    r_squared: float


@dataclass(frozen=True)
class ReadoutValue:
    best: float | None = None
    mean: float | None = None
    curve_class: str | None = None
    curve_params: CurveParams | None = None
    data_points: list[dict[str, float]] | None = None
    n: int | None = None
    sd: float | None = None


@dataclass(frozen=True)
class ReadoutDefInfo:
    name: str
    data_type: str
    unit: str | None
    best_direction: str  # "high" or "low"


@dataclass(frozen=True)
class CompoundActivity:
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    run_count: int
    last_tested: str | None
    readouts: dict[str, ReadoutValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivitySummaryV2:
    items: list[CompoundActivity]
    readout_definitions: list[ReadoutDefInfo]
    total_compounds: int


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class GetProtocolActivitySummary:
    """Aggregate compound results across all runs for a protocol.

    Uses raw SA queries (read-model approach) rather than loading full
    aggregates, since we only need per-molecule aggregated readout data.

    Returns all numeric and dose-response readouts per compound in a
    single response — the frontend builds dynamic columns from
    ``readout_definitions``.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        input: ActivitySummaryQuery,
        auth: AuthContext | None = None,
    ) -> Result[ActivitySummaryV2, DomainError]:
        # Deferred imports — these are infra models, only used inside the
        # read-model query.  Keeps the module importable without a DB.
        from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
            MoleculeModel,
        )
        from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            DoseResponseCurveModel,
            ProtocolModel,
            ReadoutDataModel,
            ReadoutDefinitionModel,
            RunModel,
        )

        async with self._uow as uow:
            session = uow.session  # type: ignore[union-attr]
            ws = input.workspace_id
            pid = input.protocol_id

            # ----------------------------------------------------------
            # Setup: load protocol, build readout def metadata
            # ----------------------------------------------------------
            protocol_stmt = (
                select(ProtocolModel)
                .where(
                    ProtocolModel.id == pid,
                    ProtocolModel.workspace_id == ws,
                )
            )
            protocol = (await session.execute(protocol_stmt)).scalar_one_or_none()
            if protocol is None:
                return Failure(
                    NotFoundError(f"Protocol {pid} not found in workspace")
                )

            # Build readout_defs (only numeric + dose_response)
            readout_defs: list[ReadoutDefInfo] = []
            # Map curve_type -> readout_name for DR readouts
            dr_curve_type_map: dict[str, str] = {}

            for rd in protocol.readout_definitions:
                if rd.data_type not in _AGGREGATABLE_DATA_TYPES:
                    continue

                if rd.data_type == "dose_response":
                    best_direction = "low"
                    config = rd.dose_response_config
                    if config and isinstance(config, dict):
                        curve_type = config.get("curve_type")
                        if curve_type:
                            dr_curve_type_map[curve_type] = rd.name
                else:
                    best_direction = "high"

                readout_defs.append(
                    ReadoutDefInfo(
                        name=rd.name,
                        data_type=rd.data_type,
                        unit=rd.unit,
                        best_direction=best_direction,
                    )
                )

            if not readout_defs:
                return Success(
                    ActivitySummaryV2(
                        items=[],
                        readout_definitions=[],
                        total_compounds=0,
                    )
                )

            # ----------------------------------------------------------
            # Query 1: Molecule base — all molecules tested + run_count
            # ----------------------------------------------------------
            mol_stmt = (
                select(
                    ReadoutDataModel.molecule_id,
                    MoleculeModel.name.label("molecule_name"),
                    MoleculeModel.registration_number,
                    func.count(distinct(ReadoutDataModel.run_id)).label("run_count"),
                    func.max(RunModel.run_date).label("last_tested"),
                )
                .select_from(ReadoutDataModel)
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .join(MoleculeModel, ReadoutDataModel.molecule_id == MoleculeModel.id)
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    RunModel.status.in_(VALID_STATUSES),
                    ReadoutDataModel.molecule_id.isnot(None),
                )
                .group_by(
                    ReadoutDataModel.molecule_id,
                    MoleculeModel.name,
                    MoleculeModel.registration_number,
                )
            )
            mol_rows = (await session.execute(mol_stmt)).all()

            if not mol_rows:
                return Success(
                    ActivitySummaryV2(
                        items=[],
                        readout_definitions=readout_defs,
                        total_compounds=0,
                    )
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
                    RunModel.status.in_(VALID_STATUSES),
                    ReadoutDefinitionModel.data_type != "dose_response",
                    ReadoutDataModel.molecule_id.isnot(None),
                    ReadoutDataModel.value_numeric.isnot(None),
                    ReadoutDataModel.is_outlier == False,  # noqa: E712
                )
                .group_by(ReadoutDataModel.molecule_id, ReadoutDefinitionModel.name)
            )
            numeric_rows = (await session.execute(numeric_stmt)).all()

            # ----------------------------------------------------------
            # Query 3a: DR aggregation — geo mean + min per curve_type
            # ----------------------------------------------------------
            dr_agg_stmt = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.curve_type,
                    func.min(DoseResponseCurveModel.fitted_value).label("best"),
                    func.exp(func.avg(func.ln(DoseResponseCurveModel.fitted_value))).label("geo_mean"),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.status.in_(VALID_STATUSES),
                    DoseResponseCurveModel.curve_class != "inactive",
                    DoseResponseCurveModel.fitted_value > 0,
                )
                .group_by(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.curve_type,
                )
            )
            dr_agg_rows = (await session.execute(dr_agg_stmt)).all()

            # ----------------------------------------------------------
            # Query 3b: Best curve params — MIN fitted_value per molecule
            # ----------------------------------------------------------
            ranked_sub = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.curve_type,
                    DoseResponseCurveModel.curve_class,
                    DoseResponseCurveModel.hill_slope,
                    DoseResponseCurveModel.top,
                    DoseResponseCurveModel.bottom,
                    DoseResponseCurveModel.fitted_value,
                    DoseResponseCurveModel.r_squared,
                    DoseResponseCurveModel.raw_data,
                    func.row_number()
                    .over(
                        partition_by=[
                            DoseResponseCurveModel.molecule_id,
                            DoseResponseCurveModel.curve_type,
                        ],
                        order_by=DoseResponseCurveModel.fitted_value.asc(),
                    )
                    .label("rn"),
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .where(
                    DoseResponseCurveModel.protocol_id == pid,
                    RunModel.status.in_(VALID_STATUSES),
                    DoseResponseCurveModel.curve_class != "inactive",
                    DoseResponseCurveModel.fitted_value > 0,
                )
                .subquery()
            )
            best_params_stmt = select(ranked_sub).where(ranked_sub.c.rn == 1)
            best_params_rows = (await session.execute(best_params_stmt)).all()

            # ----------------------------------------------------------
            # Python merge
            # ----------------------------------------------------------

            # Index numeric rows: (molecule_id, readout_name) -> row
            numeric_map: dict[tuple[uuid.UUID, str], object] = {
                (row.molecule_id, row.readout_name): row for row in numeric_rows
            }

            # Index DR agg rows: (molecule_id, curve_type) -> row
            dr_agg_map: dict[tuple[uuid.UUID, str], object] = {
                (row.molecule_id, row.curve_type): row for row in dr_agg_rows
            }

            # Index best params rows: (molecule_id, curve_type) -> row
            best_params_map: dict[tuple[uuid.UUID, str], object] = {
                (row.molecule_id, row.curve_type): row for row in best_params_rows
            }

            items: list[CompoundActivity] = []
            for mol in mol_rows:
                readouts: dict[str, ReadoutValue] = {}

                for rd_info in readout_defs:
                    if rd_info.data_type == "dose_response":
                        # Find curve_type for this readout name
                        curve_type: str | None = None
                        for ct, rn in dr_curve_type_map.items():
                            if rn == rd_info.name:
                                curve_type = ct
                                break
                        if curve_type is None:
                            continue

                        dr_key = (mol.molecule_id, curve_type)
                        dr_row = dr_agg_map.get(dr_key)
                        bp_row = best_params_map.get(dr_key)

                        if dr_row is None:
                            continue

                        curve_params: CurveParams | None = None
                        curve_class: str | None = None
                        data_points: list[dict[str, float]] | None = None
                        if bp_row is not None:
                            curve_class = bp_row.curve_class
                            curve_params = CurveParams(
                                hill_slope=float(bp_row.hill_slope),
                                top=float(bp_row.top),
                                bottom=float(bp_row.bottom),
                                fitted_value=float(bp_row.fitted_value),
                                r_squared=float(bp_row.r_squared),
                            )
                            # Extract condensed data points from raw_data JSONB
                            raw = bp_row.raw_data
                            if raw and isinstance(raw, list):
                                data_points = []
                                for pt in raw:
                                    conc = pt.get("concentration") or pt.get("x")
                                    resp = pt.get("response") or pt.get("y")
                                    if isinstance(conc, (int, float)) and isinstance(resp, (int, float)):
                                        data_points.append({"x": float(conc), "y": float(resp)})

                        readouts[rd_info.name] = ReadoutValue(
                            best=float(dr_row.best) if dr_row.best is not None else None,
                            mean=round(float(dr_row.geo_mean), 6) if dr_row.geo_mean is not None else None,
                            curve_class=curve_class,
                            curve_params=curve_params,
                            data_points=data_points,
                        )
                    else:
                        # Numeric readout
                        num_key = (mol.molecule_id, rd_info.name)
                        num_row = numeric_map.get(num_key)
                        if num_row is None:
                            continue

                        readouts[rd_info.name] = ReadoutValue(
                            best=float(num_row.best) if num_row.best is not None else None,
                            mean=round(float(num_row.mean), 4) if num_row.mean is not None else None,
                            n=int(num_row.n) if num_row.n is not None else None,
                            sd=round(float(num_row.sd), 4) if num_row.sd is not None else None,
                        )

                items.append(
                    CompoundActivity(
                        molecule_id=mol.molecule_id,
                        molecule_name=mol.molecule_name or "",
                        registration_number=mol.registration_number or "",
                        run_count=mol.run_count,
                        last_tested=(
                            mol.last_tested.isoformat()
                            if mol.last_tested is not None
                            else None
                        ),
                        readouts=readouts,
                    )
                )

            return Success(
                ActivitySummaryV2(
                    items=items,
                    readout_definitions=readout_defs,
                    total_compounds=len(items),
                )
            )
