"""SQLAlchemy implementation of PlateMapReader."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.screening.plate_map_reader import (
    PlateMapData,
    PlateMapResult,
    WellMapEntry,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateModel,
    RunModel,
    WellModel,
)


class SQLAlchemyPlateMapReader:
    """Infrastructure-layer read model for plate map queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_plate_map(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> PlateMapResult | None:
        async with self._session_factory() as session:
            # Load run (workspace scoped)
            run_stmt = select(RunModel).where(
                RunModel.id == run_id,
                RunModel.workspace_id == workspace_id,
            )
            run_row = await session.execute(run_stmt)
            run_model = run_row.scalar_one_or_none()
            if run_model is None:
                return None

            # Load plates for this run
            plates_stmt = select(PlateModel).where(PlateModel.run_id == run_id)
            plates_result = await session.execute(plates_stmt)
            plates = plates_result.scalars().all()

            plate_ids = [p.id for p in plates]

            # Load wells for all plates
            wells: list = []
            if plate_ids:
                wells_stmt = select(WellModel).where(WellModel.plate_id.in_(plate_ids))
                wells_result = await session.execute(wells_stmt)
                wells = list(wells_result.scalars().all())

            # Batch-resolve batch -> molecule_id
            batch_ids = list({w.batch_id for w in wells if w.batch_id is not None})
            batch_to_mol: dict[uuid.UUID, uuid.UUID] = {}
            mol_names: dict[uuid.UUID, str] = {}

            if batch_ids:
                batch_stmt = select(BatchModel.id, BatchModel.molecule_id).where(
                    BatchModel.id.in_(batch_ids)
                )
                batch_rows = await session.execute(batch_stmt)
                batch_to_mol = {row[0]: row[1] for row in batch_rows}

                mol_ids = list(set(batch_to_mol.values()))
                if mol_ids:
                    mol_stmt = select(MoleculeModel.id, MoleculeModel.name).where(
                        MoleculeModel.id.in_(mol_ids)
                    )
                    mol_rows = await session.execute(mol_stmt)
                    mol_names = {row[0]: row[1] for row in mol_rows}

            # Build plate_id -> wells mapping
            plate_wells: dict[uuid.UUID, list] = {p.id: [] for p in plates}
            for w in wells:
                plate_wells[w.plate_id].append(w)

            plates_data = []
            for plate in sorted(plates, key=lambda p: p.plate_number):
                well_entries = []
                for well in sorted(plate_wells[plate.id], key=lambda w: (w.row, w.column)):
                    molecule_id = batch_to_mol.get(well.batch_id) if well.batch_id else None
                    well_entries.append(
                        WellMapEntry(
                            well_id=well.id,
                            row=well.row,
                            column=well.column,
                            well_type=well.well_type,
                            batch_id=well.batch_id,
                            molecule_id=molecule_id,
                            molecule_name=mol_names.get(molecule_id) if molecule_id else None,
                            concentration_value=well.concentration_value,
                            concentration_unit=well.concentration_unit,
                        )
                    )
                plates_data.append(
                    PlateMapData(
                        plate_id=plate.id,
                        plate_number=plate.plate_number,
                        wells=well_entries,
                    )
                )

        return PlateMapResult(run_id=run_id, plates=plates_data)
