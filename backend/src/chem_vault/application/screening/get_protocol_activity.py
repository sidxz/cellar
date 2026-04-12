"""GetProtocolActivitySummary query use case — compound-centric results across all runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success
from sqlalchemy import distinct, func, select

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ActivitySummaryQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    readout_name: str | None = None  # defaults to first readout def


@dataclass(frozen=True)
class ActivitySummaryItem:
    molecule_id: uuid.UUID
    molecule_name: str
    molecule_registration_number: str
    best_value: float | None
    mean_value: float | None
    run_count: int
    min_value: float | None
    max_value: float | None
    curve_class: str | None
    last_tested: str | None  # ISO date string


@dataclass(frozen=True)
class ActivitySummary:
    items: list[ActivitySummaryItem]
    readout_name: str
    readout_unit: str | None
    total_compounds: int


class GetProtocolActivitySummary:
    """Aggregate compound results across all runs for a protocol.

    Uses raw SA queries (read-model approach) rather than loading full
    aggregates, since we only need per-molecule aggregated readout data.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        input: ActivitySummaryQuery,
        auth: AuthContext | None = None,
    ) -> Result[ActivitySummary, DomainError]:
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

            # 1. Verify protocol exists in workspace
            protocol_stmt = select(ProtocolModel.id).where(
                ProtocolModel.id == pid,
                ProtocolModel.workspace_id == ws,
            )
            protocol_row = (await session.execute(protocol_stmt)).one_or_none()
            if protocol_row is None:
                return Failure(
                    NotFoundError(f"Protocol {pid} not found in workspace")
                )

            # 2. Resolve readout_name: if not provided, use the first readout definition
            if input.readout_name is not None:
                rd_stmt = select(
                    ReadoutDefinitionModel.id,
                    ReadoutDefinitionModel.name,
                    ReadoutDefinitionModel.unit,
                ).where(
                    ReadoutDefinitionModel.protocol_id == pid,
                    ReadoutDefinitionModel.name == input.readout_name,
                )
            else:
                rd_stmt = (
                    select(
                        ReadoutDefinitionModel.id,
                        ReadoutDefinitionModel.name,
                        ReadoutDefinitionModel.unit,
                    )
                    .where(ReadoutDefinitionModel.protocol_id == pid)
                    .order_by(ReadoutDefinitionModel.created_at.asc())
                    .limit(1)
                )

            rd_row = (await session.execute(rd_stmt)).one_or_none()
            if rd_row is None:
                # No matching readout definition — return empty summary
                readout_name = input.readout_name or ""
                return Success(
                    ActivitySummary(
                        items=[],
                        readout_name=readout_name,
                        readout_unit=None,
                        total_compounds=0,
                    )
                )

            rd_id = rd_row.id
            readout_name = rd_row.name
            readout_unit = rd_row.unit

            # 3. Build curve_class subquery — most recent curve_class per molecule
            curve_sub = (
                select(
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.curve_class,
                    func.row_number()
                    .over(
                        partition_by=DoseResponseCurveModel.molecule_id,
                        order_by=DoseResponseCurveModel.created_at.desc(),
                    )
                    .label("rn"),
                ).where(DoseResponseCurveModel.protocol_id == pid)
            ).subquery("curve_sub")

            latest_curve = (
                select(curve_sub.c.molecule_id, curve_sub.c.curve_class).where(
                    curve_sub.c.rn == 1
                )
            ).subquery("latest_curve")

            # 4. Main aggregation query
            main_stmt = (
                select(
                    ReadoutDataModel.molecule_id,
                    MoleculeModel.name.label("molecule_name"),
                    MoleculeModel.registration_number.label(
                        "molecule_registration_number"
                    ),
                    func.min(ReadoutDataModel.value_numeric).label("best_value"),
                    func.avg(ReadoutDataModel.value_numeric).label("mean_value"),
                    func.count(distinct(ReadoutDataModel.run_id)).label("run_count"),
                    func.min(ReadoutDataModel.value_numeric).label("min_value"),
                    func.max(ReadoutDataModel.value_numeric).label("max_value"),
                    func.max(RunModel.run_date).label("last_tested"),
                    latest_curve.c.curve_class,
                )
                .select_from(ReadoutDataModel)
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .join(MoleculeModel, ReadoutDataModel.molecule_id == MoleculeModel.id)
                .outerjoin(
                    latest_curve,
                    ReadoutDataModel.molecule_id == latest_curve.c.molecule_id,
                )
                .where(
                    RunModel.protocol_id == pid,
                    RunModel.workspace_id == ws,
                    ReadoutDataModel.readout_definition_id == rd_id,
                    ReadoutDataModel.molecule_id.isnot(None),
                    ReadoutDataModel.value_numeric.isnot(None),
                    ReadoutDataModel.is_outlier == False,  # noqa: E712
                )
                .group_by(
                    ReadoutDataModel.molecule_id,
                    MoleculeModel.name,
                    MoleculeModel.registration_number,
                    latest_curve.c.curve_class,
                )
                .order_by(func.min(ReadoutDataModel.value_numeric).asc())
            )

            rows = (await session.execute(main_stmt)).all()

            items = [
                ActivitySummaryItem(
                    molecule_id=row.molecule_id,
                    molecule_name=row.molecule_name,
                    molecule_registration_number=row.molecule_registration_number,
                    best_value=float(row.best_value) if row.best_value is not None else None,
                    mean_value=round(float(row.mean_value), 4) if row.mean_value is not None else None,
                    run_count=row.run_count,
                    min_value=float(row.min_value) if row.min_value is not None else None,
                    max_value=float(row.max_value) if row.max_value is not None else None,
                    curve_class=row.curve_class,
                    last_tested=row.last_tested.isoformat() if row.last_tested is not None else None,
                )
                for row in rows
            ]

            return Success(
                ActivitySummary(
                    items=items,
                    readout_name=readout_name,
                    readout_unit=readout_unit,
                    total_compounds=len(items),
                )
            )
