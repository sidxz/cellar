"""API tests for /api/v1/plate-loans."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID, _create_test_app
from tests.fakes.fake_auth import FakeAuth


async def _mk_plate(client: AsyncClient, barcode: str, **overrides) -> dict:
    body = {
        "barcode": barcode,
        "plate_label": barcode,
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_group(client: AsyncClient, name: str, **overrides) -> dict:
    body = {"name": name, **overrides}
    resp = await client.post("/api/v1/plate-groups", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_policy(client: AsyncClient, org_id, **fields) -> dict:
    body = {
        "require_approval": True,
        "confirmation": "admin_confirm",
        "default_due_days": None,
        "plates_private": False,
        **fields,
    }
    resp = await client.put(f"/api/v1/org-plate-policies/{org_id}", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _mk_loan(client: AsyncClient, **body) -> dict:
    resp = await client.post("/api/v1/plate-loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    """An ad-hoc client for an identity distinct from the standard fixtures.

    ``client``/``editor_client_*`` all resolve from the SAME cached
    ``workspace_id``/``user_id`` fixtures within one test function, so they
    share one ``user_id`` (and, unless overridden, ``org_id``) — that can't
    exercise ``mine=`` (needs a second requester) or a genuinely third,
    unrelated org (visibility tests). Not passing ``user_id``/``org_id``
    gets a fresh ``uuid4()`` from ``FakeAuth`` for either.
    """
    auth_kwargs.setdefault("role", "editor")
    auth = FakeAuth(workspace_id=workspace_id, **auth_kwargs)
    app = _create_test_app(database_url, auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


class TestColonPathRouting:
    """Dedicated probe (plan Step 1): fail loud and early if FastAPI/Starlette
    can't route a literal colon in a path segment, before trusting it across
    the rest of the matrix."""

    async def test_verb_route_is_reachable(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        assert resp.status_code != 404, resp.text


class TestRequestModes:
    async def test_by_plate_ids(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["owner_org_id"] == str(AUTH_ORG_ID)
        assert loan["borrower_org_id"] == str(AUTH_ORG_ID)
        assert [i["plate_id"] for i in loan["items"]] == [plate["id"]]
        assert loan["items"][0]["barcode"] == plate["barcode"]
        assert loan["items"][0]["plate_label"] == plate["plate_label"]

    async def test_by_barcodes_short_form_resolves_padded(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, "005261")
        loan = await _mk_loan(client, barcodes=["5261"])
        assert [i["plate_id"] for i in loan["items"]] == [plate["id"]]

    async def test_by_group_id(self, client: AsyncClient) -> None:
        group = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        assert (
            await client.post(
                f"/api/v1/plate-groups/{group['id']}/plates", json={"plate_ids": [plate["id"]]}
            )
        ).status_code == 204
        loan = await _mk_loan(client, group_id=group["id"])
        assert [i["plate_id"] for i in loan["items"]] == [plate["id"]]

    async def test_exactly_one_mode_required(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        # none of plate_ids/barcodes/group_id provided
        resp = await client.post("/api/v1/plate-loans", json={"notes": "x"})
        assert resp.status_code == 422
        # two modes at once
        resp = await client.post(
            "/api/v1/plate-loans",
            json={"plate_ids": [plate["id"]], "barcodes": [plate["barcode"]]},
        )
        assert resp.status_code == 422

    async def test_unknown_barcode_rejected_and_listed(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/plate-loans", json={"barcodes": ["NOPE-XYZ"]})
        assert resp.status_code == 422
        assert "NOPE-XYZ" in resp.json()["message"]

    async def test_empty_group_rejected(self, client: AsyncClient) -> None:
        group = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        resp = await client.post("/api/v1/plate-loans", json={"group_id": group["id"]})
        assert resp.status_code == 422


class TestOwnershipOrg:
    async def test_plates_spanning_two_orgs_rejected(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        mine = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        theirs = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await client.post(
            "/api/v1/plate-loans", json={"plate_ids": [mine["id"], theirs["id"]]}
        )
        assert resp.status_code == 422

    async def test_null_owner_plate_rejected(
        self, client: AsyncClient, editor_client: AsyncClient
    ) -> None:
        plate = await _mk_plate(editor_client, f"PL-{uuid.uuid4().hex[:8]}")
        assert plate["owner_org_id"] is None
        resp = await client.post("/api/v1/plate-loans", json={"plate_ids": [plate["id"]]})
        assert resp.status_code == 422

    async def test_borrower_recorded_as_callers_org(
        self, editor_client_other_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        assert loan["owner_org_id"] == str(OTHER_ORG_ID)
        assert loan["borrower_org_id"] == str(OTHER_ORG_ID)


class TestPolicyCollapse:
    async def test_default_policy_items_requested(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["items"][0]["status"] == "requested"

    async def test_require_approval_false_items_approved(self, client: AsyncClient) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False)
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["items"][0]["status"] == "approved"

    async def test_require_approval_false_confirmation_none_items_checked_out(
        self, client: AsyncClient
    ) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["items"][0]["status"] == "checked_out"

    async def test_default_due_days_fills_due_date(self, client: AsyncClient) -> None:
        await _set_policy(client, AUTH_ORG_ID, default_due_days=7)
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["due_date"] == (date.today() + timedelta(days=7)).isoformat()

    async def test_explicit_due_date_wins_over_policy_default(self, client: AsyncClient) -> None:
        await _set_policy(client, AUTH_ORG_ID, default_due_days=7)
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        explicit = (date.today() + timedelta(days=30)).isoformat()
        loan = await _mk_loan(client, plate_ids=[plate["id"]], due_date=explicit)
        assert loan["due_date"] == explicit


class TestActiveConflict:
    async def test_second_loan_on_active_plate_conflicts(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post("/api/v1/plate-loans", json={"plate_ids": [plate["id"]]})
        assert resp.status_code == 409
        assert plate["barcode"] in resp.json()["message"]

    async def test_returned_plate_can_be_reloaned(self, client: AsyncClient) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["items"][0]["status"] == "checked_out"
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "returned"
        resp = await client.post("/api/v1/plate-loans", json={"plate_ids": [plate["id"]]})
        assert resp.status_code == 201, resp.text


class TestAuthorityMatrix:
    async def test_approve_as_admin(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "approved"

    async def test_approve_as_owner_org_editor_with_action(
        self, client: AsyncClient, approver_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await approver_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={}
        )
        assert resp.status_code == 200, resp.text

    async def test_approve_as_owner_org_editor_without_action_forbidden(
        self, client: AsyncClient, denied_editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await denied_editor_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={}
        )
        assert resp.status_code == 403

    async def test_approve_as_borrower_org_editor_wrong_org_forbidden(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        # owner = AUTH_ORG (via `client`), borrower = OTHER_ORG (requester's org)
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={}
        )
        assert resp.status_code == 403

    async def test_deny_wrong_org_forbidden(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:deny", json={}
        )
        assert resp.status_code == 403

    async def test_confirm_out_wrong_org_forbidden(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        ).status_code == 200
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:confirm-out", json={}
        )
        assert resp.status_code == 403

    async def test_confirm_in_wrong_org_forbidden(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:confirm-out", json={})
        ).status_code == 200
        assert (
            await editor_client_other_org.post(
                f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={}
            )
        ).status_code == 200  # borrower org (OTHER_ORG) may request-return
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:confirm-in", json={}
        )
        assert resp.status_code == 403

    async def test_request_return_as_borrower_org_editor(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:confirm-out", json={})
        ).status_code == 200
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={}
        )
        assert resp.status_code == 200, resp.text

    async def test_request_return_as_unrelated_org_editor_forbidden(
        self,
        client: AsyncClient,
        editor_client_other_org: AsyncClient,
        editor_client_own_org: AsyncClient,
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        # borrower = OTHER_ORG
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:confirm-out", json={})
        ).status_code == 200
        # Owner-org editor (AUTH_ORG) is neither the borrower nor admin — no
        # borrower-side authority despite owning the plates.
        resp = await editor_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={}
        )
        assert resp.status_code == 403

    async def test_cancel_as_requester(self, editor_client_own_org: AsyncClient) -> None:
        plate = await _mk_plate(editor_client_own_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_own_org, plate_ids=[plate["id"]])
        resp = await editor_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:cancel", json={}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "cancelled"


class TestMachineViaApi:
    async def test_full_happy_path_closes_loan(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        loan_id = loan["id"]

        resp = await client.post(f"/api/v1/plate-loans/{loan_id}/items:approve", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "approved"

        resp = await client.post(f"/api/v1/plate-loans/{loan_id}/items:confirm-out", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "checked_out"

        resp = await client.post(f"/api/v1/plate-loans/{loan_id}/items:request-return", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "return_pending"

        resp = await client.post(f"/api/v1/plate-loans/{loan_id}/items:confirm-in", json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"][0]["status"] == "returned"
        assert body["status"] == "closed"
        assert body["closed_at"] is not None

    async def test_null_item_ids_expands_to_all_eligible(self, client: AsyncClient) -> None:
        p1 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        p2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[p1["id"], p2["id"]])
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={"item_ids": None}
        )
        assert resp.status_code == 200, resp.text
        assert {i["status"] for i in resp.json()["items"]} == {"approved"}

    async def test_invalid_transition_rejected(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        item_id = loan["items"][0]["id"]
        # item is still REQUESTED — confirm-out requires APPROVED
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:confirm-out",
            json={"item_ids": [item_id]},
        )
        assert resp.status_code == 422

    async def test_approve_already_approved_rejected(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        item_id = loan["items"][0]["id"]
        assert (
            await client.post(
                f"/api/v1/plate-loans/{loan['id']}/items:approve", json={"item_ids": [item_id]}
            )
        ).status_code == 200
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={"item_ids": [item_id]}
        )
        assert resp.status_code == 422


class TestCollapseOnTransitions:
    async def test_approve_auto_advances_to_checked_out_when_confirmation_none(
        self, client: AsyncClient
    ) -> None:
        # require_approval stays default True — only confirmation changes.
        await _set_policy(client, AUTH_ORG_ID, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert loan["items"][0]["status"] == "requested"
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "checked_out"

    async def test_request_return_auto_advances_to_returned_when_confirmation_none(
        self, client: AsyncClient
    ) -> None:
        await _set_policy(client, AUTH_ORG_ID, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        ).status_code == 200  # collapses straight to CHECKED_OUT
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"][0]["status"] == "returned"
        assert body["status"] == "closed"


class TestFilters:
    async def test_mine_true_returns_only_my_requests(
        self, editor_client_own_org: AsyncClient, database_url: str, workspace_id: uuid.UUID
    ) -> None:
        plate = await _mk_plate(editor_client_own_org, f"PL-{uuid.uuid4().hex[:8]}")
        mine = await _mk_loan(editor_client_own_org, plate_ids=[plate["id"]])
        async with _client_as(database_url, workspace_id, org_id=AUTH_ORG_ID) as other:
            other_plate = await _mk_plate(other, f"PL-{uuid.uuid4().hex[:8]}")
            others_loan = await _mk_loan(other, plate_ids=[other_plate["id"]])
            resp = await editor_client_own_org.get("/api/v1/plate-loans", params={"mine": "true"})
            assert resp.status_code == 200, resp.text
            ids = [loan["id"] for loan in resp.json()]
            assert mine["id"] in ids
            assert others_loan["id"] not in ids

    async def test_status_filter(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.get("/api/v1/plate-loans", params={"status": "open"})
        assert resp.status_code == 200
        assert loan["id"] in [loan_["id"] for loan_ in resp.json()]
        resp = await client.get("/api/v1/plate-loans", params={"status": "closed"})
        assert loan["id"] not in [loan_["id"] for loan_ in resp.json()]

    async def test_overdue_filter(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        past_due = (date.today() - timedelta(days=1)).isoformat()
        overdue_loan = await _mk_loan(client, plate_ids=[plate["id"]], due_date=past_due)
        plate2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        not_due = await _mk_loan(client, plate_ids=[plate2["id"]])
        resp = await client.get("/api/v1/plate-loans", params={"overdue": "true"})
        assert resp.status_code == 200
        ids = [loan["id"] for loan in resp.json()]
        assert overdue_loan["id"] in ids
        assert not_due["id"] not in ids

    async def test_plate_id_filter(self, client: AsyncClient) -> None:
        p1 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        p2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan1 = await _mk_loan(client, plate_ids=[p1["id"]])
        loan2 = await _mk_loan(client, plate_ids=[p2["id"]])
        resp = await client.get("/api/v1/plate-loans", params={"plate_id": p1["id"]})
        assert resp.status_code == 200
        ids = [loan["id"] for loan in resp.json()]
        assert loan1["id"] in ids
        assert loan2["id"] not in ids


class TestLoanVisibility:
    async def test_private_owner_org_loan_visibility(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        # owner = OTHER_ORG, borrower = AUTH_ORG
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_own_org, plate_ids=[plate["id"]])
        await _set_policy(client, OTHER_ORG_ID, plates_private=True)
        try:
            # A genuinely unrelated third org — neither owner nor borrower.
            async with _client_as(database_url, workspace_id, org_id=uuid.uuid4()) as unrelated:
                resp = await unrelated.get(f"/api/v1/plate-loans/{loan['id']}")
                assert resp.status_code == 404
                listed = await unrelated.get("/api/v1/plate-loans")
                assert loan["id"] not in [loan_["id"] for loan_ in listed.json()]

            resp = await editor_client_own_org.get(f"/api/v1/plate-loans/{loan['id']}")
            assert resp.status_code == 200
            listed = await editor_client_own_org.get("/api/v1/plate-loans")
            assert loan["id"] in [loan_["id"] for loan_ in listed.json()]

            resp = await editor_client_other_org.get(f"/api/v1/plate-loans/{loan['id']}")
            assert resp.status_code == 200
            listed = await editor_client_other_org.get("/api/v1/plate-loans")
            assert loan["id"] in [loan_["id"] for loan_ in listed.json()]
        finally:
            await _set_policy(client, OTHER_ORG_ID, plates_private=False)


class TestBorrowedPlateVisibility:
    async def test_borrowed_plate_visible_then_hidden_after_return(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        loaned = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        never_loaned = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        # Request the loan while the org is still visible — RequestPlateLoan's
        # plate resolution doesn't apply the borrowed carve-out (Task 7's
        # deliberate write-path narrowing), so a caller can't request a loan
        # on a plate it can't already see. Privacy flips on AFTER, proving
        # the carve-out keeps the now-borrowed plate visible regardless.
        loan = await _mk_loan(client, plate_ids=[loaned["id"]])  # borrower = AUTH_ORG

        await _set_policy(client, OTHER_ORG_ID, plates_private=True)
        try:
            resp = await editor_client_own_org.get(f"/api/v1/plates/{never_loaned['id']}")
            assert resp.status_code == 404

            resp = await editor_client_own_org.get(f"/api/v1/plates/{loaned['id']}")
            assert resp.status_code == 200, resp.text
            listed = await editor_client_own_org.get("/api/v1/plates")
            listed_ids = [p["id"] for p in listed.json()]
            assert loaned["id"] in listed_ids
            assert never_loaned["id"] not in listed_ids

            assert (
                await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
            ).status_code == 200
            assert (
                await client.post(f"/api/v1/plate-loans/{loan['id']}/items:confirm-out", json={})
            ).status_code == 200
            assert (
                await client.post(
                    f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={}
                )
            ).status_code == 200
            closing = await client.post(
                f"/api/v1/plate-loans/{loan['id']}/items:confirm-in", json={}
            )
            assert closing.status_code == 200
            assert closing.json()["status"] == "closed"

            resp = await editor_client_own_org.get(f"/api/v1/plates/{loaned['id']}")
            assert resp.status_code == 404

            resp = await editor_client_own_org.get(f"/api/v1/plates/{never_loaned['id']}")
            assert resp.status_code == 404
        finally:
            await _set_policy(client, OTHER_ORG_ID, plates_private=False)
