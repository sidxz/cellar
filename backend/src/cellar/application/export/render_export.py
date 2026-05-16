"""RenderExport — in-process runner: row_stream → renderer → fsspec upload → job state.

T13's Temporal activity wraps this callable. The NullExportOrchestrator (T13) also
runs it inline for environments without a Temporal cluster.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import AsyncIterator, Callable

import structlog

from cellar.application.export.renderers.base import ExportRenderer, RenderOptions
from cellar.application.export.renderers.csv_renderer import CsvRenderer
from cellar.application.export.renderers.excel_renderer import ExcelRenderer
from cellar.application.export.renderers.pdf_renderer import PdfRenderer
from cellar.application.export.renderers.sdf_renderer import SdfRenderer
from cellar.application.export.row_streams.base import ExportRow, RowStream
from cellar.application.export.row_streams.search_results import SearchResultsRowStream
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient

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

        runner = RenderExport(uow=..., repo=..., storage=..., build_search_stream=...)
        await runner(job_id=job.id, workspace_id=job.workspace_id)
    """

    uow: UnitOfWork
    repo: ExportJobRepository
    storage: FsspecStorageClient
    build_search_stream: Callable[[ExportJob], SearchResultsRowStream]

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
            stream = self._build_stream(job)
            renderer = _renderer_for(job.format)
            total = await stream.total_count()

            # ── 2. Persist row count so the UI can show a denominator ────────
            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                job.set_row_count(total)
                await self.repo.save(job)
                await self.uow.commit()

            ext = job.format.extension
            with NamedTemporaryFile(suffix=ext, delete=False) as tf:
                tmp_path = Path(tf.name)

            options = RenderOptions(title=f"Cellar Export — {job.format.value.upper()}")
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
                await self.uow.commit()

        except Exception as exc:  # noqa: BLE001
            logger.exception("export.failed", job_id=str(job_id))
            async with self.uow:
                job = await self.repo.find_by_id_in_workspace(workspace_id, job_id)
                if job is not None:
                    job.mark_failed(str(exc))
                    await self.repo.save(job)
                    await self.uow.commit()
            raise

    def _build_stream(self, job: ExportJob) -> RowStream:
        if job.source == ExportSource.SEARCH:
            return self.build_search_stream(job)
        raise ValueError(f"Unsupported export source: {job.source}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
