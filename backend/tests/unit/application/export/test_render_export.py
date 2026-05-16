from __future__ import annotations
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.render_export import RenderExport
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow, RowStream
from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
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

    repo = MagicMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=job)
    repo.save = AsyncMock()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    storage = MagicMock()
    storage.upload = AsyncMock()

    runner = RenderExport(
        uow=uow,
        repo=repo,
        storage=storage,
        build_search_stream=lambda j: _FakeStream(),
    )
    await runner(job_id=job.id, workspace_id=workspace_id)
    assert job.status == ExportStatus.READY
    assert job.byte_size > 0
    assert storage.upload.await_count == 1
