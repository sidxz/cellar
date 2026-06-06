"""Export a registered plate's well-map as a round-trippable layout file.

Emits the exact columns the well-mapping import reads — ``Well, Batch Number,
Concentration, Unit, Role`` — so a plate can be exported, edited in a
spreadsheet, and re-imported losslessly. Batch references are resolved from the
stored UUID back to the human-readable batch number.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass

from openpyxl import Workbook
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import BatchRepository, RegisteredPlateRepository
from cellar.domain.shared.errors import DomainError, NotFoundError

_COLUMNS = ["Well", "Batch Number", "Concentration", "Unit", "Role"]


@dataclass(frozen=True, kw_only=True)
class ExportPlateLayoutQuery(Query):
    workspace_id: uuid.UUID
    plate_id: uuid.UUID


@dataclass(frozen=True)
class PlateLayoutRow:
    well: str
    batch_number: str
    concentration_value: float | None
    concentration_unit: str | None
    well_type: str


@dataclass(frozen=True)
class PlateLayoutExport:
    barcode: str
    rows: list[PlateLayoutRow]


def _well_sort_key(pos: str) -> tuple[int, str, int]:
    """Order wells A1, A2, … then B1 … (row length first so Z < AA)."""
    m = re.match(r"^([A-Z]+)(\d+)$", pos)
    if not m:
        return (99, pos, 0)
    return (len(m.group(1)), m.group(1), int(m.group(2)))


class ExportPlateLayout:
    """Build the round-trippable well-map rows for a registered plate."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: RegisteredPlateRepository,
        batch_repo: BatchRepository,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._batch_repo = batch_repo

    async def __call__(
        self, input: ExportPlateLayoutQuery, auth: AuthContext | None = None
    ) -> Result[PlateLayoutExport, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            plate = await self._repo.find_by_id_in_workspace(input.workspace_id, input.plate_id)
            if plate is None:
                return Failure(NotFoundError("RegisteredPlate", str(input.plate_id)))

            # Resolve well batch UUIDs back to human-readable batch numbers.
            batch_ids = list(
                {wa.batch_id for wa in plate.well_map.values() if wa.batch_id is not None}
            )
            batches = (
                await self._batch_repo.find_by_ids(input.workspace_id, batch_ids)
                if batch_ids
                else []
            )
            number_by_id = {b.id: b.batch_number.value for b in batches}

            rows: list[PlateLayoutRow] = []
            for pos in sorted(plate.well_map, key=_well_sort_key):
                wa = plate.well_map[pos]
                rows.append(
                    PlateLayoutRow(
                        well=pos,
                        batch_number=(number_by_id.get(wa.batch_id, "") if wa.batch_id else ""),
                        concentration_value=(wa.concentration.value if wa.concentration else None),
                        concentration_unit=(
                            wa.concentration.unit.value if wa.concentration else None
                        ),
                        well_type=wa.well_type.value,
                    )
                )

            return Success(PlateLayoutExport(barcode=plate.barcode.value, rows=rows))


# ---------------------------------------------------------------------------
# Renderers — rows -> file bytes (round-trippable column layout)
# ---------------------------------------------------------------------------


def _cells(row: PlateLayoutRow) -> list[object]:
    return [
        row.well,
        row.batch_number,
        "" if row.concentration_value is None else row.concentration_value,
        row.concentration_unit or "",
        row.well_type,
    ]


def render_csv(rows: list[PlateLayoutRow]) -> bytes:
    """Render rows to CSV bytes (utf-8-sig so Excel opens it cleanly)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_COLUMNS)
    for row in rows:
        writer.writerow(_cells(row))
    return buf.getvalue().encode("utf-8-sig")


def render_xlsx(rows: list[PlateLayoutRow]) -> bytes:
    """Render rows to an XLSX workbook's bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Well Map"
    ws.append(_COLUMNS)
    for row in rows:
        ws.append(_cells(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
