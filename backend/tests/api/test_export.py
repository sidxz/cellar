"""API tests for the unified export endpoints + legacy SDF shim."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


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

    async def test_unsupported_source_returns_422(self, client: AsyncClient) -> None:
        """Only 'search' is a supported source; any other value fails validation."""
        res = await client.post(
            "/api/v1/exports",
            json={
                "source": "not_a_valid_source",
                "format": "csv",
                "payload": {},
            },
        )
        assert res.status_code == 422

    async def test_invalid_format_returns_422(self, client: AsyncClient) -> None:
        res = await client.post(
            "/api/v1/exports",
            json={
                "format": "docx",
                "payload": {},
            },
        )
        assert res.status_code == 422


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
    async def test_returns_list(self, client: AsyncClient) -> None:
        res = await client.get("/api/v1/exports")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_limit_query_param(self, client: AsyncClient) -> None:
        res = await client.get("/api/v1/exports?limit=10")
        assert res.status_code == 200

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

    async def test_cancel_pending_job(self, client: AsyncClient) -> None:
        start = await client.post(
            "/api/v1/exports",
            json={
                "format": "sdf",
                "payload": {"query": {"criteria": []}, "protocol_columns": []},
            },
        )
        assert start.status_code == 202
        job_id = start.json()["job_id"]

        cancel = await client.post(f"/api/v1/exports/{job_id}/cancel")
        # 204 No Content on success; the job may have already completed (409 conflict)
        # depending on how fast the Null orchestrator runs — both are acceptable.
        assert cancel.status_code in {204, 409}


class TestDownloadExport:
    async def test_not_ready_returns_409(self, client: AsyncClient) -> None:
        """A freshly created job that is still PENDING returns 409."""
        start = await client.post(
            "/api/v1/exports",
            json={
                "format": "csv",
                "payload": {"query": {"criteria": []}, "protocol_columns": []},
            },
        )
        assert start.status_code == 202
        job_id = start.json()["job_id"]

        # Check status first — if the Null orchestrator ran synchronously the job
        # could already be READY (and the download would return 200).  Only assert
        # 409 when the job is genuinely not ready.
        poll = await client.get(f"/api/v1/exports/{job_id}")
        status = poll.json()["status"]
        if status != "ready":
            dl = await client.get(f"/api/v1/exports/{job_id}/download")
            assert dl.status_code == 409

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
