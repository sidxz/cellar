"""API tests for the unified export endpoints + legacy SDF shim."""

from __future__ import annotations

import uuid

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.sqlalchemy.export.export_job_model import ExportJobModel


async def _seed_pending_job(session_factory: async_sessionmaker[AsyncSession], fake_auth) -> str:
    """A PENDING job with no runner behind it, so its status cannot move under the test
    (a job started through the API renders inline and races the assertions)."""
    job_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(
            ExportJobModel(
                id=job_id,
                workspace_id=fake_auth.workspace_id,
                requested_by=fake_auth.user_id,
                source="search",
                format="csv",
                query_snapshot={},
                status="pending",
                filename="export.csv",
                requested_at=datetime.now(UTC),
            )
        )
        await s.commit()
    return str(job_id)


# ---------------------------------------------------------------------------
# Unified export endpoints — /api/v1/exports
# ---------------------------------------------------------------------------


class TestStartExport:
    async def test_returns_job_id(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/v1/exports",
            json={
                "format": "csv",
                "payload": {"query": {"criteria": []}, "protocol_columns": []},
            },
        )
        assert res.status_code == 202
        body = res.json()
        assert "job_id" in body
        # Must be a valid UUID
        uuid.UUID(body["job_id"])


class TestGetExport:
    async def test_unknown_id_returns_404(self, client: AsyncClient) -> None:
        res = await client.get(
            f"/api/v1/exports/{uuid.uuid4()}",
        )
        assert res.status_code == 404

    async def test_round_trip_pending_status(self, client: AsyncClient) -> None:
        """Start an export, then immediately poll — expect PENDING or RUNNING."""
        start = await client.post(
            "/api/v1/exports",
            json={
                "format": "csv",
                "payload": {"query": {"criteria": []}, "protocol_columns": []},
            },
        )
        assert start.status_code == 202
        job_id = start.json()["job_id"]

        poll = await client.get(f"/api/v1/exports/{job_id}")
        assert poll.status_code == 200
        body = poll.json()
        assert body["id"] == job_id
        assert body["status"] in {"pending", "running", "ready", "failed"}
        assert body["format"] == "csv"


class TestListExports:
    async def test_limit_too_large_returns_422(self, client: AsyncClient) -> None:
        res = await client.get("/api/v1/exports?limit=999")
        assert res.status_code == 422

    async def test_started_job_appears_in_list(self, client: AsyncClient) -> None:
        start = await client.post(
            "/api/v1/exports",
            json={
                "format": "xlsx",
                "payload": {"query": {"criteria": []}, "protocol_columns": []},
            },
        )
        assert start.status_code == 202
        job_id = start.json()["job_id"]

        listing = await client.get("/api/v1/exports")
        assert listing.status_code == 200
        ids = [item["id"] for item in listing.json()]
        assert job_id in ids


class TestCancelExport:
    async def test_cancel_unknown_returns_404(self, client: AsyncClient) -> None:
        res = await client.post(f"/api/v1/exports/{uuid.uuid4()}/cancel")
        assert res.status_code == 404

    async def test_cancel_pending_job(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth
    ) -> None:
        job_id = await _seed_pending_job(session_factory, fake_auth)

        cancel = await client.post(f"/api/v1/exports/{job_id}/cancel")
        assert cancel.status_code == 204, cancel.text

        poll = await client.get(f"/api/v1/exports/{job_id}")
        assert poll.json()["status"] == "cancel_requested"


class TestDownloadExport:
    async def test_not_ready_returns_409(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth
    ) -> None:
        """A job that is still PENDING has no file to download yet."""
        job_id = await _seed_pending_job(session_factory, fake_auth)

        dl = await client.get(f"/api/v1/exports/{job_id}/download")
        assert dl.status_code == 409, dl.text

    async def test_unknown_id_returns_404(self, client: AsyncClient) -> None:
        res = await client.get(f"/api/v1/exports/{uuid.uuid4()}/download")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Legacy SDF shim — /api/v1/molecules/export/sdf now returns 410 Gone
# ---------------------------------------------------------------------------


class TestLegacySdfShim:
    async def test_returns_410(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/v1/molecules/export/sdf",
            json={"molecule_ids": []},
        )
        assert res.status_code == 410

    async def test_410_body_has_detail(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/v1/molecules/export/sdf",
            json={"molecule_ids": [str(uuid.uuid4())]},
        )
        assert res.status_code == 410
        body = res.json()
        assert "detail" in body
        assert "exports" in body["detail"]
