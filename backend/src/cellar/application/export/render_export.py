"""RenderExport — in-process runner: row_stream → renderer → fsspec upload → job state.

T13's Temporal activity wraps this callable. The NullExportOrchestrator (T13) also
runs it inline for environments without a Temporal cluster.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

import structlog

from cellar.application.attachment.storage import StorageClient
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
    storage: StorageClient
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

            options = RenderOptions(
                title=_title_for(job),
                image_size=_image_size_for(job),
                extras=_extras_for(job),
            )
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

        except Exception as exc:
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


# Keyed by the lowercase enum *value* on the wire (matches
# ``SelectionRule.LATEST_APPROVED_RUN.value == "latest_approved_run"``).
_AGGREGATION_LABELS = {
    "latest_approved_run": "Latest run",
    "best_r_squared": "Best R²",
    "mean_across_runs": "Arithmetic mean",
    "geometric_mean": "Geometric mean",
}


def _title_for(job: ExportJob) -> str:
    return "Cellar Search"


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
    agg_raw = (payload.get("aggregation") or "latest_approved_run").lower()
    extras: dict = {
        "aggregation_label": _AGGREGATION_LABELS.get(agg_raw, agg_raw.replace("_", " ").title()),
        "exported_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }
    query = payload.get("query")
    if isinstance(query, dict):
        summary = _summarize_query(query)
        if summary:
            extras["query_summary"] = summary
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
