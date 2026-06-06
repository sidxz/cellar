"""PreviewSummaryImport — dry-run forecast of a wide-format summary import.

The Preview (step 3 of the Upload → Map → Preview → Confirm wizard) resolves
every ``compound_ref`` / ``batch_ref`` and forecasts what a real import WOULD
write, WITHOUT writing anything. It is the summary-path analog of the plate
path's repreview (``resolve_rows`` dry-run).

It does everything ``ImportSummaryFile`` does — ``require_editor`` guard, load
run + protocol, parse via the shared ``TabularParser``, build the identifier-
aware ``compound_index`` / ``batch_index`` (the SAME path the plate import
uses), and run the pure ``plan_summary_rows`` planner — EXCEPT the bulk write.
Instead of calling ``BulkCreateReadoutData`` it forecasts insert-vs-update by
probing ``ReadoutDataRepository.find_wellless_by_keys`` per planned item: an
existing well-less row → ``values_to_update``; otherwise ``values_to_insert``.
All probes are read-only.

Mirrors ``PreviewSummaryFile`` / ``ImportSummaryFile`` conventions: Railway
``Result``, workspace-scoped repo loads, structlog, and owning + entering its
own read UoW.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.summary_import_models import (
    SummaryColumnMapping,
    SummaryImportPlanPreview,
)
from cellar.application.screening.summary_import_resolver import (
    build_batch_index,
    build_compound_index,
    plan_summary_rows,
)
from cellar.application.shared.command import Command
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

_log = structlog.get_logger(__name__)

# Defense-in-depth row cap (mirrors ImportSummaryFile / PreviewSummaryFile;
# preview & import are separate requests, so neither can assume the other
# validated the file).
_MAX_ROWS = 50_000


@dataclass(frozen=True, kw_only=True)
class PreviewSummaryImportCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    filename: str
    content: bytes
    mapping: SummaryColumnMapping


class PreviewSummaryImport:
    """Dry-run a wide-format summary import: resolve refs + forecast writes (no writes)."""

    def __init__(
        self,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_repo: ReadoutDataRepository,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
        parser: TabularParser,
        uow: UnitOfWork,
    ) -> None:
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_repo = readout_repo
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._parser = parser
        self._uow = uow

    async def __call__(
        self,
        command: PreviewSummaryImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[SummaryImportPlanPreview, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, command.workspace_id)

        # Own + enter the read UoW so the repos have an active session. Read-only:
        # no commit, no write (mirrors PreviewSummaryFile / ImportSummaryFile).
        async with self._uow:
            return await self._execute(command)

    async def _execute(
        self,
        command: PreviewSummaryImportCommand,
    ) -> Result[SummaryImportPlanPreview, DomainError]:
        ws = command.workspace_id
        run_id = command.run_id
        mapping = command.mapping

        run = await self._run_repo.find_by_id_in_workspace(ws, run_id)
        if run is None:
            return Failure(NotFoundError("Run", str(run_id)))

        protocol = await self._protocol_repo.find_by_id_in_workspace(ws, run.protocol_id)
        if protocol is None:
            return Failure(NotFoundError("Protocol", str(run.protocol_id)))

        defs_by_id = {d.id: d for d in protocol.readout_definitions}

        try:
            table = self._parser.parse(command.content, command.filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        if table.row_count > _MAX_ROWS:
            return Failure(
                ValidationError(
                    f"File has {table.row_count} rows; sync import limit is {_MAX_ROWS}"
                )
            )

        rows = table.rows

        # Distinct refs across the file, then identifier-aware resolution (one
        # repo call per distinct ref). SAME path as ImportSummaryFile / the plate
        # import, so the dry-run resolves exactly as the real import would.
        compound_refs: list[str] = []
        batch_refs: list[str] = []
        if mapping.compound_ref:
            compound_refs = [(r.get(mapping.compound_ref) or "") for r in rows]
        if mapping.batch_ref:
            batch_refs = [(r.get(mapping.batch_ref) or "") for r in rows]

        compound_index = await build_compound_index(compound_refs, ws, self._molecule_repo)
        batch_index = await build_batch_index(batch_refs, ws, self._batch_repo)

        plan = plan_summary_rows(
            rows,
            mapping=mapping,
            defs_by_id=defs_by_id,
            compound_index=compound_index,
            batch_index=batch_index,
        )

        # Per-row errors: ``plan.errors`` already covers BOTH cell-level errors
        # (bad numeric / unknown def) AND unmatched-ref errors. The unmatched ref
        # SETS are returned separately (not re-listed here). ``row_conflicts`` are
        # rendered as {row, error}.
        errors: list[dict[str, str]] = list(plan.errors)
        for c in plan.row_conflicts:
            errors.append({"row": str(c.source_row), "error": c.reason})

        # Forecast insert vs. update by probing for an existing well-less row per
        # planned item. Read-only — find_wellless_by_keys never writes.
        values_to_insert = 0
        values_to_update = 0
        for item in plan.items:
            existing = await self._readout_repo.find_wellless_by_keys(
                workspace_id=ws,
                run_id=run_id,
                molecule_id=item.molecule_id,
                batch_id=item.batch_id,
                readout_definition_id=item.readout_definition_id,
            )
            if existing is not None:
                values_to_update += 1
            else:
                values_to_insert += 1

        _log.info(
            "summary_import.previewed",
            workspace_id=str(ws),
            run_id=str(run_id),
            total_rows=table.row_count,
            matched_compound_count=plan.matched_compound_count,
            values_to_insert=values_to_insert,
            values_to_update=values_to_update,
            rows_skipped=plan.rows_skipped,
            errors=len(errors),
        )

        return Success(
            SummaryImportPlanPreview(
                total_rows=table.row_count,
                matched_compound_count=plan.matched_compound_count,
                unmatched_compound_refs=sorted(plan.unmatched_compound_refs),
                unmatched_batch_refs=sorted(plan.unmatched_batch_refs),
                values_to_insert=values_to_insert,
                values_to_update=values_to_update,
                rows_skipped=plan.rows_skipped,
                errors=errors,
            )
        )
