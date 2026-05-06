"""SQLAlchemy implementation of PlateMapReader."""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.screening.plate_map_reader import (
    PlateMapData,
    PlateMapResult,
    PlateMapSummary,
    WellMapEntry,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeIdentifierModel,
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    PlateModel,
    ProtocolModel,
    RunModel,
    WellModel,
)


_SAMPLE = "sample"
_ALIAS_TYPES = ("custom", "synonym", "common_name")


class SQLAlchemyPlateMapReader:
    """Infrastructure-layer read model for plate map queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_plate_map(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> PlateMapResult | None:
        async with self._session_factory() as session:
            run_stmt = select(RunModel).where(
                RunModel.id == run_id,
                RunModel.workspace_id == workspace_id,
            )
            run_row = await session.execute(run_stmt)
            run_model = run_row.scalar_one_or_none()
            if run_model is None:
                return None

            dose_unit_stmt = select(ProtocolModel.dose_unit).where(
                ProtocolModel.id == run_model.protocol_id
            )
            dose_unit = (
                await session.execute(dose_unit_stmt)
            ).scalar_one_or_none() or "uM"

            plates_stmt = select(PlateModel).where(PlateModel.run_id == run_id)
            plates_result = await session.execute(plates_stmt)
            plates = list(plates_result.scalars().all())

            plate_ids = [p.id for p in plates]

            wells: list[WellModel] = []
            if plate_ids:
                wells_stmt = select(WellModel).where(WellModel.plate_id.in_(plate_ids))
                wells_result = await session.execute(wells_stmt)
                wells = list(wells_result.scalars().all())

            # Batch lookup: batch_id -> (batch_number, molecule_id) + per-mol
            # display info (name, smiles, custom synonyms) so the well tooltip
            # can render structure + aliases without a second roundtrip.
            batch_ids = list({w.batch_id for w in wells if w.batch_id is not None})
            batch_to_mol: dict[uuid.UUID, uuid.UUID] = {}
            batch_numbers: dict[uuid.UUID, str] = {}
            mol_names: dict[uuid.UUID, str] = {}
            mol_smiles: dict[uuid.UUID, str | None] = {}
            mol_synonyms: dict[uuid.UUID, list[str]] = {}

            if batch_ids:
                batch_stmt = select(
                    BatchModel.id, BatchModel.molecule_id, BatchModel.batch_number
                ).where(BatchModel.id.in_(batch_ids))
                batch_rows = await session.execute(batch_stmt)
                for bid, mol_id, bnum in batch_rows:
                    batch_to_mol[bid] = mol_id
                    batch_numbers[bid] = bnum

                mol_ids = list(set(batch_to_mol.values()))
                if mol_ids:
                    mol_stmt = select(
                        MoleculeModel.id,
                        MoleculeModel.name,
                        MoleculeModel.smiles,
                    ).where(MoleculeModel.id.in_(mol_ids))
                    mol_rows = await session.execute(mol_stmt)
                    for mid, name, smiles in mol_rows:
                        mol_names[mid] = name
                        mol_smiles[mid] = smiles

                    ident_stmt = select(
                        MoleculeIdentifierModel.molecule_id,
                        MoleculeIdentifierModel.identifier,
                        MoleculeIdentifierModel.identifier_type,
                    ).where(
                        MoleculeIdentifierModel.molecule_id.in_(mol_ids),
                        MoleculeIdentifierModel.identifier_type.in_(_ALIAS_TYPES),
                    )
                    ident_rows = await session.execute(ident_stmt)
                    for mid, ident, _ in ident_rows:
                        if ident:
                            mol_synonyms.setdefault(mid, []).append(ident)

            plate_wells: dict[uuid.UUID, list[WellModel]] = {p.id: [] for p in plates}
            for w in wells:
                plate_wells[w.plate_id].append(w)

            plates_data: list[PlateMapData] = []
            for plate in sorted(plates, key=lambda p: p.plate_number):
                well_entries: list[WellMapEntry] = []
                for well in sorted(
                    plate_wells[plate.id], key=lambda w: (w.row, w.column)
                ):
                    molecule_id = (
                        batch_to_mol.get(well.batch_id) if well.batch_id else None
                    )
                    well_entries.append(
                        WellMapEntry(
                            well_id=well.id,
                            position=f"{well.row}{well.column}",
                            row=well.row,
                            column=well.column,
                            well_type=well.well_type,
                            batch_id=well.batch_id,
                            batch_number=(
                                batch_numbers.get(well.batch_id)
                                if well.batch_id
                                else None
                            ),
                            molecule_id=molecule_id,
                            molecule_name=(
                                mol_names.get(molecule_id) if molecule_id else None
                            ),
                            synonyms=tuple(
                                mol_synonyms.get(molecule_id, [])
                                if molecule_id
                                else ()
                            ),
                            smiles=(
                                mol_smiles.get(molecule_id) if molecule_id else None
                            ),
                            dose=well.dose,
                        )
                    )
                plates_data.append(
                    PlateMapData(
                        plate_id=plate.id,
                        plate_number=plate.plate_number,
                        format=plate.format or "",
                        wells=well_entries,
                        summary=_summarize(well_entries),
                    )
                )

        return PlateMapResult(run_id=run_id, dose_unit=dose_unit, plates=plates_data)


def _summarize(wells: list[WellMapEntry]) -> PlateMapSummary:
    """Compute a single-plate summary."""
    total_wells = len(wells)
    sample_wells = sum(1 for w in wells if w.well_type == _SAMPLE)
    control_wells = sum(
        1 for w in wells if w.well_type != _SAMPLE and w.well_type != ""
    )

    # Compounds = unique molecules represented in sample wells.
    sample_molecules = [
        w.molecule_id for w in wells
        if w.well_type == _SAMPLE and w.molecule_id is not None
    ]
    compounds = len(set(sample_molecules))

    # For each compound, the number of distinct doses and the modal
    # replicate count across (compound, dose) pairs.
    per_compound_conc: dict[uuid.UUID, set[float]] = {}
    replicate_counts: Counter[tuple[uuid.UUID, float]] = Counter()
    for w in wells:
        if w.well_type != _SAMPLE or w.molecule_id is None:
            continue
        if w.dose is None:
            continue
        per_compound_conc.setdefault(w.molecule_id, set()).add(w.dose)
        replicate_counts[(w.molecule_id, w.dose)] += 1

    if per_compound_conc:
        concentrations_per_compound = max(
            len(s) for s in per_compound_conc.values()
        )
    else:
        concentrations_per_compound = 0

    replicates = max(replicate_counts.values()) if replicate_counts else 0

    return PlateMapSummary(
        total_wells=total_wells,
        sample_wells=sample_wells,
        control_wells=control_wells,
        compounds=compounds,
        concentrations_per_compound=concentrations_per_compound,
        replicates=replicates,
    )
