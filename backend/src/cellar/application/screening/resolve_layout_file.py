"""ResolveLayoutFile: read a labelling layout file and resolve its compounds and batches.

The file has a Position column and any of Label, Role, Compound, Batch,
Concentration (the header may name the unit) and Note, and Use. One row comes
back per file row with its parsed values, the compound and batch it resolved,
and the problems found on that row. Writes nothing; matching rows to the
table's positions is the browser's job.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.instrument_export import MAX_INSTRUMENT_FILE_BYTES
from cellar.application.screening.layout_compound_resolver import (
    LayoutCompound,
    LayoutCompoundResolver,
)
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.enums import WellType
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

ROLE_NAMES: Mapping[str, WellType] = {
    "sample": WellType.SAMPLE,
    "reference": WellType.REFERENCE,
    "blank": WellType.BLANK,
    "positive control": WellType.POSITIVE_CONTROL,
    "negative control": WellType.NEGATIVE_CONTROL,
}
MAX_LAYOUT_ROWS = 2000
# The template has 8 columns; anything wider is not a layout file. A spreadsheet is
# also refused above this size unpacked, before the spreadsheet library opens it.
MAX_LAYOUT_COLUMNS = 64
MAX_LAYOUT_UNPACKED_BYTES = 50 * 1024 * 1024
_MAX_LABEL = 200
_MAX_NOTE = 1000
_COLUMNS = ("position", "label", "role", "compound", "batch", "note", "use")
_CALCULATED_COLUMNS = ("role", "compound", "batch", "concentration")
# The template writes ' before a cell starting with one of these, so a spreadsheet
# program keeps it as text instead of running it as a formula; reading drops that one '.
_FORMULA_START = ("=", "+", "-", "@")
# Concentration too: the template writes the table's text, so "+5" goes out as '+5.
_GUARDED_COLUMNS = ("position", "label", "compound", "batch", "concentration", "note")


@dataclass(frozen=True)
class LayoutRow:
    """One file row. A value is None when its cell was empty, its column absent, or it had a problem."""  # noqa: E501

    position: str
    label: str | None
    note: str | None
    well_type: WellType | None
    dose: float | None
    use: bool | None
    compound: LayoutCompound | None
    problems: tuple[str, ...]


@dataclass(frozen=True)
class LayoutFile:
    rows: tuple[LayoutRow, ...]
    unrecognised_columns: tuple[str, ...]
    # The run's role, compound, batch and concentration cannot change, and the file
    # had a non-empty cell in one of those columns, valid or not.
    calculated_columns_ignored: bool


@dataclass(frozen=True, kw_only=True)
class ResolveLayoutFileQuery(Query):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    filename: str
    content: bytes


class ResolveLayoutFile:
    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
        parser: TabularParser,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._parser = parser

    async def __call__(
        self, input: ResolveLayoutFileQuery, auth: AuthContext | None = None
    ) -> Result[LayoutFile, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            if len(input.content) > MAX_INSTRUMENT_FILE_BYTES:
                return Failure(ValidationError("File is larger than 20 MB"))
            try:
                table = self._parser.parse(
                    input.content,
                    input.filename,
                    max_rows=MAX_LAYOUT_ROWS,
                    max_columns=MAX_LAYOUT_COLUMNS,
                    max_uncompressed_bytes=MAX_LAYOUT_UNPACKED_BYTES,
                    # The template's leading apostrophes are text, never quotes.
                    quotechar='"',
                )
            except TabularParseError as exc:
                return Failure(ValidationError(str(exc)))

            columns: dict[str, str] = {}
            unrecognised: list[str] = []
            for header in table.headers:
                key = header.strip().casefold()
                if not key:
                    continue
                if key.startswith("concentration"):
                    key = "concentration"
                if key in _COLUMNS or key == "concentration":
                    columns.setdefault(key, header)
                else:
                    unrecognised.append(header.strip())
            if "position" not in columns:
                return Failure(ValidationError("The file has no Position column"))
            if table.row_count > MAX_LAYOUT_ROWS:
                return Failure(ValidationError(f"The file has more than {MAX_LAYOUT_ROWS} rows"))

            resolver = LayoutCompoundResolver(
                input.workspace_id, self._molecule_repo, self._batch_repo
            )
            # Where those columns cannot change, their problems are not worth listing.
            report_calculated = run.calculated_positions_editable
            rows = []
            ignored = False
            for raw in table.iter_rows():
                cells = {key: raw.get(header, "").strip() for key, header in columns.items()}
                for key in _GUARDED_COLUMNS:
                    if key in cells:
                        cells[key] = _without_formula_guard(cells[key])
                rows.append(await _row(cells, resolver, report_calculated=report_calculated))
                ignored = ignored or (
                    not report_calculated and any(cells.get(k) for k in _CALCULATED_COLUMNS)
                )

        return Success(
            LayoutFile(
                rows=tuple(rows),
                unrecognised_columns=tuple(unrecognised),
                calculated_columns_ignored=ignored,
            )
        )


def _without_formula_guard(text: str) -> str:
    return text[1:] if text[:1] == "'" and text[1:2] in _FORMULA_START else text


async def _row(
    cells: dict[str, str], resolver: LayoutCompoundResolver, *, report_calculated: bool = True
) -> LayoutRow:
    """``report_calculated`` off leaves out the problems of role, compound, batch and
    concentration; their values are still read."""
    problems: list[str] = []
    calculated = problems if report_calculated else []

    def text(key: str, limit: int, name: str) -> str | None:
        value = cells.get(key) or None
        if value is not None and len(value) > limit:
            problems.append(f"{name} is longer than {limit} characters")
            return None
        return value

    label = text("label", _MAX_LABEL, "Label")

    well_type = None
    if role := cells.get("role"):
        well_type = ROLE_NAMES.get(" ".join(role.split()).casefold())
        if well_type is None:
            calculated.append(
                f"Unknown role '{role}'. Use Sample, Reference, Blank, "
                "Positive control or Negative control"
            )

    dose = None
    if concentration := cells.get("concentration"):
        try:
            # float() also reads "1_000" and digits of other scripts; a cell is not that.
            dose = (
                float(concentration)
                if concentration.isascii() and "_" not in concentration
                else None
            )
        except ValueError:
            dose = None
        if dose is None or not math.isfinite(dose) or dose < 0:
            dose = None
            calculated.append("Concentration must be a number, 0 or more")

    note = text("note", _MAX_NOTE, "Note")

    use = None
    if use_text := cells.get("use"):
        use = {"yes": True, "no": False}.get(use_text.casefold())
        if use is None:
            problems.append("Use must be Yes or No")

    compound = await resolver(cells.get("compound", ""), cells.get("batch", ""), calculated)
    return LayoutRow(
        position=cells.get("position", ""),
        label=label,
        note=note,
        well_type=well_type,
        dose=dose,
        use=use,
        compound=compound,
        problems=tuple(problems),
    )
