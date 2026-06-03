"""ImportSummaryFile — import wide-format summary (endpoint) values for a run.

Companion to ``PreviewSummaryFile``: takes the confirmed
``SummaryColumnMapping`` plus the uploaded file and writes one well-less
``ReadoutData`` row per (compound[/batch], readout-definition) cell.

It reuses the shared ``TabularParser`` to read the file and delegates all
identity resolution + persistence to ``BulkCreateReadoutData`` (invoked with
``upsert=True, require_batch=False`` so molecule-only rows overwrite in place
instead of duplicating). The use case itself only parses cell values, splits a
qualifier from a number, and computes insert-vs-update accounting by diffing the
set of well-less, non-computed rows before and after the bulk call. Triggering
the calculated-readout engine is the route's job, not this use case's.

Mirrors ``PreviewSummaryFile`` conventions: Railway ``Result``,
``require_editor`` guard, workspace-scoped repo loads, structlog.
"""

from __future__ import annotations

import re
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
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.domain.screening_assay.enums import ReadoutDataType
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

_log = structlog.get_logger(__name__)

# Optional qualifier symbol + a signed int/float/scientific number.
_NUMERIC_RE = re.compile(r"^\s*(<=|>=|<|>|=)?\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*$")


@dataclass(frozen=True, kw_only=True)
class ImportSummaryFileCommand:
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    filename: str
    content: bytes
    mapping: SummaryColumnMapping


class ImportSummaryFile:
    """Import wide-format summary endpoint values into a run (upsert well-less)."""

    def __init__(
        self,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        readout_repo: ReadoutDataRepository,
        parser: TabularParser,
        bulk_uc: BulkCreateReadoutData,
    ) -> None:
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._readout_repo = readout_repo
        self._parser = parser
        self._bulk = bulk_uc

    async def __call__(
        self,
        command: ImportSummaryFileCommand,
        auth: AuthContext | None = None,
    ) -> Result[SummaryImportResult, DomainError]:
        require_editor(auth)

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

        items: list[ReadoutDataItem] = []
        errors: list[dict[str, str]] = []
        rows_skipped = 0

        for ridx, row in enumerate(table.rows):
            reg = (row.get(mapping.compound_ref) or "").strip() if mapping.compound_ref else ""
            batch = (row.get(mapping.batch_ref) or "").strip() if mapping.batch_ref else ""
            if not reg and not batch:
                rows_skipped += 1
                continue

            for header, rdef_id in mapping.readout_columns.items():
                raw = (row.get(header) or "").strip()
                if not raw:
                    continue

                d = defs_by_id.get(rdef_id)
                if d is None:
                    errors.append({"row": str(ridx + 1), "error": "unknown readout def"})
                    continue

                value_numeric: float | None = None
                value_qualifier: str | None = None
                value_text: str | None = None

                if d.data_type == ReadoutDataType.TEXT:
                    value_text = raw
                else:
                    m = _NUMERIC_RE.match(raw)
                    if m is None:
                        errors.append(
                            {
                                "row": str(ridx + 1),
                                "error": f"'{raw}' not numeric for {d.name}",
                            }
                        )
                        continue
                    value_qualifier = m.group(1) or "="
                    value_numeric = float(m.group(2))

                items.append(
                    ReadoutDataItem(
                        run_id=run_id,
                        well_id=None,
                        registration_number=(reg or None),
                        batch_number=(batch or None),
                        readout_definition_id=rdef_id,
                        value_numeric=value_numeric,
                        value_qualifier=value_qualifier,
                        value_text=value_text,
                    )
                )

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
            for err in bulk.errors:
                errors.append({k: str(v) for k, v in err.items()})

        _log.info(
            "summary_file.imported",
            workspace_id=str(ws),
            run_id=str(run_id),
            rows_processed=table.row_count,
            values_inserted=values_inserted,
            values_updated=values_updated,
            rows_skipped=rows_skipped,
            errors=len(errors),
        )

        return Success(
            SummaryImportResult(
                rows_processed=table.row_count,
                values_inserted=values_inserted,
                values_updated=values_updated,
                rows_skipped=rows_skipped,
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
