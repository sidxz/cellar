"""ImportSummaryFile — import wide-format summary (endpoint) values for a run.

Companion to ``PreviewSummaryFile``: takes the confirmed
``SummaryColumnMapping`` plus the uploaded file and writes one well-less
``ReadoutData`` row per (compound[/batch], readout-definition) cell.

It reuses the shared ``TabularParser`` to read the file and the identifier-aware
``summary_import_resolver`` (the same path the PLATE import uses) to resolve each
``compound_ref`` / ``batch_ref`` to a concrete ``(molecule_id, batch_id)`` BEFORE
handing items to ``BulkCreateReadoutData``. Resolution is therefore identifier-
aware (matches name / synonym / external id / registration number), fixing
files keyed by custom identifiers (e.g. ``SACC-0501058``) that the old
registration-number-only path silently dropped.

``BulkCreateReadoutData`` is invoked with ``upsert=True, require_batch=False`` so
molecule-only rows overwrite in place instead of duplicating; because items now
carry RESOLVED ids, the bulk UC short-circuits its own lookups. Insert-vs-update
accounting is computed by diffing the set of well-less, non-computed rows before
and after the bulk call. Triggering the calculated-readout engine is the route's
job, not this use case's.

Mirrors ``PreviewSummaryFile`` conventions: Railway ``Result``,
``require_editor`` guard, workspace-scoped repo loads, structlog.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from cellar.application.screening.summary_import_models import (
    SummaryColumnMapping,
    SummaryImportResult,
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

# Defense-in-depth row cap (mirrors PreviewSummaryFile; preview & import are
# separate requests, so neither can assume the other validated the file).
_MAX_ROWS = 50_000


@dataclass(frozen=True, kw_only=True)
class ImportSummaryFileCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    filename: str
    content: bytes
    mapping: SummaryColumnMapping


class ImportSummaryFile:
    """Import wide-format summary endpoint values into a run (upsert well-less)."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_repo: ReadoutDataRepository,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
        parser: TabularParser,
        bulk_uc: BulkCreateReadoutData,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_repo = readout_repo
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._parser = parser
        self._bulk = bulk_uc

    async def __call__(
        self,
        command: ImportSummaryFileCommand,
        auth: AuthContext | None = None,
    ) -> Result[SummaryImportResult, DomainError]:
        require_editor(auth)

        # Own + enter the read UoW for run/protocol/snapshot/resolution reads.
        # ``self._bulk`` opens its OWN write UoW (separate instance) that commits
        # + closes independently, so the read session is never torn down under us.
        async with self._uow:
            return await self._execute(command, auth)

    async def _execute(
        self,
        command: ImportSummaryFileCommand,
        auth: AuthContext | None = None,
    ) -> Result[SummaryImportResult, DomainError]:
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
        # repo call per distinct ref). This is the SAME path the plate import
        # takes, so a custom-identifier file (e.g. ``SACC-0501058``) resolves
        # exactly as it does there.
        compound_refs: list[str] = []
        batch_refs: list[str] = []
        if mapping.compound_ref:
            compound_refs = [(r.get(mapping.compound_ref) or "") for r in rows]
        if mapping.batch_ref:
            batch_refs = [(r.get(mapping.batch_ref) or "") for r in rows]

        compound_index = await build_compound_index(compound_refs, ws, self._molecule_repo)
        batch_index = await build_batch_index(batch_refs, ws, self._batch_repo)

        # Pure planner: resolves each row, routes values, dedups on the resolved
        # key (last-wins), and collects cell-level + unmatched-ref errors.
        plan = plan_summary_rows(
            rows,
            mapping=mapping,
            defs_by_id=defs_by_id,
            compound_index=compound_index,
            batch_index=batch_index,
        )

        # Build bulk items from the RESOLVED ids — no registration_number /
        # batch_number, so the bulk UC short-circuits its own lookups.
        items = [
            ReadoutDataItem(
                run_id=run_id,
                well_id=None,
                molecule_id=item.molecule_id,
                batch_id=item.batch_id,
                readout_definition_id=item.readout_definition_id,
                value_numeric=item.value_numeric,
                value_qualifier=item.value_qualifier,
                value_text=item.value_text,
            )
            for item in plan.items
        ]

        # Per-row error list. ``plan.errors`` already covers BOTH cell-level
        # errors (bad numeric / unknown def) AND unmatched-ref errors, so we do
        # NOT separately re-list the unmatched ref SETS here (that would
        # double-report the same row). ``row_conflicts`` are rendered as rows.
        errors: list[dict[str, str]] = list(plan.errors)
        for c in plan.row_conflicts:
            errors.append({"row": str(c.source_row), "error": c.reason})

        # Before/after snapshot diff assumes READ COMMITTED isolation (the default);
        # a stricter isolation level would break the inserted/updated accounting below.
        before = await self._wellless_keys(ws, run_id)

        values_inserted = 0
        values_updated = 0
        if items:
            bulk_result = await self._bulk(
                BulkCreateReadoutDataCommand(workspace_id=ws, items=items),
                auth=auth,
                upsert=True,
                require_batch=False,
            )
            if isinstance(bulk_result, Failure):
                return bulk_result
            bulk = bulk_result.unwrap()

            after = await self._wellless_keys(ws, run_id)
            values_inserted = len(after - before)
            values_updated = max(0, bulk.success_count - values_inserted)
            # Defensive: items carry resolved ids so bulk.errors should be empty,
            # but normalize any to the {row, error} shape just in case.
            for err in bulk.errors:
                errors.append({"row": "", "error": str(err.get("error", ""))})

        _log.info(
            "summary_file.imported",
            workspace_id=str(ws),
            run_id=str(run_id),
            rows_processed=table.row_count,
            values_inserted=values_inserted,
            values_updated=values_updated,
            rows_skipped=plan.rows_skipped,
            errors=len(errors),
        )

        return Success(
            SummaryImportResult(
                rows_processed=table.row_count,
                values_inserted=values_inserted,
                values_updated=values_updated,
                rows_skipped=plan.rows_skipped,
                errors=errors,
            )
        )

    async def _wellless_keys(
        self, ws: uuid.UUID, run_id: uuid.UUID
    ) -> set[tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID]]:
        """Snapshot of (molecule_id, batch_id, readout_definition_id) for well-less raw rows."""
        rows = await self._readout_repo.find_by_run(workspace_id=ws, run_id=run_id)
        return {
            (r.molecule_id, r.batch_id, r.readout_definition_id)
            for r in rows
            if r.well_id is None and not r.is_computed
        }
