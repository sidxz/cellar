"""API tests for /api/v1/plate-loans."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.auth import LOAN_APPROVE_ACTION
from tests.api.conftest import AUTH_ORG_ID, ORG_ID, OTHER_ORG_ID, _create_test_app
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


async def _mk_loan_as_org(
    database_url: str, workspace_id: uuid.UUID, org_id: uuid.UUID, **body
) -> dict:
    """Create a loan with ``borrower_org_id == org_id``.

    RequestPlateLoan derives ``borrower_org_id`` from the caller's own org and
    (strict-by-default) can only resolve plates the caller can see — so a
    non-admin editor in ``org_id`` can't request a loan on a plate owned by a
    different org. An ad-hoc admin scoped to ``org_id`` bypasses visibility
    (sees the plate) while still supplying the right ``borrower_org_id``.
    """
    async with _client_as(database_url, workspace_id, org_id=org_id, role="admin") as admin_as_org:
        return await _mk_loan(admin_as_org, **body)


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
        me = (await approver_client_own_org.get("/api/v1/user/me")).json()
        resp = await approver_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["approved_by"] == me["user_id"]

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
        self, client: AsyncClient, database_url: str, workspace_id: uuid.UUID
    ) -> None:
        # owner = AUTH_ORG (via `client`), borrower = OTHER_ORG (requester's org).
        # Grant the approve action explicitly — editor_client_other_org's
        # default `granted_actions=None` is permissive, which would let this
        # 403 pass even if the org guard were silently dropped. Granting the
        # action proves the org check is what rejects, and that it runs
        # before (not masked by) the action grant.
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan_as_org(
            database_url, workspace_id, OTHER_ORG_ID, plate_ids=[plate["id"]]
        )
        async with _client_as(
            database_url,
            workspace_id,
            org_id=OTHER_ORG_ID,
            granted_actions={LOAN_APPROVE_ACTION},
        ) as other_org_approver:
            resp = await other_org_approver.post(
                f"/api/v1/plate-loans/{loan['id']}/items:approve", json={}
            )
            assert resp.status_code == 403

    async def test_deny_wrong_org_forbidden(
        self,
        client: AsyncClient,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        # owner = AUTH_ORG (via `client`), borrower = OTHER_ORG.
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan_as_org(
            database_url, workspace_id, OTHER_ORG_ID, plate_ids=[plate["id"]]
        )
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:deny", json={}
        )
        assert resp.status_code == 403

    async def test_confirm_out_wrong_org_forbidden(
        self,
        client: AsyncClient,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        # owner = AUTH_ORG (via `client`), borrower = OTHER_ORG.
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan_as_org(
            database_url, workspace_id, OTHER_ORG_ID, plate_ids=[plate["id"]]
        )
        assert (
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={})
        ).status_code == 200
        resp = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:confirm-out", json={}
        )
        assert resp.status_code == 403

    async def test_confirm_in_wrong_org_forbidden(
        self,
        client: AsyncClient,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        # owner = AUTH_ORG (via `client`), borrower = OTHER_ORG.
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan_as_org(
            database_url, workspace_id, OTHER_ORG_ID, plate_ids=[plate["id"]]
        )
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
        self,
        client: AsyncClient,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        # owner = AUTH_ORG (via `client`), borrower = OTHER_ORG.
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan_as_org(
            database_url, workspace_id, OTHER_ORG_ID, plate_ids=[plate["id"]]
        )
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
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        # borrower = OTHER_ORG
        loan = await _mk_loan_as_org(
            database_url, workspace_id, OTHER_ORG_ID, plate_ids=[plate["id"]]
        )
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

    async def test_list_loans_rejects_unknown_status(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/plate-loans", params={"status": "opne"})
        assert resp.status_code == 422  # was: silently zero rows

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
    async def test_foreign_owner_org_loan_visibility(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        # owner = OTHER_ORG, borrower = AUTH_ORG. Admin (own org == AUTH_ORG)
        # requests the loan — a non-admin AUTH_ORG editor can't see a plate it
        # doesn't yet borrow, so it can't be the one to request it.
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])

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


class TestBorrowedPlateVisibility:
    async def test_borrowed_plate_visible_then_hidden_after_return(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        loaned = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        never_loaned = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        # Admin requests the loan (bypasses visibility entirely) — both plates
        # are OTHER_ORG's and strict-by-default already excludes them from
        # AUTH_ORG's editor; the borrowed carve-out is what re-admits `loaned`.
        loan = await _mk_loan(client, plate_ids=[loaned["id"]])  # borrower = AUTH_ORG

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
            await client.post(f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={})
        ).status_code == 200
        closing = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:confirm-in", json={})
        assert closing.status_code == 200
        assert closing.json()["status"] == "closed"

        resp = await editor_client_own_org.get(f"/api/v1/plates/{loaned['id']}")
        assert resp.status_code == 404

        resp = await editor_client_own_org.get(f"/api/v1/plates/{never_loaned['id']}")
        assert resp.status_code == 404


class TestOwnerLends:
    """Ruling R6: cross-org loans are created by the owner org."""

    async def test_owner_editor_lends_to_other_org_items_approved(
        self, client: AsyncClient, editor_client_own_org: AsyncClient, user_id: uuid.UUID
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # owner = AUTH_ORG
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID)
        )
        assert loan["owner_org_id"] == str(AUTH_ORG_ID)
        assert loan["borrower_org_id"] == str(OTHER_ORG_ID)
        assert [i["status"] for i in loan["items"]] == ["approved"]
        assert loan["approved_by"] == str(user_id)

    async def test_lend_with_confirmation_none_checks_out(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=True, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID)
        )
        assert [i["status"] for i in loan["items"]] == ["checked_out"]

    async def test_lend_to_unknown_org_rejected(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await editor_client_own_org.post(
            "/api/v1/plate-loans",
            json={"plate_ids": [plate["id"]], "borrower_org_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422, resp.text
        assert "Unknown borrower organization" in resp.text

    async def test_non_owner_editor_cannot_lend_foreign_plate(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await editor_client_own_org.post(
            "/api/v1/plate-loans",
            json={"plate_ids": [plate["id"]], "borrower_org_id": str(ORG_ID)},
        )
        assert resp.status_code == 404, resp.text  # hidden == missing

    async def test_admin_can_lend_any_orgs_plate(self, client: AsyncClient) -> None:
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        loan = await _mk_loan(client, plate_ids=[plate["id"]], borrower_org_id=str(ORG_ID))
        assert loan["owner_org_id"] == str(OTHER_ORG_ID)
        assert loan["borrower_org_id"] == str(ORG_ID)
        assert [i["status"] for i in loan["items"]] == ["approved"]

    async def test_borrower_org_id_equal_to_own_org_is_a_plain_request(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(AUTH_ORG_ID)
        )
        assert loan["borrower_org_id"] == str(AUTH_ORG_ID)
        # default policy: approval required
        assert [i["status"] for i in loan["items"]] == ["requested"]

    async def test_owner_editor_cancels_own_initiated_loan(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        """Ruling R7 (final review I3): the owner org can retract a mis-lend
        before the borrower has physically received the plates."""
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # owner = AUTH_ORG
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID)
        )
        resp = await editor_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:cancel", json={}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [i["status"] for i in body["items"]] == ["cancelled"]
        assert body["status"] == "closed"

    async def test_unrelated_org_editor_cannot_cancel_owner_initiated_loan(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        database_url: str,
        workspace_id: uuid.UUID,
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # owner = AUTH_ORG
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID)
        )
        async with _client_as(database_url, workspace_id, org_id=uuid.uuid4()) as unrelated:
            resp = await unrelated.post(
                f"/api/v1/plate-loans/{loan['id']}/items:cancel", json={}
            )
            # hidden == missing: unrelated is neither owner (AUTH_ORG) nor
            # borrower (OTHER_ORG), so the loan is invisible to it before
            # _authorize ever runs (same invariant as
            # test_non_owner_editor_cannot_lend_foreign_plate above).
            assert resp.status_code == 404, resp.text

    async def test_owner_org_editor_without_approve_action_cannot_cancel(
        self, client: AsyncClient, denied_editor_client_own_org: AsyncClient
    ) -> None:
        """The fallback's own failure must still surface — an owner-org
        editor who is visibly not the borrower AND lacks cellar:approve_loan
        gets a real 403, not a silently-swallowed pass."""
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # owner = AUTH_ORG
        loan = await _mk_loan(client, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID))
        resp = await denied_editor_client_own_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:cancel", json={}
        )
        assert resp.status_code == 403, resp.text


class TestMyOrgFilterIncludesBorrowed:
    """Spec §5 'plus borrowed-by-us' — S4 deviation #5 closure."""

    async def _borrow_foreign_plate(self, client, editor_client_own_org) -> dict:
        # Admin registers a plate owned by OTHER org, then requests the loan
        # itself (admin's own org == AUTH_ORG == borrower) — a non-admin
        # AUTH-org editor can't see OTHER's plate to borrow it directly.
        plate = await _mk_plate(
            client, f"BR-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        await _mk_loan(client, plate_ids=[plate["id"]])
        return plate

    async def test_my_org_filter_includes_borrowed_foreign_plate(
        self, client, editor_client_own_org
    ) -> None:
        plate = await self._borrow_foreign_plate(client, editor_client_own_org)
        # OTHER is excluded from AUTH_ORG's editor by strict-by-default (no
        # policy needed). The plate only survives if BOTH the owner-scope
        # OR-arm and the exclusion AND-arm's borrowed carve-out admit it —
        # not just the OR-arm, which is all the un-excluded case exercises.
        resp = await editor_client_own_org.get(
            "/api/v1/plates", params={"owner_org_id": str(AUTH_ORG_ID)}
        )
        assert resp.status_code == 200
        assert plate["id"] in [p["id"] for p in resp.json()]

    async def test_explicit_foreign_org_filter_not_widened(
        self, client, editor_client_own_org
    ) -> None:
        # A random third org gets no widening — the borrowed carve-out only
        # ever re-admits via the plate's actual owner, so it stays hidden.
        # Filtering the OWNER org itself (OTHER, excluded by strict-by-default)
        # needs no widening either: the plain owner_org_id match already
        # selects it, and the exclusion AND-arm's borrowed re-admit keeps it
        # visible despite OTHER being excluded — asserted below.
        plate = await self._borrow_foreign_plate(client, editor_client_own_org)
        third = uuid.uuid4()
        resp = await editor_client_own_org.get(
            "/api/v1/plates", params={"owner_org_id": str(third)}
        )
        assert plate["id"] not in [p["id"] for p in resp.json()]

        resp = await editor_client_own_org.get(
            "/api/v1/plates", params={"owner_org_id": str(OTHER_ORG_ID)}
        )
        assert plate["id"] in [p["id"] for p in resp.json()]


class TestReturnComments:
    """Spec §7.3: one non-empty comment per distinct group among the returning plates."""

    async def _checked_out_loan_with_groups(
        self, client: AsyncClient
    ) -> tuple[dict, dict, dict, dict]:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False, confirmation="none")
        g1 = await _mk_group(client, f"G1-{uuid.uuid4().hex[:6]}")
        g2 = await _mk_group(client, f"G2-{uuid.uuid4().hex[:6]}")
        p1 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        p2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        p3 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # ungrouped
        for gid, pid in ((g1["id"], p1["id"]), (g2["id"], p2["id"])):
            r = await client.post(f"/api/v1/plate-groups/{gid}/plates", json={"plate_ids": [pid]})
            assert r.status_code == 204, r.text
        loan = await _mk_loan(client, plate_ids=[p1["id"], p2["id"], p3["id"]])
        assert {i["status"] for i in loan["items"]} == {"checked_out"}
        return loan, g1, g2, p1

    async def test_items_expose_group(self, client: AsyncClient) -> None:
        loan, g1, _g2, p1 = await self._checked_out_loan_with_groups(client)
        by_plate = {i["plate_id"]: i for i in loan["items"]}
        assert by_plate[p1["id"]]["group_id"] == g1["id"]
        assert by_plate[p1["id"]]["group_name"] == g1["name"]
        assert sum(1 for i in loan["items"] if i["group_id"] is None) == 1

    async def test_missing_group_comment_422_names_groups(self, client: AsyncClient) -> None:
        loan, g1, g2, _ = await self._checked_out_loan_with_groups(client)
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={"comments": [{"group_id": g1["id"], "body": "0.5 uL for NadE"}]},
        )
        assert resp.status_code == 422, resp.text
        assert g2["name"] in resp.text and g1["name"] not in resp.text
        # nothing moved
        got = (await client.get(f"/api/v1/plate-loans/{loan['id']}")).json()
        assert {i["status"] for i in got["items"]} == {"checked_out"}

    async def test_blank_comment_counts_as_missing(self, client: AsyncClient) -> None:
        loan, g1, g2, _ = await self._checked_out_loan_with_groups(client)
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={
                "comments": [
                    {"group_id": g1["id"], "body": "  "},
                    {"group_id": g2["id"], "body": "ok"},
                ]
            },
        )
        assert resp.status_code == 422, resp.text

    async def test_comments_written_in_loan_context(self, client: AsyncClient) -> None:
        loan, g1, g2, p1 = await self._checked_out_loan_with_groups(client)
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={
                "comments": [
                    {"group_id": g1["id"], "body": "0.5 uL for NadE"},
                    {"group_id": g2["id"], "body": "untouched"},
                ],
                "plate_comments": [
                    {"plate_id": p1["id"], "body": "removed 12.5 uL from each well"}
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        # confirmation=none collapses request-return straight to returned
        assert {i["status"] for i in resp.json()["items"]} == {"returned"}
        feed = (await client.get("/api/v1/comments", params={"loan_id": loan["id"]})).json()
        assert sorted(c["body"] for c in feed) == [
            "0.5 uL for NadE",
            "removed 12.5 uL from each well",
            "untouched",
        ]
        g1_feed = (
            await client.get(
                "/api/v1/comments",
                params={"target_type": "plate_group", "target_id": g1["id"]},
            )
        ).json()
        assert [c["body"] for c in g1_feed] == ["0.5 uL for NadE"]
        assert g1_feed[0]["loan_id"] == loan["id"]

    async def test_partial_return_only_requires_groups_of_returning_items(
        self, client: AsyncClient
    ) -> None:
        loan, g1, _g2, p1 = await self._checked_out_loan_with_groups(client)
        item_p1 = next(i["id"] for i in loan["items"] if i["plate_id"] == p1["id"])
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={"item_ids": [item_p1], "comments": [{"group_id": g1["id"], "body": "done"}]},
        )
        assert resp.status_code == 200, resp.text

    async def test_ungrouped_plates_need_no_comment(self, client: AsyncClient) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={}
        )
        assert resp.status_code == 200, resp.text

    async def test_unknown_field_still_forbidden_on_other_verbs(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:approve", json={"comments": []}
        )
        assert resp.status_code == 422, resp.text
