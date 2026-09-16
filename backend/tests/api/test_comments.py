"""Comments API — feed on loans/groups/plates with visibility (spec 2026-08-25 §7)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.conftest import AUTH_ORG_ID, ORG_ID, OTHER_ORG_ID, _create_test_app
from tests.fakes.fake_auth import FakeAuth


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    """An ad-hoc client for an identity distinct from the standard fixtures.

    Copied from ``tests/api/test_plate_loans.py`` (brief instructs not to
    import across test modules).
    """
    auth_kwargs.setdefault("role", "editor")
    auth = FakeAuth(workspace_id=workspace_id, **auth_kwargs)
    app = _create_test_app(database_url, auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


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
    resp = await client.post("/api/v1/plate-groups", json={"name": name, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_loan(client: AsyncClient, **body) -> dict:
    resp = await client.post("/api/v1/plate-loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _post(client: AsyncClient, **body) -> object:
    return await client.post("/api/v1/comments", json=body)


class TestAddAndList:
    async def test_group_comment_round_trips_with_author_name(
        self, editor_client_own_org: AsyncClient, client: AsyncClient
    ) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        resp = await _post(
            editor_client_own_org,
            target_type="plate_group",
            target_id=g["id"],
            body="  screened vs NadE  ",
        )
        assert resp.status_code == 201, resp.text
        c = resp.json()
        assert c["body"] == "screened vs NadE"
        assert c["author_name"] == "Test User"
        assert c["loan_id"] is None
        listed = await editor_client_own_org.get(
            "/api/v1/comments", params={"target_type": "plate_group", "target_id": g["id"]}
        )
        assert listed.status_code == 200, listed.text
        assert [x["id"] for x in listed.json()] == [c["id"]]

    async def test_newest_first(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        for body in ("first", "second"):
            resp = await _post(client, target_type="plate", target_id=plate["id"], body=body)
            assert resp.status_code == 201
        listed = await client.get(
            "/api/v1/comments", params={"target_type": "plate", "target_id": plate["id"]}
        )
        assert [x["body"] for x in listed.json()] == ["second", "first"]

    async def test_loan_comment_and_loan_feed(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await _post(
            client, target_type="plate_loan", target_id=loan["id"], body="By Friday"
        )
        assert resp.status_code == 201, resp.text
        # a plate comment made in the context of this loan shows up on the loan feed too
        resp = await _post(
            client,
            target_type="plate",
            target_id=plate["id"],
            loan_id=loan["id"],
            body="removed 12.5 uL",
        )
        assert resp.status_code == 201, resp.text
        feed = await client.get("/api/v1/comments", params={"loan_id": loan["id"]})
        assert feed.status_code == 200, feed.text
        assert sorted(x["body"] for x in feed.json()) == ["By Friday", "removed 12.5 uL"]

    async def test_loan_context_must_contain_target(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        other = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await _post(
            client, target_type="plate", target_id=other["id"], loan_id=loan["id"], body="x"
        )
        assert resp.status_code == 422, resp.text


class TestValidation:
    async def test_empty_body_422(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await _post(client, target_type="plate", target_id=plate["id"], body="   ")
        assert resp.status_code == 422

    async def test_unknown_target_type_422(self, client: AsyncClient) -> None:
        resp = await _post(client, target_type="batch", target_id=str(uuid.uuid4()), body="x")
        assert resp.status_code == 422

    async def test_list_requires_exactly_one_form(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/comments")).status_code == 422
        resp = await client.get("/api/v1/comments", params={"target_type": "plate"})
        assert resp.status_code == 422


class TestVisibility:
    async def test_hidden_plate_404_for_foreign_editor_visible_for_owner(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await _post(
            editor_client_own_org, target_type="plate", target_id=plate["id"], body="x"
        )
        assert resp.status_code == 404
        resp = await editor_client_own_org.get(
            "/api/v1/comments", params={"target_type": "plate", "target_id": plate["id"]}
        )
        assert resp.status_code == 404
        resp = await _post(
            editor_client_other_org, target_type="plate", target_id=plate["id"], body="x"
        )
        assert resp.status_code == 201

    async def test_borrower_can_comment_on_borrowed_plate(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        # OTHER org lends its plate to AUTH org (owner-initiated, auto-approved)
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(
            editor_client_other_org, plate_ids=[plate["id"]], borrower_org_id=str(AUTH_ORG_ID)
        )
        resp = await _post(
            editor_client_own_org,
            target_type="plate",
            target_id=plate["id"],
            loan_id=loan["id"],
            body="took 1 uL",
        )
        assert resp.status_code == 201, resp.text

    async def test_hidden_group_and_loan_404(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID))
        resp = await _post(
            editor_client_own_org, target_type="plate_group", target_id=g["id"], body="x"
        )
        assert resp.status_code == 404
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        resp = await _post(
            editor_client_own_org, target_type="plate_loan", target_id=loan["id"], body="x"
        )
        assert resp.status_code == 404
        resp = await editor_client_own_org.get(
            "/api/v1/comments", params={"loan_id": loan["id"]}
        )
        assert resp.status_code == 404

    async def test_viewer_can_read_not_write(
        self, client: AsyncClient, database_url: str, workspace_id: uuid.UUID
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await _post(client, target_type="plate", target_id=plate["id"], body="x")
        assert resp.status_code == 201
        async with _client_as(
            database_url, workspace_id, role="viewer", org_id=AUTH_ORG_ID
        ) as viewer_client:
            resp = await viewer_client.get(
                "/api/v1/comments", params={"target_type": "plate", "target_id": plate["id"]}
            )
            assert resp.status_code == 200
            resp = await _post(
                viewer_client, target_type="plate", target_id=plate["id"], body="y"
            )
            assert resp.status_code == 403


class TestBorrowedCarveOutBoundaries:
    """I3(b): the borrowed carve-out is bounded to plates currently on an
    ACTIVE loan to the caller's own org — it must expire when the loan is
    cancelled, and never extend to a plate loaned to a *different* org."""

    async def test_borrowed_carve_out_expires_when_loan_cancelled(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        # OTHER org lends to AUTH org (owner-initiated). Default policy
        # (confirmation=admin_confirm) leaves items APPROVED, not
        # checked_out — CANCELLED is only a valid transition from
        # requested/approved, so this is what makes cancellation reachable.
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(
            editor_client_other_org, plate_ids=[plate["id"]], borrower_org_id=str(AUTH_ORG_ID)
        )
        assert {i["status"] for i in loan["items"]} == {"approved"}
        # Sanity: the carve-out is live before cancellation.
        resp = await _post(
            editor_client_own_org, target_type="plate", target_id=plate["id"], body="pre-cancel"
        )
        assert resp.status_code == 201, resp.text

        # The lender (owner org) cancels the loan — editor_client_other_org
        # is permissive-by-default (no explicit granted_actions), so it
        # already carries the approve action needed for the owner-authority
        # fallback in CancelLoanItems.
        cancel = await editor_client_other_org.post(
            f"/api/v1/plate-loans/{loan['id']}/items:cancel", json={}
        )
        assert cancel.status_code == 200, cancel.text

        resp = await _post(
            editor_client_own_org, target_type="plate", target_id=plate["id"], body="post-cancel"
        )
        assert resp.status_code == 404, resp.text

    async def test_plate_in_another_orgs_loan_still_404(
        self, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        # OTHER org lends to a THIRD org (ORG_ID) — AUTH_ORG_ID is neither
        # the owner nor the borrower, so the borrowed carve-out must not
        # apply to it.
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        await _mk_loan(
            editor_client_other_org, plate_ids=[plate["id"]], borrower_org_id=str(ORG_ID)
        )
        resp = await _post(
            editor_client_own_org, target_type="plate", target_id=plate["id"], body="x"
        )
        assert resp.status_code == 404, resp.text


class TestLoanContainsGroupTarget:
    """I3(c): _loan_contains_target for a group target — a group the caller
    can see but that isn't among the loan's plates' groups is 422, not 404
    (visibility already passed; containment is what fails)."""

    async def test_visible_unrelated_group_422(self, editor_client_own_org: AsyncClient) -> None:
        g = await _mk_group(editor_client_own_org, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(editor_client_own_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_own_org, plate_ids=[plate["id"]])
        resp = await _post(
            editor_client_own_org,
            target_type="plate_group",
            target_id=g["id"],
            loan_id=loan["id"],
            body="x",
        )
        assert resp.status_code == 422, resp.text


class TestAuditActor:
    """I3(d): CommentAdded reaches the audit catch-all with the posting
    user as actor. Harness copied from
    ``tests/api/test_registered_plates.py::TestAuditActor``."""

    @pytest.fixture(autouse=True)
    def _wire_audit_catch_all(self, api_app: FastAPI) -> None:
        """The shared test app never wires the audit catch-all handler (only
        production's ``create_app()`` lifespan does)."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from cellar.domain.shared.events import DomainEvent
        from cellar.infrastructure.messaging.audit_event_handler import AuditEventHandler
        from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher

        container = api_app.state.container
        container[EventDispatcher].register(
            DomainEvent, AuditEventHandler(container[async_sessionmaker])
        )

    @pytest.fixture(autouse=True)
    def _bind_actor_context(self, api_app: FastAPI, fake_auth) -> None:
        """Reproduce ``get_auth``'s ``set_current_actor`` side effect, which
        the shared test override (``tests/api/conftest.py``) bypasses."""
        from cellar.application.shared.actor_context import set_current_actor
        from cellar.interface.dependencies import get_auth

        async def _fake_get_auth():
            # Must be async — FastAPI runs sync dependencies in a threadpool
            # (a copied context), so a plain `def` here would set the
            # ContextVar on a copy that never propagates back to this task.
            set_current_actor(fake_auth.user_id)
            return fake_auth

        api_app.dependency_overrides[get_auth] = _fake_get_auth

    async def test_comment_audit_row_names_the_caller(
        self, client: AsyncClient, user_id: uuid.UUID
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await _post(client, target_type="plate", target_id=plate["id"], body="audited")
        assert resp.status_code == 201, resp.text
        comment_id = resp.json()["id"]

        audit = await client.get(
            "/api/v1/audit", params={"entity_type": "Comment", "entity_id": comment_id}
        )
        assert audit.status_code == 200, audit.text
        rows = audit.json()["items"]
        assert rows, "expected at least one audit row for the comment"
        assert {r["performed_by"] for r in rows} == {str(user_id)}
