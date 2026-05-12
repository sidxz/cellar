"""Plate setup use cases — file parsing and well creation for screening runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    RefType,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.enums import ReadoutDataType, WellType
from cellar.domain.screening_assay.repository import ProtocolRepository, RunRepository
from cellar.domain.screening_assay.run import Plate, Well
from cellar.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.application.shared.parsers import (
    ParsedTable,
    TabularParseError,
    TabularParser,
)

# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------

_DEFAULT_DOSE_SERIES = [10_000.0 / (3**i) for i in range(10)]
"""Default 10-point, 3-fold dilution from 10 uM (in nM)."""


@dataclass(frozen=True)
class CompoundAssignment:
    """A compound mapped to specific well positions on a plate."""

    molecule_ref: str
    batch_ref: str | None = None
    well_positions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPlateMap:
    """Result of parsing a plate map CSV file."""

    assignments: list[CompoundAssignment]
    unresolved: list[str]
    row_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_range(start: str, end: str) -> list[str]:
    """Return uppercase row letters from start to end (inclusive).

    Supports single-character rows A-Z.
    """
    s = ord(start.upper())
    e = ord(end.upper())
    if s > e:
        s, e = e, s
    return [chr(c) for c in range(s, e + 1)]


def _normalize_header(h: str) -> str:
    """Lowercase, strip whitespace/underscores for fuzzy header matching."""
    return h.strip().lower().replace("_", "").replace(" ", "")


# ---------------------------------------------------------------------------
# ParsePlateMapFile — pure function, no DB
# ---------------------------------------------------------------------------


class ParsePlateMapFile:
    """Parse a plate map file into compound-to-well assignments.

    Accepts CSV or XLSX content (detected by ``filename`` extension and
    magic bytes). Supports two layouts:

    - **Well-level**: columns ``Well, Compound`` — each row is one well.
    - **Row-range**: columns ``Compound, Start Row, End Row`` — compound
      assigned to all wells in those rows (columns generated later by
      SetUpRunPlate based on concentration series length).
    """

    def __init__(self, parser: TabularParser) -> None:
        self._parser = parser

    async def __call__(
        self,
        file_content: bytes | str,
        filename: str = "",
        auth: AuthContext | None = None,
    ) -> Result[ParsedPlateMap, DomainError]:
        require_editor(auth)
        if isinstance(file_content, str):
            file_content = file_content.encode("utf-8")

        try:
            table = self._parser.parse(file_content, filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        headers = {_normalize_header(h): h for h in table.headers}

        if "well" in headers and "compound" in headers:
            return self._parse_well_level(table, headers)
        if "compound" in headers and "startrow" in headers and "endrow" in headers:
            return self._parse_row_range(table, headers)
        return Failure(
            ValidationError(
                "File must have either [Well, Compound] or [Compound, Start Row, End Row] columns"
            )
        )

    def _parse_well_level(
        self,
        table: ParsedTable,
        headers: dict[str, str],
    ) -> Result[ParsedPlateMap, DomainError]:
        """Parse well-level format: Well, Compound columns."""
        well_col = headers["well"]
        compound_col = headers["compound"]

        compound_wells: dict[str, list[str]] = {}
        row_count = 0
        for row in table.iter_rows():
            row_count += 1
            compound = (row.get(compound_col) or "").strip()
            well = (row.get(well_col) or "").strip().upper()
            if not compound or not well:
                continue
            compound_wells.setdefault(compound, []).append(well)

        assignments = [
            CompoundAssignment(molecule_ref=name, well_positions=positions)
            for name, positions in compound_wells.items()
        ]
        return Success(ParsedPlateMap(assignments=assignments, unresolved=[], row_count=row_count))

    def _parse_row_range(
        self,
        table: ParsedTable,
        headers: dict[str, str],
    ) -> Result[ParsedPlateMap, DomainError]:
        """Parse row-range format: Compound, Start Row, End Row columns."""
        compound_col = headers["compound"]
        start_col = headers["startrow"]
        end_col = headers["endrow"]

        assignments: list[CompoundAssignment] = []
        row_count = 0
        for row in table.iter_rows():
            row_count += 1
            compound = (row.get(compound_col) or "").strip()
            start_row = (row.get(start_col) or "").strip()
            end_row = (row.get(end_col) or "").strip()
            if not compound or not start_row or not end_row:
                continue

            if not start_row.isalpha() or not end_row.isalpha():
                continue

            rows = _row_range(start_row, end_row)
            assignments.append(
                CompoundAssignment(
                    molecule_ref=compound,
                    well_positions=[f"{r}" for r in rows],
                )
            )

        return Success(ParsedPlateMap(assignments=assignments, unresolved=[], row_count=row_count))


# ---------------------------------------------------------------------------
# SetUpRunPlate — creates wells on a run
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SetUpRunPlateCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    plate_number: int = 1
    compound_assignments: list[CompoundAssignment]
    # Dose values in the protocol's dose_unit. The unit is NOT specified per
    # request — it lives on Protocol.dose_unit (single source of truth).
    concentration_series: list[float] | None = None


class SetUpRunPlate:
    """Create wells on a run plate from compound assignments and dose series.

    Flow:
    1. Load Run (must not be locked)
    2. Load Protocol -> find DoseResponseConfig -> get default dose series
    3. Resolve molecules via MoleculeResolver
    4. For each compound: resolve first batch via BatchRepository
    5. For each compound x well position: create Well with concentration
    6. Create Plate, add wells, save run
    """

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        batch_repo: BatchRepository,
        molecule_resolver: MoleculeResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._batch_repo = batch_repo
        self._molecule_resolver = molecule_resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: SetUpRunPlateCommand,
        auth: AuthContext | None = None,
    ) -> Result[dict, DomainError]:
        if auth is None:
            return Failure(AuthorizationError("Authentication required"))
        require_editor(auth)

        async with self._uow:
            # 1. Load run
            run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))

            # 2. Load protocol -> find dose response config for default series
            conc_series = input.concentration_series
            if conc_series is None:
                protocol = await self._protocol_repo.find_by_id_in_workspace(
                    input.workspace_id, run.protocol_id
                )
                if protocol is not None:
                    conc_series = self._extract_dose_series(protocol)
            if conc_series is None:
                conc_series = list(_DEFAULT_DOSE_SERIES)

            # 3. Resolve molecules
            refs = [
                MoleculeReference(
                    value=a.molecule_ref,
                    ref_type=RefType.NAME,
                )
                for a in input.compound_assignments
            ]
            resolved, unresolved_mols = await self._molecule_resolver.resolve(
                input.workspace_id, refs
            )

            # Build lookup: molecule_ref -> molecule_id
            ref_to_mol: dict[str, uuid.UUID] = {r.ref.value: r.molecule_id for r in resolved}
            unresolved_names = [u.ref.value for u in unresolved_mols]

            # 4. For each resolved compound, find first batch
            mol_to_batch: dict[uuid.UUID, uuid.UUID] = {}
            for mol_id in ref_to_mol.values():
                if mol_id not in mol_to_batch:
                    batches = await self._batch_repo.find_by_molecule(input.workspace_id, mol_id)
                    if batches:
                        mol_to_batch[mol_id] = batches[0].id

            # 5. Create wells
            plate = Plate(run_id=run.id, plate_number=input.plate_number)
            wells: list[Well] = []
            compounds_assigned = 0

            for assignment in input.compound_assignments:
                mol_id = ref_to_mol.get(assignment.molecule_ref)
                if mol_id is None:
                    continue  # skip unresolved

                batch_id = mol_to_batch.get(mol_id)
                compounds_assigned += 1

                for i, pos in enumerate(assignment.well_positions):
                    row, column = self._parse_position(pos, i, conc_series)
                    conc_value = conc_series[i % len(conc_series)]

                    wells.append(
                        Well(
                            plate_id=plate.id,
                            row=row,
                            column=column,
                            well_type=WellType.SAMPLE,
                            batch_id=batch_id,
                            dose=conc_value,
                        )
                    )

            # 6. Add wells to plate, add plate to run, save
            plate.wells = wells  # type: ignore[attr-defined]
            run.add_plate(plate)
            await self._run_repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            {
                "plate_id": plate.id,
                "wells_created": len(wells),
                "compounds_assigned": compounds_assigned,
                "unresolved": unresolved_names,
            }
        )

    @staticmethod
    def _extract_dose_series(protocol) -> list[float] | None:
        """Extract dose series from protocol's DoseResponseConfig, if any."""
        for rd in protocol.readout_definitions:
            if rd.data_type == ReadoutDataType.DOSE_RESPONSE:
                # DoseResponseConfig doesn't carry a series itself;
                # use the default series
                return None
        return None

    @staticmethod
    def _parse_position(pos: str, index: int, conc_series: list[float]) -> tuple[str, int]:
        """Parse a well position string into (row, column).

        If the position is a single row letter (from row-range format),
        generate a column from the concentration series index.
        If it's a full well position like 'A1', parse row and column.
        """
        pos = pos.strip().upper()

        # Full well position (e.g., "A1", "B12")
        if len(pos) >= 2 and pos[0].isalpha() and pos[1:].isdigit():
            return pos[0], int(pos[1:])

        # Two-letter row + number (e.g., "AA1")
        if len(pos) >= 3 and pos[:2].isalpha() and pos[2:].isdigit():
            return pos[:2], int(pos[2:])

        # Row letter only (from row-range format) — generate column
        if pos.isalpha():
            col = (index % len(conc_series)) + 1
            return pos, col

        # Fallback: treat as row A, column from index
        return "A", index + 1
