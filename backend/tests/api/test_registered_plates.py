"""API tests for RegisteredPlate well-role harmonization.

Control wells (no batch) exercise the role + concentration flow end-to-end
without needing to seed a batch through the resolver.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID


async def _register(client: AsyncClient, **overrides):
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


class TestWellRoles:
    async def test_register_with_control_well_returns_flat_shape(
        self, client: AsyncClient
    ) -> None:
        resp = await _register(
            client,
            well_map={
                "A1": {
                    "well_type": "positive_control",
                    "concentration_value": 5.0,
                    "concentration_unit": "uM",
                }
            },
        )
        assert resp.status_code == 201, resp.text
        wm = resp.json()["well_map"]
        assert wm["A1"] == {
            "batch_id": None,
            "concentration_value": 5.0,
            "concentration_unit": "uM",
            "well_type": "positive_control",
            "cdd_batch_id_unresolved": None,
        }

    async def test_map_wells_endpoint_sets_role(self, client: AsyncClient) -> None:
        reg = await _register(client)
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        resp = await client.put(
            f"/api/v1/plates/{plate_id}/wells",
            json={"well_map": {"B2": {"well_type": "negative_control"}}},
        )
        assert resp.status_code == 200, resp.text
        well = resp.json()["well_map"]["B2"]
        assert well["well_type"] == "negative_control"
        assert well["batch_id"] is None

    async def test_invalid_well_type_rejected(self, client: AsyncClient) -> None:
        resp = await _register(client, well_map={"A1": {"well_type": "bogus"}})
        assert resp.status_code >= 400


class TestExport:
    async def test_csv_export(self, client: AsyncClient) -> None:
        reg = await _register(
            client,
            well_map={
                "A1": {
                    "well_type": "negative_control",
                    "concentration_value": 5.0,
                    "concentration_unit": "uM",
                }
            },
        )
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        resp = await client.get(f"/api/v1/plates/{plate_id}/export?format=csv")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")
        body = resp.text
        # Header order matches the well-mapping import exactly (round-trippable).
        assert "Well,Batch Number,Concentration,Unit,Role" in body
        assert "negative_control" in body

    async def test_xlsx_export(self, client: AsyncClient) -> None:
        reg = await _register(client, well_map={"A1": {"well_type": "blank"}})
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        resp = await client.get(f"/api/v1/plates/{plate_id}/export?format=xlsx")
        assert resp.status_code == 200, resp.text
        assert "spreadsheetml" in resp.headers["content-type"]
        assert resp.content[:2] == b"PK"  # xlsx is a zip archive

    async def test_export_missing_plate_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/plates/{uuid.uuid4()}/export?format=csv")
        assert resp.status_code == 404


class TestOwnerOrg:
    async def test_register_defaults_owner_org_from_auth(self, client: AsyncClient) -> None:
        resp = await _register(client)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["owner_org_id"] == str(AUTH_ORG_ID)

    async def test_register_explicit_owner_org_allowed_for_admin(
        self, client: AsyncClient
    ) -> None:
        """`client` is admin-role auth (tests/api/conftest.py) — admins are exempt
        from the cross-org assignment guard, so an explicit foreign org is allowed."""
        explicit_org = uuid.uuid4()
        resp = await _register(client, owner_org_id=str(explicit_org))
        assert resp.status_code == 201, resp.text
        assert resp.json()["owner_org_id"] == str(explicit_org)

    async def test_register_explicit_same_org_allowed_for_editor(
        self, editor_client_own_org: AsyncClient
    ) -> None:
        resp = await _register(editor_client_own_org, owner_org_id=str(AUTH_ORG_ID))
        assert resp.status_code == 201, resp.text
        assert resp.json()["owner_org_id"] == str(AUTH_ORG_ID)

    async def test_register_explicit_foreign_org_forbidden_for_editor(
        self, editor_client_own_org: AsyncClient
    ) -> None:
        foreign_org = uuid.uuid4()
        resp = await _register(editor_client_own_org, owner_org_id=str(foreign_org))
        assert resp.status_code == 403, resp.text

    async def test_list_filters_by_owner_org(self, client: AsyncClient) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        reg_a = await _register(client, owner_org_id=str(org_a))
        assert reg_a.status_code == 201, reg_a.text
        reg_b = await _register(client, owner_org_id=str(org_b))
        assert reg_b.status_code == 201, reg_b.text

        resp = await client.get("/api/v1/plates", params={"owner_org_id": str(org_a)})
        assert resp.status_code == 200, resp.text
        ids = {p["id"] for p in resp.json()}
        assert reg_a.json()["id"] in ids
        assert reg_b.json()["id"] not in ids


class TestPlateVisibility:
    """Private-org plate exclusion (PlateVisibilityService) — S2 scope."""

    async def test_private_org_excluded_from_list_and_get_for_other_org_caller(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        # `client` is AUTH_ORG_ID — a different org than the plate's owner —
        # so the now-private plate is excluded from list and 404s on direct GET.
        listed = await client.get("/api/v1/plates")
        assert listed.status_code == 200, listed.text
        assert plate_id not in {p["id"] for p in listed.json()}

        got = await client.get(f"/api/v1/plates/{plate_id}")
        assert got.status_code == 404, got.text

        # `editor_client_other_org` is OTHER_ORG_ID — the plate's own org —
        # so it stays visible in both list and direct GET.
        got_own = await editor_client_other_org.get(f"/api/v1/plates/{plate_id}")
        assert got_own.status_code == 200, got_own.text
        assert got_own.json()["id"] == plate_id

        listed_own = await editor_client_other_org.get("/api/v1/plates")
        assert listed_own.status_code == 200, listed_own.text
        assert plate_id in {p["id"] for p in listed_own.json()}

    async def test_explicit_owner_org_filter_cannot_disclose_private_org(
        self, client: AsyncClient
    ) -> None:
        """Security-review addition: an explicit ``owner_org_id`` filter for a
        now-private org must not leak its plates either — the exclusion applies
        even when the caller names the org directly, not just on the unfiltered
        list."""
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        resp = await client.get("/api/v1/plates", params={"owner_org_id": str(OTHER_ORG_ID)})
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    # -- Task 5b: children / export / write-path enforcement -----------------

    async def test_children_exclude_private_org_child(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        parent = await _register(client)
        assert parent.status_code == 201, parent.text
        parent_id = parent.json()["id"]

        child = await _register(client, parent_plate_id=parent_id, owner_org_id=str(OTHER_ORG_ID))
        assert child.status_code == 201, child.text
        child_id = child.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        # Parent (AUTH_ORG_ID) is visible, but the private-org child must not
        # appear in its children list.
        listed = await client.get(f"/api/v1/plates/{parent_id}/children")
        assert listed.status_code == 200, listed.text
        assert child_id not in {p["id"] for p in listed.json()}

        # The child's own org still sees it.
        listed_own = await editor_client_other_org.get(f"/api/v1/plates/{parent_id}/children")
        assert listed_own.status_code == 200, listed_own.text
        assert child_id in {p["id"] for p in listed_own.json()}

    async def test_children_of_invisible_parent_404(self, client: AsyncClient) -> None:
        parent = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert parent.status_code == 201, parent.text
        parent_id = parent.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        resp = await client.get(f"/api/v1/plates/{parent_id}/children")
        assert resp.status_code == 404, resp.text

    async def test_export_private_plate_404_foreign_200_own_org(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        resp = await client.get(f"/api/v1/plates/{plate_id}/export?format=csv")
        assert resp.status_code == 404, resp.text

        resp_own = await editor_client_other_org.get(
            f"/api/v1/plates/{plate_id}/export?format=csv"
        )
        assert resp_own.status_code == 200, resp_own.text

    async def test_update_and_delete_private_plate_404_foreign_200_own_org(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        patch_foreign = await client.patch(f"/api/v1/plates/{plate_id}", json={"notes": "nope"})
        assert patch_foreign.status_code == 404, patch_foreign.text

        delete_foreign = await client.delete(f"/api/v1/plates/{plate_id}")
        assert delete_foreign.status_code == 404, delete_foreign.text

        # Status quo preserved — the plate's own org can still update it.
        patch_own = await editor_client_other_org.patch(
            f"/api/v1/plates/{plate_id}", json={"notes": "legit update"}
        )
        assert patch_own.status_code == 200, patch_own.text
        assert patch_own.json()["notes"] == "legit update"

    async def test_map_wells_change_status_derive_404_for_foreign_org(
        self, client: AsyncClient
    ) -> None:
        """MapWells, ChangeStatus, and DerivePlate's parent lookup share the
        exact fetch-then-can_view guard proven above for update/delete — this
        exercises each one's own new branch directly."""
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        wells = await client.put(
            f"/api/v1/plates/{plate_id}/wells",
            json={"well_map": {"A1": {"well_type": "blank"}}},
        )
        assert wells.status_code == 404, wells.text

        status = await client.patch(
            f"/api/v1/plates/{plate_id}/status", json={"new_status": "in_use"}
        )
        assert status.status_code == 404, status.text

        derive = await client.post(
            f"/api/v1/plates/{plate_id}/derive",
            json={"barcode": f"PLT-CHILD-{uuid.uuid4().hex[:8]}", "plate_label": "Child"},
        )
        assert derive.status_code == 404, derive.text

    async def test_derive_from_private_org_plate_inherits_owner_and_stays_private(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        """Derived children inherit the parent's owner_org_id (domain invariant,
        not a caller choice) — so a daughter of a private org's plate is itself
        private, invisible to a foreign-org caller."""
        parent = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert parent.status_code == 201, parent.text
        parent_id = parent.json()["id"]

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        # Derive as the plate's own org — the only caller that can see the parent.
        derive = await editor_client_other_org.post(
            f"/api/v1/plates/{parent_id}/derive",
            json={"barcode": f"PLT-CHILD-{uuid.uuid4().hex[:8]}", "plate_label": "Child"},
        )
        assert derive.status_code == 201, derive.text
        child = derive.json()
        assert child["owner_org_id"] == str(OTHER_ORG_ID)
        child_id = child["id"]

        # Foreign-org caller cannot see the derived child, same as the parent.
        got_foreign = await client.get(f"/api/v1/plates/{child_id}")
        assert got_foreign.status_code == 404, got_foreign.text

        listed_foreign = await client.get("/api/v1/plates")
        assert listed_foreign.status_code == 200, listed_foreign.text
        assert child_id not in {p["id"] for p in listed_foreign.json()}


class TestMoleculePlatesVisibility:
    """Private-org exclusion on GET /molecules/{id}/plates (read-model path)."""

    async def test_molecule_plates_excludes_private_org_plate(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        org = await client.post(
            "/api/v1/organizations", json={"name": "MolPlateVisOrg", "org_type": "internal"}
        )
        assert org.status_code == 201, org.text
        org_id = org.json()["id"]

        mol = await client.post(
            "/api/v1/molecules",
            json={"smiles": "CCO", "name": "ethanol-mp-vis", "originating_org_id": org_id},
        )
        assert mol.status_code in (200, 201), mol.text
        molecule_id = mol.json()["molecule"]["id"]

        batch = await client.post(
            "/api/v1/batches",
            json={
                "molecule_id": molecule_id,
                "source": "synthesized",
                "amount_value": 10.0,
                "amount_unit": "mg",
            },
        )
        assert batch.status_code in (200, 201), batch.text
        batch_id = batch.json()["batch"]["id"]

        # Private-org plate carrying this molecule's batch.
        private_plate = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert private_plate.status_code == 201, private_plate.text
        private_plate_id = private_plate.json()["id"]
        mapped = await client.put(
            f"/api/v1/plates/{private_plate_id}/wells",
            json={"well_map": {"A1": {"batch_id": batch_id}}},
        )
        assert mapped.status_code == 200, mapped.text

        # Visible (own-org) plate carrying the same batch — must stay listed.
        visible_plate = await _register(client)
        assert visible_plate.status_code == 201, visible_plate.text
        visible_plate_id = visible_plate.json()["id"]
        mapped_visible = await client.put(
            f"/api/v1/plates/{visible_plate_id}/wells",
            json={"well_map": {"A1": {"batch_id": batch_id}}},
        )
        assert mapped_visible.status_code == 200, mapped_visible.text

        policy = await _set_plates_private(client, OTHER_ORG_ID)
        assert policy.status_code == 200, policy.text

        resp = await client.get(f"/api/v1/molecules/{molecule_id}/plates")
        assert resp.status_code == 200, resp.text
        plate_ids = {e["plate_id"] for e in resp.json()}
        assert private_plate_id not in plate_ids
        assert visible_plate_id in plate_ids

        # The private plate's own org still sees it.
        resp_own = await editor_client_other_org.get(f"/api/v1/molecules/{molecule_id}/plates")
        assert resp_own.status_code == 200, resp_own.text
        assert private_plate_id in {e["plate_id"] for e in resp_own.json()}
