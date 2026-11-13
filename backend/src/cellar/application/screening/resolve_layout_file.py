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
from cellar.application.inventory.resolve_batch_ref import resolve_batch_ref
from cellar.application.screening.instrument_export import MAX_INSTRUMENT_FILE_BYTES
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.batch import Batch
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
_MAX_LABEL = 200
_MAX_NOTE = 1000
_COLUMNS = ("position", "label", "role", "compound", "batch", "note", "use")
# The template writes ' before a text cell starting with one of these, so a spreadsheet
# program keeps it as text instead of running it as a formula; reading drops that one '.
_FORMULA_START = ("=", "+", "-", "@")
_TEXT_COLUMNS = ("position", "label", "compound", "batch", "note")


@dataclass(frozen=True)
class LayoutCompound:
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    batch_id: uuid.UUID | None
    batch_number: str | None
    needs_batch_choice: bool


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

            resolver = _Resolver(input.workspace_id, self._molecule_repo, self._batch_repo)
            # Where those columns cannot change, their problems are not worth listing.
            report_calculated = run.calculated_positions_editable
            rows = []
            for raw in table.iter_rows():
                cells = {key: raw.get(header, "").strip() for key, header in columns.items()}
                for key in _TEXT_COLUMNS:
                    if key in cells:
                        cells[key] = _without_formula_guard(cells[key])
                rows.append(await _row(cells, resolver, report_calculated=report_calculated))

        return Success(LayoutFile(rows=tuple(rows), unrecognised_columns=tuple(unrecognised)))


def _without_formula_guard(text: str) -> str:
    return text[1:] if text[:1] == "'" and text[1:2] in _FORMULA_START else text


async def _row(
    cells: dict[str, str], resolver: _Resolver, *, report_calculated: bool = True
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


class _Resolver:
    """Compound and Batch text -> LayoutCompound, one lookup per distinct text and molecule."""

    def __init__(
        self, ws: uuid.UUID, molecule_repo: MoleculeRepository, batch_repo: BatchRepository
    ) -> None:
        self._ws = ws
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._molecules: dict[str, Molecule | None] = {}
        self._molecules_by_id: dict[uuid.UUID, Molecule | None] = {}
        self._batches: dict[str, Batch | None] = {}
        self._batches_of: dict[uuid.UUID, list[Batch]] = {}

    async def __call__(
        self, compound_text: str, batch_text: str, problems: list[str]
    ) -> LayoutCompound | None:
        molecule = await self._molecule(compound_text) if compound_text else None
        batch = await self._batch(batch_text) if batch_text else None
        missing = False
        if compound_text and molecule is None:
            problems.append(f"Compound '{compound_text}' was not found")
            missing = True
        if batch_text and batch is None:
            problems.append(f"Batch '{batch_text}' was not found")
            missing = True
        if missing:
            return None

        if batch is not None:
            if molecule is None:
                molecule = await self._molecule_by_id(batch.molecule_id)
                if molecule is None:
                    problems.append(f"Batch '{batch_text}' was not found")
                    return None
            elif batch.molecule_id != molecule.id:
                problems.append(
                    f"Batch '{batch_text}' does not belong to compound '{compound_text}'"
                )
                return None
            return _compound(molecule, batch, needs_batch_choice=False)

        if molecule is None:
            return None
        batches = await self._batches_of_molecule(molecule.id)
        if len(batches) == 1:
            return _compound(molecule, batches[0], needs_batch_choice=False)
        return _compound(molecule, None, needs_batch_choice=len(batches) > 1)

    async def _molecule(self, text: str) -> Molecule | None:
        if text not in self._molecules:
            found = await self._molecule_repo.find_by_registration_number(self._ws, text)
            if found is None:
                found = await self._molecule_repo.find_by_identifier(self._ws, text)
            self._molecules[text] = found
        return self._molecules[text]

    async def _molecule_by_id(self, molecule_id: uuid.UUID) -> Molecule | None:
        if molecule_id not in self._molecules_by_id:
            self._molecules_by_id[molecule_id] = await self._molecule_repo.find_by_id_in_workspace(
                self._ws, molecule_id
            )
        return self._molecules_by_id[molecule_id]

    async def _batch(self, text: str) -> Batch | None:
        if text not in self._batches:
            self._batches[text] = await resolve_batch_ref(self._batch_repo, self._ws, text)
        return self._batches[text]

    async def _batches_of_molecule(self, molecule_id: uuid.UUID) -> list[Batch]:
        if molecule_id not in self._batches_of:
            self._batches_of[molecule_id] = await self._batch_repo.find_by_molecule(
                self._ws, molecule_id
            )
        return self._batches_of[molecule_id]


def _compound(
    molecule: Molecule, batch: Batch | None, *, needs_batch_choice: bool
) -> LayoutCompound:
    return LayoutCompound(
        molecule_id=molecule.id,
        molecule_name=molecule.name,
        registration_number=molecule.registration_number.value,
        batch_id=batch.id if batch is not None else None,
        batch_number=batch.batch_number.value if batch is not None else None,
        needs_batch_choice=needs_batch_choice,
    )
