"""PreviewSummaryFile — parse a wide summary file and suggest a column mapping.

Read-only use case for the summary-results (wide-format endpoint values)
importer. Given an uploaded file and a target run, it parses the tabular
content (reusing the shared ``TabularParser``), loads the run's protocol so
its readout-definition catalog can drive header inference, and returns a
``SummaryPreviewResult`` describing a suggested role per column. No writes.

Mirrors ``PreviewRunFile`` conventions: Railway ``Result``, ``require_editor``
guard, workspace-scoped repo loads, and the shared parser Protocol.
"""

from __future__ import annotations

import uuid

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening.summary_import_models import (
    SummaryHeaderSuggestion,
    SummaryPreviewResult,
    SummaryRole,
)
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    RunRepository,
)
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)

_log = structlog.get_logger(__name__)

# Header-name families recognised as compound / batch references. Compared
# against the normalized header (lower + strip, space/hyphen -> underscore).
_COMPOUND_HEADERS = frozenset(
    {
        "compound",
        "compound_id",
        "compound_ref",
        "registration_number",
        "reg_no",
        "regno",
        "structure_id",
        "name",
        "id",
    }
)
_BATCH_HEADERS = frozenset(
    {
        "batch",
        "batch_number",
        "batch_ref",
        "batch_id",
        "lot",
        "lot_number",
    }
)

_SAMPLE_N = 10
# Hard cap mirrors the run-file sync-import limit.
_MAX_ROWS = 50_000


def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_")


class PreviewSummaryFile:
    """Parse a wide summary file + suggest a per-column role mapping (no writes)."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        protocol_repo: ProtocolRepository,
        parser: TabularParser,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._protocol_repo = protocol_repo
        self._parser = parser

    async def __call__(
        self,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        filename: str,
        content: bytes,
        auth: AuthContext | None = None,
    ) -> Result[SummaryPreviewResult, DomainError]:
        require_editor(auth)

        # Own + enter the read UoW so the repos have an active session
        # (mirrors PreviewRunFile). Read-only: no commit.
        async with self._uow:
            return await self._execute(
                workspace_id=workspace_id,
                run_id=run_id,
                filename=filename,
                content=content,
            )

    async def _execute(
        self,
        *,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        filename: str,
        content: bytes,
    ) -> Result[SummaryPreviewResult, DomainError]:
        run = await self._run_repo.find_by_id_in_workspace(workspace_id, run_id)
        if run is None:
            return Failure(NotFoundError("Run", str(run_id)))

        protocol = await self._protocol_repo.find_by_id_in_workspace(workspace_id, run.protocol_id)
        if protocol is None:
            return Failure(NotFoundError("Protocol", str(run.protocol_id)))

        try:
            table = self._parser.parse(content, filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        if table.row_count > _MAX_ROWS:
            return Failure(
                ValidationError(
                    f"File has {table.row_count} rows; sync import limit is {_MAX_ROWS}"
                )
            )

        # Index protocol readout-defs by normalized name for O(1) lookup.
        readout_by_name: dict[str, uuid.UUID] = {
            _norm(rd.name): rd.id for rd in protocol.readout_definitions
        }

        suggestions = _infer_suggestions(table.headers, readout_by_name)

        sample_rows = [
            {h: (row.get(h) or "") for h in table.headers} for row in table.rows[:_SAMPLE_N]
        ]

        _log.info(
            "summary_file.previewed",
            workspace_id=str(workspace_id),
            run_id=str(run_id),
            headers=len(table.headers),
            total_rows=table.row_count,
        )

        return Success(
            SummaryPreviewResult(
                headers=list(table.headers),
                suggestions=suggestions,
                sample_rows=sample_rows,
                total_rows=table.row_count,
            )
        )


def _infer_suggestions(
    headers: list[str], readout_by_name: dict[str, uuid.UUID]
) -> list[SummaryHeaderSuggestion]:
    """Build a role suggestion per header.

    First-match-wins for compound_ref / batch_ref so only one column claims
    each ref role; readout matches are independent of that gate.
    """
    suggestions: list[SummaryHeaderSuggestion] = []
    compound_assigned = False
    batch_assigned = False

    for header in headers:
        norm = _norm(header)

        readout_def_id = readout_by_name.get(norm)
        if readout_def_id is not None:
            suggestions.append(
                SummaryHeaderSuggestion(
                    header=header,
                    role=SummaryRole.READOUT,
                    confidence="high",
                    readout_definition_id=readout_def_id,
                )
            )
            continue

        if norm in _COMPOUND_HEADERS and not compound_assigned:
            compound_assigned = True
            suggestions.append(
                SummaryHeaderSuggestion(
                    header=header,
                    role=SummaryRole.COMPOUND_REF,
                    confidence="high",
                )
            )
            continue

        if norm in _BATCH_HEADERS and not batch_assigned:
            batch_assigned = True
            suggestions.append(
                SummaryHeaderSuggestion(
                    header=header,
                    role=SummaryRole.BATCH_REF,
                    confidence="high",
                )
            )
            continue

        suggestions.append(
            SummaryHeaderSuggestion(
                header=header,
                role=SummaryRole.IGNORE,
                confidence="low",
                note="no confident role match",
            )
        )

    return suggestions
