"""Plate mapper — maps CDD plate JSON to internal plate DTOs.

Pure mapping logic, no I/O. Converts 0-indexed row/col to
A1-style well positions and infers plate format from dimensions.

Field extraction is driven by ``EntityMapping`` config from the
DataSource aggregate — no hardcoded source field names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cellar.application.cdd_import.molecule_mapper import _collect_fields, _resolve_field
from cellar.domain.workspace_config.data_source import EntityMapping


@dataclass
class MappedWell:
    """A single well extracted from plate data."""

    position: str  # e.g. "A1", "H12"
    cdd_batch_id: int | None = None


@dataclass
class MappedPlate:
    """A plate record mapped for registration."""

    cdd_plate_id: int
    name: str
    format: str  # e.g. "96", "384"
    wells: list[MappedWell] = field(default_factory=list)
    cdd_statistics: list[dict[str, Any]] = field(default_factory=list)


def map_cdd_plate(
    raw: dict[str, Any],
    plate_mapping: EntityMapping,
    well_mapping: EntityMapping | None = None,
) -> MappedPlate:
    """Map a single plate JSON object to a MappedPlate DTO."""
    cdd_plate_id: int = _resolve_field(raw, plate_mapping.id_field) or 0

    core, _ = _collect_fields(raw, plate_mapping)
    name: str = core.get("barcode") or core.get("plate_label") or ""
    statistics: list[dict[str, Any]] = raw.get("statistics") or []

    # Map wells via well_mapping.parent_path
    mapped_wells: list[MappedWell] = []
    max_row = 0
    max_col = 0

    if well_mapping:
        wells_raw: list[dict[str, Any]] = (
            _resolve_field(raw, well_mapping.parent_path) if well_mapping.parent_path else []
        ) or []

        for well_obj in wells_raw:
            well_core, _ = _collect_fields(well_obj, well_mapping)
            row: int = int(well_core.get("row", 0) or 0)
            col: int = int(well_core.get("col", 0) or 0)
            cdd_batch_id = well_core.get("cdd_batch_id")

            max_row = max(max_row, row)
            max_col = max(max_col, col)

            position = _row_col_to_position(row, col)
            mapped_wells.append(MappedWell(position=position, cdd_batch_id=cdd_batch_id))

    plate_format = _infer_format(max_row, max_col)

    return MappedPlate(
        cdd_plate_id=cdd_plate_id,
        name=name,
        format=plate_format,
        wells=mapped_wells,
        cdd_statistics=statistics,
    )


def _row_col_to_position(row: int, col: int) -> str:
    """Convert 0-indexed row/col integers to A1-style position.

    row=0 -> A, row=1 -> B, ..., row=25 -> Z, row=26 -> AA
    col=0 -> 1, col=1 -> 2, ...
    """
    row_str = _int_to_row_letter(row)
    col_str = str(col + 1)
    return f"{row_str}{col_str}"


def _int_to_row_letter(row: int) -> str:
    """Convert 0-indexed row to letter(s): 0->A, 25->Z, 26->AA, 31->AF."""
    if row < 26:
        return chr(ord("A") + row)
    first = chr(ord("A") + (row // 26) - 1)
    second = chr(ord("A") + (row % 26))
    return f"{first}{second}"


def _infer_format(max_row: int, max_col: int) -> str:
    """Infer plate format from max row/col (0-indexed).

    Standard formats:
        6-well:    2 rows (0-1) x 3 cols (0-2)
        12-well:   3 rows (0-2) x 4 cols (0-3)
        24-well:   4 rows (0-3) x 6 cols (0-5)
        48-well:   6 rows (0-5) x 8 cols (0-7)
        96-well:   8 rows (0-7) x 12 cols (0-11)
        384-well:  16 rows (0-15) x 24 cols (0-23)
        1536-well: 32 rows (0-31) x 48 cols (0-47)
    """
    rows = max_row + 1
    cols = max_col + 1

    if rows <= 2 and cols <= 3:
        return "6"
    if rows <= 3 and cols <= 4:
        return "12"
    if rows <= 4 and cols <= 6:
        return "24"
    if rows <= 6 and cols <= 8:
        return "48"
    if rows <= 8 and cols <= 12:
        return "96"
    if rows <= 16 and cols <= 24:
        return "384"
    return "1536"
