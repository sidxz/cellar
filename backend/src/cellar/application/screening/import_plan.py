"""Conflict-scan helpers + plan dataclasses for run-file import.

Extracted from ``import_run_file.py`` to keep that module focused on the
use-case orchestration. ``_scan_conflicts`` walks a ``NormalizedTable``
against existing run state and produces an ``_ImportPlan`` describing
exactly what to write and what to skip — pure logic, no I/O.

``WellConflict`` and ``ReadoutConflict`` are public DTOs surfaced through
the preview/import results; the underscore-prefixed types are
implementation details consumed by ``ImportRunFile``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from cellar.application.screening.compound_ref_resolver import Resolutions
from cellar.application.screening.long_format_normalizer import (
    NormalizedTable,
    WellPosition,
)
from cellar.domain.screening_assay.enums import WellType
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.enums import PlateFormat, Qualifier
from cellar.domain.shared.value_objects import QualifiedValue

# ---------------------------------------------------------------------------
# Conflict reporting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WellConflict:
    """A row from the file refers to an existing well whose metadata
    (well_type, batch_ref, dose) differs from what the file declares.

    The whole row is skipped — neither the well nor any of its readout
    columns are written.
    """

    plate_name: str
    well_position: str  # e.g. "A12"
    reason: str  # human-readable diff


@dataclass(frozen=True)
class ReadoutConflict:
    """A specific (well, readout_def) cell already has a value persisted.

    The cell is left untouched. Other readout columns on the same row
    that don't conflict still write.
    """

    plate_name: str
    well_position: str
    readout_definition_id: uuid.UUID
    readout_name: str  # for display


# ---------------------------------------------------------------------------
# Plan dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _ReadoutWrite:
    """One readout cell to be persisted."""

    well_id: uuid.UUID
    molecule_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    readout_definition_id: uuid.UUID
    value: QualifiedValue | None
    value_text: str | None


@dataclass
class _ImportPlan:
    """Output of _scan_conflicts — what to write and what to skip."""

    new_plates: list[Plate] = field(default_factory=list)
    wells_for_new_plate: dict[uuid.UUID, list[Well]] = field(default_factory=dict)
    new_wells_for_existing_plates: list[Well] = field(default_factory=list)
    new_readouts: list[_ReadoutWrite] = field(default_factory=list)
    well_conflicts: list[WellConflict] = field(default_factory=list)
    readout_conflicts: list[ReadoutConflict] = field(default_factory=list)
    pick_list_violations: list[str] = field(default_factory=list)
    controls_from_template: int = 0
    controls_unclassified: int = 0
    create_plate_count: int = 0
    create_well_count: int = 0
    create_readout_count: int = 0


# ---------------------------------------------------------------------------
# Conflict scanning
# ---------------------------------------------------------------------------


def _scan_conflicts(
    normalized: NormalizedTable,
    run: Run,
    existing_readouts: list[ReadoutData],
    templates_by_format: dict[PlateFormat, dict[str, WellType]],
    *,
    resolutions: Resolutions | None = None,
    rd_name_by_id: dict[uuid.UUID, str] | None = None,
    pick_list_allowed: dict[uuid.UUID, set[str]] | None = None,
) -> _ImportPlan:
    """Scan a normalized file against existing run state.

    The plan is computed but no I/O happens here. ``resolutions`` carries
    the per-row outcome of the compound/batch resolver — index ``i``
    corresponds to ``normalized.rows[i]``. Pass ``None`` only for tests
    that don't care about resolution; sample rows with no resolution are
    skipped either way.

    `pick_list_allowed` carries each PICK_LIST readout-def's allowed label
    set. Values not in the set are recorded as plan.pick_list_violations
    so the preview can surface a hard error and the import can refuse the
    write.
    """
    plan = _ImportPlan()
    rd_name_by_id = rd_name_by_id or {}
    pick_list_allowed = pick_list_allowed or {}
    per_row_resolutions = resolutions.per_row if resolutions is not None else ()

    # Index existing run state.
    plates_by_name: dict[str, Plate] = {}
    for p in run.plates:
        name = (p.plate_map or {}).get("name") if p.plate_map else None
        if isinstance(name, str):
            plates_by_name[name] = p

    wells_by_plate_pos: dict[tuple[uuid.UUID, str, int], Well] = {
        (w.plate_id, w.row, w.column): w for w in run.wells
    }

    existing_readout_keys: set[tuple[uuid.UUID, uuid.UUID]] = {
        (r.well_id, r.readout_definition_id) for r in existing_readouts
    }

    next_plate_number = max((p.plate_number for p in run.plates), default=0) + 1

    # Build/reuse plates.
    for plate_name, plate_format in normalized.plate_formats.items():
        if plate_name in plates_by_name:
            continue
        new_plate = Plate(
            run_id=run.id,
            plate_number=next_plate_number,
            format=plate_format,
            plate_map={"name": plate_name},
        )
        next_plate_number += 1
        plates_by_name[plate_name] = new_plate
        plan.new_plates.append(new_plate)
        plan.wells_for_new_plate[new_plate.id] = []
        plan.create_plate_count += 1

    # Walk rows.
    for row_index, row in enumerate(normalized.rows):
        plate = plates_by_name.get(row.plate_name)
        if plate is None:
            continue  # defensive; plate_formats covered all names
        plate_format = normalized.plate_formats.get(row.plate_name)

        # Classify well type from template (canonical) else from data.
        per_well = templates_by_format.get(plate_format) if plate_format is not None else None
        tmpl_type = per_well.get(_well_key(row.well)) if per_well else None
        if tmpl_type is not None:
            file_well_type = tmpl_type
            if tmpl_type != WellType.SAMPLE:
                plan.controls_from_template += 1
        elif row.batch_ref or row.compound_ref or row.concentration is not None:
            file_well_type = WellType.SAMPLE
        else:
            file_well_type = WellType.SAMPLE
            plan.controls_unclassified += 1

        # Apply the resolver's per-row decision.
        file_batch_id: uuid.UUID | None = None
        file_molecule_id: uuid.UUID | None = None
        resolution = (
            per_row_resolutions[row_index] if row_index < len(per_row_resolutions) else None
        )
        if resolution is not None and resolution.error is None:
            file_batch_id = resolution.batch_id
            file_molecule_id = resolution.molecule_id
        elif resolution is not None and resolution.error is not None:
            # Sample rows must resolve. Control rows (mapped from the
            # plate template) don't need a batch — we keep them.
            if file_well_type == WellType.SAMPLE and (row.batch_ref or row.compound_ref):
                continue

        # Look up existing well at this position.
        well_pos_key = (plate.id, row.well.row, row.well.column)
        existing_well = wells_by_plate_pos.get(well_pos_key)

        if existing_well is None:
            # Fresh well — create.
            new_well = Well(
                plate_id=plate.id,
                row=row.well.row,
                column=row.well.column,
                well_type=file_well_type,
                batch_id=file_batch_id,
                dose=row.concentration,
            )
            wells_by_plate_pos[well_pos_key] = new_well
            target_well = new_well
            target_molecule_id = file_molecule_id
            target_batch_id = file_batch_id

            if plate in plan.new_plates:
                plan.wells_for_new_plate[plate.id].append(new_well)
            else:
                plan.new_wells_for_existing_plates.append(new_well)
            plan.create_well_count += 1
        else:
            # Well already exists — must agree with the file.
            mismatch = _well_metadata_mismatch(
                existing_well,
                file_well_type=file_well_type,
                file_batch_id=file_batch_id,
                file_dose=row.concentration,
            )
            if mismatch is not None:
                plan.well_conflicts.append(
                    WellConflict(
                        plate_name=row.plate_name,
                        well_position=_well_key(row.well),
                        reason=mismatch,
                    )
                )
                continue
            target_well = existing_well
            target_batch_id = existing_well.batch_id
            target_molecule_id = file_molecule_id  # already validated to match

        # Per-readout cell scan.
        for rd_id, value in row.readouts.items():
            cell_key = (target_well.id, rd_id)
            if cell_key in existing_readout_keys:
                plan.readout_conflicts.append(
                    ReadoutConflict(
                        plate_name=row.plate_name,
                        well_position=_well_key(row.well),
                        readout_definition_id=rd_id,
                        readout_name=rd_name_by_id.get(rd_id, ""),
                    )
                )
                continue

            if isinstance(value, str):
                # Pick-list constraint: if this readout def has an allowed
                # set, the value must be in it. Mismatch is a hard error
                # (typo'd hit class is worse than a missing batch ref;
                # there's no later opportunity to clean it up). Recorded
                # against the plan so the preview surfaces it and the
                # import refuses to commit.
                allowed = pick_list_allowed.get(rd_id)
                if allowed is not None and value not in allowed:
                    plan.pick_list_violations.append(
                        f"{row.plate_name} {_well_key(row.well)} "
                        f"'{rd_name_by_id.get(rd_id, '')}': "
                        f"value {value!r} not in allowed values "
                        f"{sorted(allowed)}"
                    )
                    continue
                plan.new_readouts.append(
                    _ReadoutWrite(
                        well_id=target_well.id,
                        molecule_id=target_molecule_id,
                        batch_id=target_batch_id,
                        readout_definition_id=rd_id,
                        value=None,
                        value_text=value,
                    )
                )
            else:
                plan.new_readouts.append(
                    _ReadoutWrite(
                        well_id=target_well.id,
                        molecule_id=target_molecule_id,
                        batch_id=target_batch_id,
                        readout_definition_id=rd_id,
                        value=QualifiedValue(value=value, qualifier=Qualifier.EQUAL),
                        value_text=None,
                    )
                )
            existing_readout_keys.add(cell_key)
            plan.create_readout_count += 1

    return plan


def _well_metadata_mismatch(
    existing: Well,
    *,
    file_well_type: WellType,
    file_batch_id: uuid.UUID | None,
    file_dose: float | None,
) -> str | None:
    """Return a human-readable mismatch description, or None if compatible.

    A None value on the file side is treated as "no opinion" — only
    explicit value disagreements count as a mismatch. This keeps imports
    additive when the chemist's second file omits already-set fields.
    """
    diffs: list[str] = []
    if existing.well_type != file_well_type:
        diffs.append(f"well_type {existing.well_type.value} vs file {file_well_type.value}")
    if file_batch_id is not None and existing.batch_id != file_batch_id:
        diffs.append("batch_ref differs")
    if file_dose is not None and existing.dose is not None:
        # Tolerant float compare — same dose at different precision is fine.
        if abs(existing.dose - file_dose) > 1e-9:
            diffs.append(f"dose {existing.dose} vs file {file_dose}")
    if not diffs:
        return None
    return "; ".join(diffs)


def _well_key(well: WellPosition) -> str:
    return f"{well.row}{well.column}"
