"""API: a run file larger than the upload limit is refused before it is parsed or stored."""

from __future__ import annotations

import uuid

import pytest

from cellar.interface.routes import run_import


@pytest.mark.asyncio
async def test_a_run_file_past_the_size_limit_is_refused(client, monkeypatch) -> None:
    monkeypatch.setattr(run_import, "MAX_RUN_FILE_BYTES", 32)
    big = b"Well,Raw\n" + b"A1,0.5\n" * 10

    resp = await client.post(
        f"/api/v1/runs/{uuid.uuid4()}/preview-file", files={"file": ("run.csv", big, "text/csv")}
    )

    assert resp.status_code == 422, resp.text
    assert "larger than" in resp.text
