from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.render_export import RenderExport
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.events import ExportCompleted
from cellar.domain.export.export_job import ExportJob


class _FakeStream:
    columns = [ColumnSpec(key="reg", header="Reg #", kind="text")]

    async def total_count(self) -> int:
        return 2

    async def iter_batches(self, batch_size: int) -> AsyncIterator[list[ExportRow]]:
        yield [ExportRow(cells={"reg": "CV-1"}), ExportRow(cells={"reg": "CV-2"})]


@pytest.mark.asyncio
async def test_render_export_csv_marks_ready(tmp_path):
    workspace_id = uuid.uuid4()
    job = ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.SEARCH,
        format=ExportFormat.CSV,
        query_snapshot={},
        filename="x.csv",
    )
    job.clear_events()  # ExportRequested was StartExport's to dispatch

    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    uow.commit = AsyncMock(side_effect=job.collect_events)  # as a real UoW would
    storage = MagicMock()
    storage.upload = AsyncMock()
    dispatcher = MagicMock()
    dispatcher.dispatch_all = AsyncMock()

    runner = RenderExport(
        uow=uow,
        repo=repo,
        storage=storage,
        build_search_stream=lambda j: _FakeStream(),
        dispatcher=dispatcher,
    )
    await runner(job_id=job.id, workspace_id=workspace_id)
    assert job.status == ExportStatus.READY
    assert job.byte_size > 0
    assert storage.upload.await_count == 1

    # Completion is audited with what left the building.
    dispatcher.dispatch_all.assert_awaited_once()
    (events,) = dispatcher.dispatch_all.await_args.args
    completed = [e for e in events if isinstance(e, ExportCompleted)]
    assert len(completed) == 1
    assert completed[0].user_id == job.requested_by
    assert completed[0].row_count == 2
    assert completed[0].byte_size == job.byte_size


def test_the_pdf_heading_uses_the_grids_summary_and_names_the_requester():
    from datetime import UTC, datetime

    from cellar.application.export.render_export import _extras_for

    job = ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        requested_by_email="ada@lab.org",
        source=ExportSource.SEARCH,
        format=ExportFormat.PDF,
        query_snapshot={
            "query": {"criteria": [{"type": "activity"}]},
            "summary": "All projects · Tested in InhA (any run, split by ATP)",
        },
        filename="x.pdf",
    )
    job.requested_at = datetime(2026, 11, 15, 19, 35, tzinfo=UTC)
    extras = _extras_for(job)
    assert extras["query_summary"] == "All projects · Tested in InhA (any run, split by ATP)"
    assert extras["exported_by"] == "ada@lab.org"
    assert extras["exported_at"] == "2026-11-15 19:35 UTC"

    job.query_snapshot = {"query": {"criteria": [{"type": "activity"}]}}  # an older request
    assert _extras_for(job)["query_summary"] == "1 activity criterion"


@pytest.mark.asyncio
async def test_a_run_export_renders_the_runs_report():
    from datetime import date

    from cellar.application.export.run_report import RunCell, RunReport, RunRow, RunWindow

    workspace_id = uuid.uuid4()
    job = ExportJob.create(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        requested_by=uuid.uuid4(),
        source=ExportSource.RUN,
        format=ExportFormat.CSV,
        query_snapshot={"run_id": str(uuid.uuid4())},
        filename="run.csv",
    )
    job.clear_events()
    report = RunReport(
        protocol="PRT-1 HsaA/B",
        run_date=date(2026, 11, 13),
        status="approved",
        operator=None,
        holder="Holder of 24",
        notes=None,
        dose_unit="uM",
        windows=(RunWindow("Main", "Ratio 350/330", 50, 85, 71.3, 1),),
        hit_rule=(),
        rows=(
            RunRow(
                uuid.uuid4(),
                "Position 1",
                "MadR",
                None,
                None,
                "MadR",
                None,
                "reference",
                None,
                {"Main": RunCell(71.3, None, "Reference")},
                None,
            ),
        ),
        steps=(),
    )
    built: list = []

    async def build(j):
        built.append(j)
        return report

    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    uow.commit = AsyncMock(side_effect=job.collect_events)
    storage = MagicMock()
    storage.upload = AsyncMock()
    dispatcher = MagicMock()
    dispatcher.dispatch_all = AsyncMock()

    runner = RenderExport(
        uow=uow,
        repo=repo,
        storage=storage,
        build_search_stream=lambda j: pytest.fail("a run export reads no search"),
        dispatcher=dispatcher,
        build_run_report=build,
    )
    await runner(job_id=job.id, workspace_id=workspace_id)
    assert built == [job]
    assert job.status == ExportStatus.READY and job.row_count == 1
    uploaded = storage.upload.await_args.args[1].decode()
    assert uploaded.splitlines()[1].startswith("Position 1,MadR")
