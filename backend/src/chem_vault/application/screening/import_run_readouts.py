"""ImportRunReadouts — simplified CSV import for runs with wells already set up.

Imports readout data from a simple CSV where each row maps a well position
to one or more measured values.  Wells must already exist on the run (created
by SetUpRunPlate).  batch_id and molecule_id are inherited from the well.

Supported CSV formats
---------------------
Single-value (readout_definition_id supplied in the command):

    Well,Value
    A1,2.3
    A2,5.1

Multi-column (column headers matched to readout definition names):

    Well,% Inhibition,Absorbance
    A1,2.3,0.95
    A2,5.1,0.88
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from chem_vault.domain.shared.enums import Qualifier
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.shared.value_objects import QualifiedValue


# ---------------------------------------------------------------------------
# Command / Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ImportRunReadoutsCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    csv_content: bytes
    # For single-value CSVs (column header "Value") supply the definition id.
    readout_definition_id: uuid.UUID | None = None


@dataclass
class ImportRunReadoutsResult:
    total_rows: int = 0
    matched: int = 0
    unmatched: int = 0
    readouts_created: int = 0


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class ImportRunReadouts:
    """Import readout data from a CSV into an existing run with wells set up.

    Batch_id is taken from the well.  molecule_id is resolved via the batch
    repository (one DB call per unique batch, cached).  If the batch cannot
    be found the readout is skipped and counted as *unmatched*.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_data_repo: ReadoutDataRepository,
        batch_repo: BatchRepository,
        dispatcher: EventDispatcherProtocol | None = None,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ImportRunReadoutsCommand,
        auth: AuthContext | None = None,
    ) -> Result[ImportRunReadoutsResult, DomainError]:
        try:
            require_editor(auth)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            return await self._execute(input)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute(
        self, cmd: ImportRunReadoutsCommand
    ) -> Result[ImportRunReadoutsResult, DomainError]:
        # 1. Load run -------------------------------------------------------
        run = await self._run_repo.find_by_id_in_workspace(
            cmd.workspace_id, cmd.run_id
        )
        if run is None:
            return Failure(NotFoundError("Run", str(cmd.run_id)))

        # 2. Require wells ---------------------------------------------------
        if not run.wells:
            return Failure(
                ValidationError(
                    "Run has no wells set up — use SetUpRunPlate before importing readout data"
                )
            )

        # 3. Load protocol for readout definition lookup --------------------
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            cmd.workspace_id, run.protocol_id
        )
        if protocol is None:
            return Failure(NotFoundError("Protocol", str(run.protocol_id)))

        # Build a case-insensitive name → id map for readout definitions
        rd_by_name: dict[str, uuid.UUID] = {
            rd.name.lower(): rd.id for rd in protocol.readout_definitions
        }

        # 4. Build well position → well lookup ------------------------------
        # Position string: row + column as string, e.g. "A1", "H12"
        well_by_pos: dict[str, object] = {
            f"{w.row}{w.column}": w for w in run.wells
        }

        # 5. Parse CSV -------------------------------------------------------
        try:
            text = cmd.csv_content.decode("utf-8-sig")  # handle BOM
        except UnicodeDecodeError:
            text = cmd.csv_content.decode("latin-1")

        try:
            rows, headers = _parse_csv(text)
        except Exception as exc:
            return Failure(ValidationError(f"CSV parse error: {exc}"))

        if not headers:
            return Failure(ValidationError("CSV has no headers"))

        # Normalise headers to lowercase for matching
        lower_headers = [h.lower() for h in headers]
        if "well" not in lower_headers:
            return Failure(ValidationError("CSV must have a 'Well' column"))

        well_col_idx = lower_headers.index("well")

        # Identify value columns and map to readout definition ids
        # Special case: a column named "value" (case-insensitive) maps to
        # readout_definition_id supplied in the command (single-value mode).
        col_to_rd_id: dict[int, uuid.UUID] = {}
        for idx, lower_hdr in enumerate(lower_headers):
            if idx == well_col_idx:
                continue
            if lower_hdr == "value":
                if cmd.readout_definition_id is not None:
                    col_to_rd_id[idx] = cmd.readout_definition_id
                # else: skip unnamed value column without an explicit id
            else:
                rd_id = rd_by_name.get(lower_hdr)
                if rd_id is not None:
                    col_to_rd_id[idx] = rd_id
                # Unmatched column headers are silently skipped

        if not col_to_rd_id:
            return Failure(
                ValidationError(
                    "No CSV columns could be matched to readout definitions. "
                    "Column headers must match readout definition names (case-insensitive), "
                    "or use 'Value' with readout_definition_id supplied."
                )
            )

        # 6. Process rows ----------------------------------------------------
        result = ImportRunReadoutsResult()
        # Cache batch → molecule_id lookups
        mol_by_batch: dict[uuid.UUID, uuid.UUID | None] = {}

        entities: list[ReadoutData] = []

        for row in rows:
            result.total_rows += 1

            # Get well position from this row
            raw_pos = row[well_col_idx].strip().upper() if row[well_col_idx] else ""
            if not raw_pos:
                result.unmatched += 1
                continue

            well = well_by_pos.get(raw_pos)
            if well is None:
                result.unmatched += 1
                continue

            result.matched += 1

            # Resolve molecule_id from batch
            if well.batch_id is None:
                # Control wells have no batch — skip value import
                continue

            if well.batch_id not in mol_by_batch:
                batch = await self._batch_repo.find_by_id_in_workspace(
                    cmd.workspace_id, well.batch_id
                )
                mol_by_batch[well.batch_id] = batch.molecule_id if batch is not None else None

            molecule_id = mol_by_batch[well.batch_id]
            if molecule_id is None:
                # Batch not found — skip this well
                continue

            # Create readout entities for each value column
            for col_idx, rd_id in col_to_rd_id.items():
                if col_idx >= len(row):
                    continue
                raw_val = row[col_idx].strip() if row[col_idx] else ""
                if not raw_val:
                    continue

                try:
                    numeric = float(raw_val)
                except ValueError:
                    continue  # non-numeric value in a numeric column — skip

                entities.append(
                    ReadoutData(
                        workspace_id=cmd.workspace_id,
                        run_id=cmd.run_id,
                        well_id=well.id,
                        molecule_id=molecule_id,
                        batch_id=well.batch_id,
                        readout_definition_id=rd_id,
                        value=QualifiedValue(value=numeric, qualifier=Qualifier.EQUAL),
                    )
                )
                result.readouts_created += 1

        # 7. Persist --------------------------------------------------------
        if entities:
            await self._readout_data_repo.save_bulk(entities)

        events = await self._uow.commit()

        if self._dispatcher and events:
            await self._dispatcher.dispatch_all(events)
        return Success(result)


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _parse_csv(text: str) -> tuple[list[list[str]], list[str]]:
    """Parse CSV content, auto-detecting delimiter.

    Returns (rows, headers) where rows is a list of string lists
    (one per data row, NOT including the header) and headers is
    the first row's fields.
    """
    if not text.strip():
        return [], []

    # Sniff for delimiter; fall back to comma
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # type: ignore[assignment]

    reader = csv.reader(io.StringIO(text), dialect)
    all_rows = list(reader)

    if not all_rows:
        return [], []

    headers = [h.strip() for h in all_rows[0]]
    data_rows = [[cell.strip() for cell in r] for r in all_rows[1:] if any(c.strip() for c in r)]
    return data_rows, headers
