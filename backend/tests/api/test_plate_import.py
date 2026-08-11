"""API tests: private-org plate visibility on the barcode-keyed plate-data
import pipeline (S2 Task 5c) — a barcode-matched plate hidden by org policy
must be reported exactly like an unmatched barcode, no distinct wording.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.api.conftest import OTHER_ORG_ID


async def _register_plate(client: AsyncClient, **overrides):
    body = {
        "barcode": f"PLT-{uuid.uuid4().hex[:8]}",
        "plate_label": "Test Plate",
        "format": "96",
        "plate_type": "assay",
    }
    body.update(overrides)
    return await client.post("/api/v1/plates", json=body)


async def _set_plates_private(client: AsyncClient, org_id: uuid.UUID, *, private: bool = True):
    body = {
        "require_approval": True,
        "confirmation": "admin_confirm",
        "default_due_days": None,
        "plates_private": private,
    }
    return await client.put(f"/api/v1/org-plate-policies/{org_id}", json=body)


async def _preview(client: AsyncClient, barcodes: list[str]) -> str:
    """Upload a minimal one-column CSV and return the cached file_id."""
    csv_bytes = ("Barcode\n" + "\n".join(barcodes) + "\n").encode()
    resp = await client.post(
        "/api/v1/plates/import/preview",
        files={"file": ("plates.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


_MAPPINGS = {"Barcode": "plate_barcode"}


class TestImportBarcodeVisibility:
    async def test_validate_hidden_plate_reports_same_shape_as_true_miss_for_foreign_org(
        self, client: AsyncClient
    ) -> None:
        reg = await _register_plate(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        private_barcode = reg.json()["barcode"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        missing_barcode = f"PLT-NOPE-{uuid.uuid4().hex[:8]}"

        # `client` is AUTH_ORG_ID — foreign to the plate's OTHER_ORG_ID owner.
        file_id = await _preview(client, [private_barcode, missing_barcode])
        resp = await client.post(
            "/api/v1/plates/import/validate",
            json={"file_id": file_id, "column_mappings": _MAPPINGS},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_rows"] == 2
        assert body["matched"] == 0
        assert body["unresolved"] == 2
        assert body["errors"] == 2
        issues = {d["issue"] for d in body["details"]}
        # Identical message template for the hidden plate and the genuinely
        # missing one — no field/wording distinguishes "exists but hidden"
        # from "does not exist" (no existence oracle).
        assert issues == {
            f"Plate {private_barcode!r} not found",
            f"Plate {missing_barcode!r} not found",
        }

    async def test_validate_matches_for_own_org(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        reg = await _register_plate(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        private_barcode = reg.json()["barcode"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        # Preview + validate must go through the SAME client — the import
        # file cache is per-app (per DI container), not shared across clients.
        file_id = await _preview(editor_client_other_org, [private_barcode])
        resp = await editor_client_other_org.post(
            "/api/v1/plates/import/validate",
            json={"file_id": file_id, "column_mappings": _MAPPINGS},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["details"] == []
        assert body["matched"] == 1
        assert body["unresolved"] == 0
