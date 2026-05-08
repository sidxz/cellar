"""End-to-end API tests for admin hard-delete (Tier 1 — vocabulary).

HTTPX note: AsyncClient.delete() does not support a `json` body parameter.
Use client.request("DELETE", url, json=...) for DELETE requests with a body.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_vocab(client: AsyncClient, name: str) -> dict:
    """Create a vocabulary via the public API and return the response body."""
    resp = await client.post("/api/v1/vocabularies", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _admin_delete(
    client: AsyncClient, entity_type: str, entity_id: str, reason: str
):
    """Issue an admin DELETE with a JSON body (workaround for httpx delete limit)."""
    return await client.request(
        "DELETE",
        f"/api/v1/admin/{entity_type}/{entity_id}",
        json={"reason": reason},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdminHardDelete:
    async def test_admin_can_delete_unreferenced_vocabulary(
        self, client: AsyncClient
    ) -> None:
        """Admin deletes an unreferenced vocabulary → 204."""
        vocab = await _create_vocab(client, "Solvents-T1")
        resp = await _admin_delete(client, "vocabulary", vocab["id"], "obsolete")
        assert resp.status_code == 204

    async def test_editor_cannot_admin_delete(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        """Editor calling admin endpoint → 403."""
        vocab = await _create_vocab(client, "Solvents-T2")
        resp = await _admin_delete(editor_client, "vocabulary", vocab["id"], "x")
        assert resp.status_code == 403

    async def test_missing_reason_422(self, client: AsyncClient) -> None:
        """Admin calls with empty reason body → 422."""
        vocab = await _create_vocab(client, "Solvents-T3")
        resp = await _admin_delete(client, "vocabulary", vocab["id"], "")
        assert resp.status_code == 422

    async def test_unknown_entity_type_404(self, client: AsyncClient) -> None:
        """Admin calls /admin/wat/<uuid> → 404 (entity_type not in registry)."""
        resp = await _admin_delete(client, "wat", str(uuid.uuid4()), "x")
        assert resp.status_code == 404

    async def test_audit_operation_recorded(self, client: AsyncClient) -> None:
        """After a successful delete, an admin_hard_delete audit operation exists."""
        vocab = await _create_vocab(client, "Solvents-T5")
        vid = vocab["id"]

        delete_resp = await _admin_delete(client, "vocabulary", vid, "obsolete")
        assert delete_resp.status_code == 204

        # Query audit log for this entity via the audit API
        audit_resp = await client.get(
            "/api/v1/audit",
            params={"entity_type": "vocabulary", "entity_id": vid},
        )
        assert audit_resp.status_code == 200
        ops = audit_resp.json()

        hard_deletes = [
            op for op in ops if op["operation_type"] == "admin_hard_delete"
        ]
        assert hard_deletes, "Expected at least one admin_hard_delete audit operation"

        op = hard_deletes[0]
        assert op["reason"] == "obsolete"
        assert any(e["entry_type"] == "delete" for e in op["entries"])
