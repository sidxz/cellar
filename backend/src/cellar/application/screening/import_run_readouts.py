"""ImportRunReadouts — simplified import for runs with wells already set up.

Imports readout data from a CSV or XLSX file where each row maps a well
position to one or more measured values.  Wells must already exist on the
run (created by SetUpRunPlate).  batch_id and molecule_id are inherited
from the well.

Supported file formats
----------------------
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

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import QualifiedValue

# ---------------------------------------------------------------------------
# Command / Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ImportRunReadoutsCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    file_content: bytes
    # Original filename — used to detect xlsx vs csv. Empty defaults to csv.
    filename: str = ""
    # For single-value files (column header "Value") supply the definition id.
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
        parser: TabularParser,
        dispatcher: EventDispatcherProtocol | None = None,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._parser = parser
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ImportRunReadoutsCommand,
        auth: AuthContext | None = None,
    ) -> Result[ImportRunReadoutsResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        events: list = []
        async with self._uow:
            result = await self._execute(input)
            if isinstance(result, Success):
                events = await self._uow.commit()

        if self._dispatcher and events:
            await self._dispatcher.dispatch_all(events)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute(
        self, cmd: ImportRunReadoutsCommand
    ) -> Result[ImportRunReadoutsResult, DomainError]:
        # 1. Load run -------------------------------------------------------
        run = await self._run_repo.find_by_id_in_workspace(cmd.workspace_id, cmd.run_id)
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
        well_by_pos: dict[str, object] = {f"{w.row}{w.column}": w for w in run.wells}

        # 5. Parse file ------------------------------------------------------
        try:
            table = self._parser.parse(cmd.file_content, cmd.filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        # Normalise headers to lowercase for matching
        lower_headers = [h.lower() for h in table.headers]
        if "well" not in lower_headers:
            return Failure(ValidationError("File must have a 'Well' column"))

        well_header = table.headers[lower_headers.index("well")]

        # Identify value headers and map to readout definition ids.
        # Special case: a column named "value" (case-insensitive) maps to
        # readout_definition_id supplied in the command (single-value mode).
        header_to_rd_id: dict[str, uuid.UUID] = {}
        for header, lower_hdr in zip(table.headers, lower_headers, strict=True):
            if lower_hdr == "well":
                continue
            if lower_hdr == "value":
                if cmd.readout_definition_id is not None:
                    header_to_rd_id[header] = cmd.readout_definition_id
            else:
                rd_id = rd_by_name.get(lower_hdr)
                if rd_id is not None:
                    header_to_rd_id[header] = rd_id

        if not header_to_rd_id:
            return Failure(
                ValidationError(
                    "No file columns could be matched to readout definitions. "
                    "Column headers must match readout definition names (case-insensitive), "
                    "or use 'Value' with readout_definition_id supplied."
                )
            )

        # 6. Process rows ----------------------------------------------------
        result = ImportRunReadoutsResult()
        # Cache batch → molecule_id lookups
        mol_by_batch: dict[uuid.UUID, uuid.UUID | None] = {}

        entities: list[ReadoutData] = []

        for row in table.iter_rows():
            result.total_rows += 1

            raw_pos = (row.get(well_header) or "").strip().upper()
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
            for header, rd_id in header_to_rd_id.items():
                raw_val = (row.get(header) or "").strip()
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

        return Success(result)
