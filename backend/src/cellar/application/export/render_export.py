"""RenderExport — in-process runner: row_stream → renderer → fsspec upload → job state.

T13's Temporal activity wraps this callable. The NullExportOrchestrator (T13) also
runs it inline for environments without a Temporal cluster.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

import structlog

from cellar.application.attachment.storage import StorageClient
from cellar.application.export.renderers.base import ExportRenderer, RenderOptions
from cellar.application.export.renderers.csv_renderer import CsvRenderer
from cellar.application.export.renderers.excel_renderer import ExcelRenderer
from cellar.application.export.renderers.pdf_renderer import PdfRenderer
from cellar.application.export.renderers.run_report_renderer import render_run_report
from cellar.application.export.renderers.sdf_renderer import SdfRenderer
from cellar.application.export.row_streams.base import ExportRow, RowStream
from cellar.application.export.row_streams.search_results import SearchResultsRowStream
from cellar.application.export.run_report import RunReport
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.export.repository import ExportJobRepository

logger = structlog.get_logger(__name__)

_TTL_DAYS = 7
_BATCH_SIZE = 500


@dataclass
class RenderExport:
    """Callable that drives the full export pipeline for one job.

    Dependencies are injected as dataclass fields so both the Temporal
    activity (T13) and the NullExportOrchestrator (T13) can wire them
    independently.

    Usage::

        runner = RenderExport(
            uow=..., repo=..., storage=..., build_search_stream=..., dispatcher=...
        )
        await runner(job_id=job.id, workspace_id=job.workspace_id)
    """

    uow: UnitOfWork
    repo: ExportJobRepository
    storage: StorageClient
    build_search_stream: Callable[[ExportJob], SearchResultsRowStream]
    dispatcher: EventDispatcherProtocol
    # A run's report (source=run); unset where only searches are exported.
    build_run_report: Callable[[ExportJob], Awaitable[RunReport]] | None = None

    async def __call__(self, job_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        # ── 1. Load job, guard idempotency, advance to RUNNING ──────────────
        async with self.uow:
            job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
            if job is None:
                raise RuntimeError(f"ExportJob {job_id} not found")
            if job.status not in (ExportStatus.PENDING, ExportStatus.RUNNING):
                logger.info(
                    "export.skip_non_runnable",
                    job_id=str(job_id),
                    status=job.status,
                )
                return
            if job.status == ExportStatus.PENDING:
                job.mark_running()
                await self.repo.save(job)
                await self.uow.commit()

        try:
            ext = job.format.extension
            with NamedTemporaryFile(suffix=ext, delete=False) as tf:
                tmp_path = Path(tf.name)
            options = RenderOptions(
                title=_title_for(job),
                image_size=_image_size_for(job),
                extras=_extras_for(job),
            )

            if job.source == ExportSource.RUN:
                if self.build_run_report is None:
                    raise ValueError("Run exports are not set up here")
                report = await self.build_run_report(job)
                total = len(report.rows)
                await self._set_row_count(workspace_id, job_id, total)
                options = replace(
                    options, extras={**options.extras, "query_summary": report.summary}
                )
                await render_run_report(report, job.format, tmp_path, options)
            else:
                stream = self._build_stream(job)
                renderer = _renderer_for(job.format)
                total = await stream.total_count()
                # ── 2. Persist row count so the UI can show a denominator ────
                await self._set_row_count(workspace_id, job_id, total)
                await renderer.render(
                    columns=stream.columns,
                    batches=_progressing(
                        stream.iter_batches(_BATCH_SIZE),
                        repo=self.repo,
                        uow=self.uow,
                        workspace_id=workspace_id,
                        job_id=job_id,
                        total=total,
                    ),
                    out_path=tmp_path,
                    options=options,
                    row_count_hint=total,
                )

            # ── 3. Upload to storage ─────────────────────────────────────────
            key = f"exports/{job.workspace_id}/{job.id}{ext}"
            await self.storage.upload(key, tmp_path.read_bytes())
            byte_size = tmp_path.stat().st_size
            tmp_path.unlink(missing_ok=True)

            # ── 4. Mark READY ────────────────────────────────────────────────
            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                job.mark_ready(
                    file_key=key,
                    byte_size=byte_size,
                    content_type=job.format.media_type,
                    expires_at=datetime.now(UTC) + timedelta(days=_TTL_DAYS),
                )
                await self.repo.save(job)
                events = await self.uow.commit()
            await self.dispatcher.dispatch_all(events)  # ExportCompleted → audit row
            logger.info(
                "export.completed",
                job_id=str(job_id),
                workspace_id=str(workspace_id),
                user_id=str(job.requested_by),
                format=job.format.value,
                row_count=total,
                byte_size=byte_size,
            )

        except Exception as exc:
            logger.exception("export.failed", job_id=str(job_id))
            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                if job is not None:
                    job.mark_failed(str(exc))
                    await self.repo.save(job)
                    await self.uow.commit()
            raise

    async def _set_row_count(self, workspace_id: uuid.UUID, job_id: uuid.UUID, total: int) -> None:
        async with self.uow:
            job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
            job.set_row_count(total)
            await self.repo.save(job)
            await self.uow.commit()

    def _build_stream(self, job: ExportJob) -> RowStream:
        if job.source == ExportSource.SEARCH:
            return self.build_search_stream(job)
        raise ValueError(f"Unsupported export source: {job.source}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Keyed by the lowercase enum *value* on the wire (matches
# ``SelectionRule.LATEST_RUN.value == "latest_run"``).
_AGGREGATION_LABELS = {
    "latest_run": "Latest run",
    "best_r_squared": "Best R²",
    "mean_across_runs": "Arithmetic mean",
    "geometric_mean": "Geometric mean",
}


def _title_for(job: ExportJob) -> str:
    return "Run report" if job.source == ExportSource.RUN else "Search results"


def _image_size_for(job: ExportJob) -> str:
    rc = (
        (job.query_snapshot or {}).get("reportConfig")
        or (job.query_snapshot or {}).get("report_config")
        or {}
    )
    size = rc.get("imageSize")
    return size if size in ("small", "medium", "large") else "medium"


def _extras_for(job: ExportJob) -> dict:
    payload = job.query_snapshot or {}
    agg_raw = (payload.get("aggregation") or "latest_run").lower()
    extras: dict = {
        "aggregation_label": _AGGREGATION_LABELS.get(agg_raw, agg_raw.replace("_", " ").title()),
        # When the person asked for it, which is what the audit trail records.
        "exported_at": (job.requested_at or datetime.now(UTC))
        .astimezone(UTC)
        .strftime("%Y-%m-%d %H:%M UTC"),
        "exported_by": job.requested_by_email,
    }
    # The grid's own summary line ("All projects · Tested in … (any run, split by
    # ATP)"), sent with the request; older requests fall back to the kinds count.
    summary = payload.get("summary")
    query = payload.get("query")
    if not (isinstance(summary, str) and summary.strip()) and isinstance(query, dict):
        summary = _summarize_query(query)
    if summary:
        extras["query_summary"] = summary.strip()
    return extras


def _summarize_query(query: dict) -> str:
    """One-line human-readable summary of the search criteria.

    Doesn't try to be exhaustive — surfaces top-level criterion kinds +
    counts so the chemist sees "Substructure + 2 property filters" rather
    than a raw JSON dump.
    """
    parts: list[str] = []
    criteria = query.get("criteria") or query.get("filters") or []
    if isinstance(criteria, list):
        kinds: dict[str, int] = {}
        for c in criteria:
            if isinstance(c, dict):
                k = c.get("kind") or c.get("type") or "criterion"
                kinds[k] = kinds.get(k, 0) + 1
        for k, n in kinds.items():
            label = k.replace("_", " ")
            noun = "criterion" if n == 1 else "criteria"
            parts.append(f"{n} {label} {noun}")
    if query.get("query_smiles") or query.get("smiles"):
        parts.append("structure query")
    return " · ".join(parts)


def _renderer_for(fmt: ExportFormat) -> ExportRenderer:
    return {
        ExportFormat.CSV: CsvRenderer(),
        ExportFormat.SDF: SdfRenderer(),
        ExportFormat.XLSX: ExcelRenderer(),
        ExportFormat.PDF: PdfRenderer(),
    }[fmt]


async def _progressing(
    source: AsyncIterator[list[ExportRow]],
    *,
    repo: ExportJobRepository,
    uow: UnitOfWork,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    total: int,
) -> AsyncIterator[list[ExportRow]]:
    """Async generator that yields batches from *source* and writes progress after each."""
    rows_done = 0
    async for batch in source:
        rows_done += len(batch)
        yield batch
        if total > 0:
            async with uow:
                job = await repo.find_by_id_in_workspace(workspace_id, job_id)
                if job is None:
                    continue
                job.report_progress(rows_done / total)
                await repo.save(job)
                await uow.commit()
