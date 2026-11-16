"""SQLAlchemy implementation of VisualizationDatasetReader."""

from __future__ import annotations

import uuid
from dataclasses import fields

from sqlalchemy import Text, and_, cast, func, join, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.screening.compound_curves_reader import CurveRow
from cellar.application.visualization.dataset_reader import (
    CompoundInfo,
    ReadoutDefInfo,
    RunInfo,
    WellValueRow,
)
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    PlateModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
    WellModel,
)

_RUN_COLUMNS = (
    RunModel.id,
    RunModel.protocol_id,
    RunModel.run_date,
    RunModel.operator,
    RunModel.status,
    RunModel.conditions,
    RunModel.created_at,
)


def _run_info(r) -> RunInfo:  # SQLAlchemy Row
    return RunInfo(
        id=r.id,
        protocol_id=r.protocol_id,
        run_date=r.run_date,
        operator_id=r.operator,
        status=r.status,
        conditions=r.conditions,
        created_at=r.created_at,
    )


class SQLAlchemyVisualizationDatasetReader:
    """Read model for workbench datasets. Every query is workspace-scoped."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def runs_for_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[RunInfo] | None:
        async with self._session_factory() as session:
            found = await session.scalar(
                select(ProtocolModel.id).where(
                    ProtocolModel.id == protocol_id, ProtocolModel.workspace_id == workspace_id
                )
            )
            if found is None:
                return None
            rows = (
                await session.execute(
                    select(*_RUN_COLUMNS)
                    .where(
                        RunModel.workspace_id == workspace_id, RunModel.protocol_id == protocol_id
                    )
                    .order_by(RunModel.run_date, RunModel.created_at)
                )
            ).all()
            return [_run_info(r) for r in rows]

    async def runs_by_ids(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> list[RunInfo]:
        if not run_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(*_RUN_COLUMNS)
                    .where(RunModel.workspace_id == workspace_id, RunModel.id.in_(run_ids))
                    .order_by(RunModel.run_date, RunModel.created_at)
                )
            ).all()
            return [_run_info(r) for r in rows]

    async def readout_definitions(
        self, workspace_id: uuid.UUID, protocol_ids: list[uuid.UUID]
    ) -> list[ReadoutDefInfo]:
        if not protocol_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        ReadoutDefinitionModel.id,
                        ReadoutDefinitionModel.protocol_id,
                        ReadoutDefinitionModel.name,
                        ReadoutDefinitionModel.data_type,
                        ReadoutDefinitionModel.unit,
                        ReadoutDefinitionModel.display_order,
                        ProtocolModel.dose_unit,
                        ReadoutDefinitionModel.dose_response_config["curve_type"].astext,
                        ReadoutDefinitionModel.melt_config["measure"].astext,
                        ReadoutDefinitionModel.aggregation,
                        ReadoutDefinitionModel.dose_response_config["intercepts"][0],
                    )
                    .join(ProtocolModel, ProtocolModel.id == ReadoutDefinitionModel.protocol_id)
                    .where(
                        ProtocolModel.workspace_id == workspace_id,
                        ReadoutDefinitionModel.protocol_id.in_(protocol_ids),
                    )
                    .order_by(ReadoutDefinitionModel.display_order, ReadoutDefinitionModel.name)
                )
            ).all()
            return [ReadoutDefInfo(*r) for r in rows]  # selected in field order

    async def count_wells_rows(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not run_ids:
            return {}
        rd = ReadoutDataModel
        wellless_key = func.concat(
            func.coalesce(cast(rd.molecule_id, Text), "-"),
            ":",
            func.coalesce(cast(rd.batch_id, Text), "-"),
        )
        stmt = (
            select(
                rd.run_id,
                (
                    func.count(func.distinct(rd.well_id))
                    + func.count(func.distinct(wellless_key)).filter(rd.well_id.is_(None))
                ).label("n"),
            )
            .where(rd.workspace_id == workspace_id, rd.run_id.in_(run_ids))
            .group_by(rd.run_id)
        )
        async with self._session_factory() as session:
            return {r.run_id: int(r.n) for r in (await session.execute(stmt)).all()}

    async def fetch_well_values(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> list[WellValueRow]:
        if not run_ids:
            return []
        rd = ReadoutDataModel
        batch_id = func.coalesce(rd.batch_id, WellModel.batch_id)
        molecule_id = func.coalesce(rd.molecule_id, BatchModel.molecule_id)
        # Selected in WellValueRow field order (built from the dataclass, so the
        # order holds by construction) and unpacked positionally: named Row
        # access dominated the fetch time at 400k rows.
        exprs = {
            "run_id": rd.run_id,
            "well_id": WellModel.id,
            "plate_id": PlateModel.id,
            "plate_number": PlateModel.plate_number,
            "plate_barcode": PlateModel.barcode,
            "plate_format": PlateModel.format,
            "holder_rows": PlateModel.holder_rows,
            "holder_columns": PlateModel.holder_columns,
            "well_row": WellModel.row,
            "well_column": WellModel.column,
            "well_type": WellModel.well_type,
            "dose": WellModel.dose,
            "well_label": WellModel.label,
            "molecule_id": molecule_id,
            "registration_number": MoleculeModel.registration_number,
            "smiles": MoleculeModel.smiles,
            "batch_id": batch_id,
            "batch_number": BatchModel.batch_number,
            "readout_definition_id": rd.readout_definition_id,
            "normalization_applied": rd.normalization_applied,
            "value_numeric": rd.value_numeric,
            "value_qualifier": rd.value_qualifier,
            "value_text": rd.value_text,
            "is_outlier": rd.is_outlier,
            "created_at": rd.created_at,
        }
        stmt = (
            select(*(exprs[f.name].label(f.name) for f in fields(WellValueRow)))
            .select_from(rd)
            .join(RunModel, and_(RunModel.id == rd.run_id, RunModel.workspace_id == workspace_id))
            # Only a well on a plate of the readout's own run joins; a well_id pointing
            # anywhere else reads as well-less rather than exposing that well.
            .outerjoin(
                join(WellModel, PlateModel, PlateModel.id == WellModel.plate_id),
                and_(WellModel.id == rd.well_id, PlateModel.run_id == rd.run_id),
            )
            .outerjoin(
                BatchModel,
                and_(BatchModel.id == batch_id, BatchModel.workspace_id == workspace_id),
            )
            .outerjoin(
                MoleculeModel,
                and_(MoleculeModel.id == molecule_id, MoleculeModel.workspace_id == workspace_id),
            )
            .where(rd.workspace_id == workspace_id, rd.run_id.in_(run_ids))
            .order_by(
                rd.run_id,
                PlateModel.plate_number.nulls_last(),
                WellModel.row,
                WellModel.column,
                rd.created_at,
            )
        )
        async with self._session_factory() as session:
            # Core execution on the session's connection skips the ORM loading layer.
            rows = (await (await session.connection()).execute(stmt)).all()
        return [WellValueRow(*r) for r in rows]

    async def fetch_curves(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> list[CurveRow]:
        if not run_ids:
            return []
        c = DoseResponseCurveModel
        stmt = (
            select(*(getattr(c, f.name) for f in fields(CurveRow)))
            .join(RunModel, and_(RunModel.id == c.run_id, RunModel.workspace_id == workspace_id))
            .where(c.workspace_id == workspace_id, any_id(c.run_id, run_ids))
        )
        async with self._session_factory() as session:
            rows = (await (await session.connection()).execute(stmt)).all()
        return [CurveRow(*r) for r in rows]

    async def compound_info(
        self, workspace_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, CompoundInfo]:
        if not molecule_ids:
            return {}
        m = MoleculeModel
        stmt = select(m.id, *(getattr(m, f.name) for f in fields(CompoundInfo))).where(
            m.workspace_id == workspace_id, any_id(m.id, molecule_ids)
        )
        async with self._session_factory() as session:
            rows = (await (await session.connection()).execute(stmt)).all()
        return {r[0]: CompoundInfo(*r[1:]) for r in rows}

    async def batch_numbers(
        self, workspace_id: uuid.UUID, batch_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not batch_ids:
            return {}
        stmt = select(BatchModel.id, BatchModel.batch_number).where(
            BatchModel.workspace_id == workspace_id, any_id(BatchModel.id, batch_ids)
        )
        async with self._session_factory() as session:
            rows = (await (await session.connection()).execute(stmt)).all()
        return {r[0]: r[1] for r in rows}
