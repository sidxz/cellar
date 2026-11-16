"""API: /api/v1/saved-visualizations — named workbench views."""

from __future__ import annotations

import uuid
from contextlib import AsyncExitStack
from datetime import date
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.infrastructure.messaging.audit_event_handler import register_audit_handler
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_member_repository import (  # noqa: E501
    SQLAlchemyProjectMemberRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

URL = "/api/v1/saved-visualizations"
OWNER_RULE = "Only the owner or a workspace admin can change this view."
OWNER, MEMBER, OUTSIDER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

CONFIG: dict[str, Any] = {
    "config_version": 1,
    "panels": [{"id": "p1", "type": "scatter", "x": "well_order", "y": "rd:X:raw", "logX": True}],
    "filters": [{"id": "f1", "kind": "category", "key": "well_type", "values": ["sample"]}],
    "labels": {"rd:X:raw": "Signal"},
}


@pytest.fixture
async def as_user(database_url, _run_migrations, workspace_id):
    """``await as_user(role, user_id)`` → a client acting as that user in the test workspace."""
    stack = AsyncExitStack()
    apps = []

    async def _make(role: str, user: uuid.UUID) -> AsyncClient:
        app = _create_test_app(
            database_url, FakeAuth(role=role, workspace_id=workspace_id, user_id=user)
        )
        apps.append(app)
        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        return await stack.enter_async_context(
            AsyncClient(transport=transport, base_url="http://test")
        )

    yield _make
    await stack.aclose()
    for app in apps:
        await app.state.container[AsyncEngine].dispose()


async def _seed(session_factory, ws: uuid.UUID) -> dict[str, Any]:
    """Protocol P with 3 runs, protocol Q with 1, project X (OWNER and MEMBER edit there)."""
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        s = uow.session
        p = await seed.protocol(s, ws)
        runs = [await seed.run(s, ws, p, date(2026, 11, d), status="approved") for d in (3, 4, 5)]
        q = await seed.protocol(s, ws)
        q_run = await seed.run(s, ws, q, date(2026, 11, 6))
        project = Project.create(workspace_id=ws, name="Kinase", created_by=OWNER)
        await SQLAlchemyProjectRepository(uow).save(project)
        await uow.commit()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        for user in (OWNER, MEMBER):
            await SQLAlchemyProjectMemberRepository(uow).add_member(
                ws, project.id, user, ProjectRole.EDITOR
            )
        await uow.commit()
    return {"p": p, "runs": runs, "q": q, "q_run": q_run, "x": project.id}


async def _sql(session_factory, statement: str, **params: Any) -> None:
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await uow.session.execute(sa.text(statement), params)
        await uow.commit()


def _protocol(pid: uuid.UUID, run_ids: list[uuid.UUID] | None = None) -> dict[str, Any]:
    return {
        "kind": "protocol",
        "protocol_id": str(pid),
        "run_ids": None if run_ids is None else [str(r) for r in run_ids],
    }


def _body(source: dict[str, Any], level: str = "wells", **kw: Any) -> dict[str, Any]:
    dataset = {"source": source, "level": level}
    return {"name": "Plate drift", "dataset": dataset, "config": CONFIG} | kw


async def _create(c: AsyncClient, source: dict[str, Any], **kw: Any) -> dict[str, Any]:
    resp = await c.post(URL, json=_body(source, **kw))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- create


async def test_create_echoes_the_view_and_is_audited(api_app, client, session_factory, fake_auth):
    container = api_app.state.container  # as the app's lifespan does
    register_audit_handler(container[EventDispatcher], container[async_sessionmaker])
    w = await _seed(session_factory, fake_auth.workspace_id)
    source = _protocol(w["p"], w["runs"][:2])

    view = await _create(client, source, level="compounds", description="Edge wells")

    assert view["version"] == 1 and view["can_edit"] is True
    assert view["name"] == "Plate drift" and view["description"] == "Edge wells"
    assert view["visibility"] == "private" and view["level"] == "compounds"
    assert view["dataset"] == {"source": source | {"compare": []}, "level": "compounds"}
    assert view["config"] == CONFIG and view["unresolved"] == []
    audit = await client.get(
        "/api/v1/audit", params={"entity_type": "SavedVisualization", "entity_id": view["id"]}
    )
    assert audit.status_code == 200 and len(audit.json()["items"]) == 1


async def test_every_plot_and_filter_kind_reopens_as_saved(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    overlays = {
        "bands": True,
        "refLine": 50,
        "limits": {"mode": "entered", "lower": 1, "upper": 9},
    }
    config = CONFIG | {
        "panels": [
            CONFIG["panels"][0] | {"overlays": overlays},
            {"id": "p2", "type": "rgroup-matrix", "x": "chem:rg1:R2", "category": "chem:rg1:R1"},
        ],
        "filters": [
            *CONFIG["filters"],
            {"id": "sub-1", "kind": "substructure", "query": "c1ccccc1", "queryKind": "smiles"},
        ],
    }
    view = await _create(client, _protocol(w["p"]), config=config)

    opened = await client.get(f"{URL}/{view['id']}")

    assert opened.status_code == 200 and opened.json()["config"] == config


async def test_viewer_cannot_save_a_view(as_user, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    viewer = await as_user("viewer", uuid.uuid4())

    assert (await viewer.post(URL, json=_body(_protocol(w["p"])))).status_code == 403


async def test_sharing_with_a_project(as_user, client, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    outsider = await as_user("editor", OUTSIDER)
    member = await as_user("editor", MEMBER)
    shared = {"visibility": "project", "project_id": str(w["x"])}

    no_project = await member.post(URL, json=_body(_protocol(w["p"]), visibility="project"))
    not_member = await outsider.post(URL, json=_body(_protocol(w["p"]), **shared))
    by_member = await member.post(URL, json=_body(_protocol(w["p"]), **shared))
    by_admin = await client.post(URL, json=_body(_protocol(w["p"]), **shared))

    assert no_project.status_code == 422, no_project.text
    assert not_member.status_code == 403, not_member.text
    assert by_member.status_code == 201, by_member.text
    assert by_admin.status_code == 201 and by_admin.json()["project_id"] == str(w["x"])


async def test_a_private_view_keeps_no_project(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    foreign = await _seed(session_factory, uuid.uuid4())

    for project in (foreign["x"], uuid.uuid4()):  # another workspace's, and none at all
        resp = await client.post(URL, json=_body(_protocol(w["p"]), project_id=str(project)))
        assert resp.status_code == 201, resp.text
        view = resp.json()
        assert view["visibility"] == "private" and view["project_id"] is None
        patched = await client.patch(
            f"{URL}/{view['id']}", json={"expected_version": 1, "project_id": str(project)}
        )
        assert patched.status_code == 200 and patched.json()["project_id"] is None


async def test_a_source_outside_the_workspace_is_not_found(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    foreign = await _seed(session_factory, uuid.uuid4())

    foreign_protocol = await client.post(URL, json=_body(_protocol(foreign["p"])))
    run_of_other_protocol = await client.post(URL, json=_body(_protocol(w["p"], [w["q_run"]])))
    foreign_run = await client.post(
        URL, json=_body({"kind": "run", "run_id": str(foreign["runs"][0])})
    )

    assert foreign_protocol.status_code == 404
    assert run_of_other_protocol.status_code == 404
    assert foreign_run.status_code == 404


async def test_a_source_the_dataset_would_refuse_is_not_saved(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    compared = _protocol(w["p"]) | {"compare": [{"protocol_id": str(w["q"])}]}
    twice = _protocol(w["p"]) | {"compare": [{"protocol_id": str(w["p"])}]}
    view = await _create(client, _protocol(w["p"]))

    at_wells = await client.post(URL, json=_body(compared, level="wells"))
    loaded_twice = await client.post(URL, json=_body(twice, level="compounds"))
    changed_to_wells = await client.patch(
        f"{URL}/{view['id']}",
        json={"expected_version": 1, "dataset": {"source": compared, "level": "wells"}},
    )

    for resp in (at_wells, changed_to_wells):
        assert resp.status_code == 422, resp.text
        assert resp.json()["message"] == "Comparing protocols works at the Compounds level only."
    assert loaded_twice.status_code == 422, loaded_twice.text
    assert loaded_twice.json()["message"] == "Each protocol can be loaded once."


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (CONFIG | {"filters": [{"id": "f1", "kind": "rows", "key": "row"}]}, "Selections"),
        (CONFIG | {"panels": [{"id": f"p{i}", "type": "bar"} for i in range(5)]}, "panels"),
        (CONFIG | {"config_version": 3}, "newer version"),
        (
            CONFIG
            | {
                "config_version": 2,
                "derived": [
                    {
                        "id": "series",
                        "kind": "series",
                        "members": [{"name": f"S{n}", "scaffold": "c1ccccc1"} for n in range(9)],
                    }
                ],
            },
            "members",
        ),
        (CONFIG | {"config_version": 2, "derived": [{"id": "x", "kind": "pca"}]}, "derived"),
        (
            CONFIG
            | {
                "filters": [
                    {
                        "id": "sub-1",
                        "kind": "substructure",
                        "query": "c1ccccc1",
                        "queryKind": "smiles",
                        "moleculeIds": [str(uuid.uuid4())],
                    }
                ]
            },
            "moleculeIds",
        ),
        (
            CONFIG
            | {
                "filters": [
                    {"id": "f1", "kind": "category", "key": "compound", "values": ["x" * 70_000]}
                ]
            },
            "64 KB",
        ),
    ],
    ids=[
        "selection",
        "five-panels",
        "newer-version",
        "nine-series-members",
        "unknown-derived-kind",
        "substructure-matches",
        "too-large",
    ],
)
async def test_unsavable_settings_are_refused(client, session_factory, fake_auth, config, message):
    w = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(URL, json=_body(_protocol(w["p"]), config=config))

    assert resp.status_code == 422, resp.text
    assert message in resp.json()["message"]


# --- read


async def test_who_can_open_a_view(as_user, client, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    owner = await as_user("editor", OWNER)
    member = await as_user("editor", MEMBER)
    outsider = await as_user("editor", OUTSIDER)
    private = await _create(owner, _protocol(w["p"]))
    shared = await _create(owner, _protocol(w["p"]), visibility="project", project_id=str(w["x"]))

    assert (await member.get(f"{URL}/{private['id']}")).status_code == 404
    assert (await client.get(f"{URL}/{private['id']}")).status_code == 404  # admins too
    as_member = await member.get(f"{URL}/{shared['id']}")
    assert as_member.status_code == 200 and as_member.json()["can_edit"] is False
    assert (await outsider.get(f"{URL}/{shared['id']}")).status_code == 404
    as_admin = await client.get(f"{URL}/{shared['id']}")
    assert as_admin.status_code == 200 and as_admin.json()["can_edit"] is True


async def test_list_a_protocols_views(as_user, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    owner = await as_user("editor", OWNER)
    member = await as_user("editor", MEMBER)
    await _create(owner, _protocol(w["p"]), name="Mine")
    await _create(
        owner, _protocol(w["p"]), name="Shared", visibility="project", project_id=str(w["x"])
    )
    await _create(owner, {"kind": "run", "run_id": str(w["runs"][0])}, name="From a run")
    await _create(owner, _protocol(w["q"]), name="Other protocol")

    mine = await owner.get(URL, params={"protocol_id": str(w["p"])})
    theirs = await member.get(URL, params={"protocol_id": str(w["p"])})

    assert mine.status_code == 200
    assert [v["name"] for v in mine.json()] == ["From a run", "Mine", "Shared"]
    assert all(v["can_edit"] for v in mine.json())
    assert [(v["name"], v["can_edit"]) for v in theirs.json()] == [("Shared", False)]


async def test_an_unreadable_view_is_left_out_of_the_list_and_says_why_on_open(
    client, session_factory, fake_auth, monkeypatch
):
    from cellar.infrastructure.persistence.sqlalchemy.research_organization import (
        saved_visualization_repository as repo_module,
    )

    warnings: list[str] = []
    # Record the event on the module's own logger: global logging state left by earlier
    # tests (cached structlog loggers, stdlib handlers) must not decide this test.
    monkeypatch.setattr(
        repo_module.log, "warning", lambda event, **_: warnings.append(event), raising=False
    )
    w = await _seed(session_factory, fake_auth.workspace_id)
    good = await _create(client, _protocol(w["p"]), name="Good")
    bad = await _create(client, _protocol(w["p"]), name="From a newer version")
    newer = '{"config_version": 99, "panels": [], "filters": []}'
    await _sql(
        session_factory,
        "UPDATE saved_visualizations SET config = cast(:c as jsonb) WHERE id = :v",
        c=newer,
        v=bad["id"],
    )

    listed = await client.get(URL, params={"protocol_id": str(w["p"])})
    opened = await client.get(f"{URL}/{bad['id']}")

    assert listed.status_code == 200, listed.text
    assert [v["id"] for v in listed.json()] == [good["id"]]
    assert warnings == ["saved_visualization.list_skipped"]
    assert opened.status_code == 422
    assert "saved by a newer version" in opened.json()["message"]


# --- update


async def test_only_the_owner_or_an_admin_changes_a_view(
    as_user, client, session_factory, workspace_id
):
    w = await _seed(session_factory, workspace_id)
    owner = await as_user("editor", OWNER)
    member = await as_user("editor", MEMBER)
    view = await _create(owner, _protocol(w["p"]), visibility="project", project_id=str(w["x"]))

    by_member = await member.patch(
        f"{URL}/{view['id']}", json={"expected_version": 1, "name": "Mine now"}
    )
    by_admin = await client.patch(
        f"{URL}/{view['id']}", json={"expected_version": 1, "name": "Renamed"}
    )

    assert by_member.status_code == 403 and by_member.json()["message"] == OWNER_RULE
    assert by_admin.status_code == 200, by_admin.text
    assert by_admin.json()["version"] == 2 and by_admin.json()["name"] == "Renamed"


async def test_owner_saves_new_settings(as_user, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    owner = await as_user("editor", OWNER)
    view = await _create(owner, _protocol(w["p"]))
    config = CONFIG | {"panels": [{"id": "p9", "type": "histogram", "x": "dose"}]}
    dataset = {"source": {"kind": "run", "run_id": str(w["q_run"])}, "level": "runs"}

    resp = await owner.patch(
        f"{URL}/{view['id']}", json={"expected_version": 1, "dataset": dataset, "config": config}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["dataset"] == dataset and resp.json()["config"] == config
    listed = await owner.get(URL, params={"protocol_id": str(w["q"])})
    assert [v["id"] for v in listed.json()] == [view["id"]]


async def test_a_stale_edit_is_refused(as_user, client, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    owner = await as_user("editor", OWNER)
    view = await _create(owner, _protocol(w["p"]), visibility="project", project_id=str(w["x"]))
    first = await owner.patch(f"{URL}/{view['id']}", json={"expected_version": 1, "name": "A"})
    assert first.status_code == 200, first.text

    stale = await client.patch(f"{URL}/{view['id']}", json={"expected_version": 1, "name": "B"})

    assert stale.status_code == 409 and stale.json()["error"] == "StaleEditError"
    assert (await owner.get(f"{URL}/{view['id']}")).json()["name"] == "A"


async def test_an_edit_that_changes_nothing_keeps_the_version(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    view = await _create(client, _protocol(w["p"]))

    same = await client.patch(
        f"{URL}/{view['id']}",
        json={"expected_version": 1, "name": view["name"], "config": CONFIG},
    )

    assert same.status_code == 200 and same.json()["version"] == 1
    assert (await client.get(f"{URL}/{view['id']}")).json()["version"] == 1


async def test_an_edit_needs_the_version_it_was_made_from(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    view = await _create(client, _protocol(w["p"]))

    resp = await client.patch(f"{URL}/{view['id']}", json={"name": "No version"})

    assert resp.status_code == 422


# --- delete


async def test_delete_a_view(as_user, session_factory, workspace_id):
    w = await _seed(session_factory, workspace_id)
    owner = await as_user("editor", OWNER)
    member = await as_user("editor", MEMBER)
    view = await _create(owner, _protocol(w["p"]), visibility="project", project_id=str(w["x"]))

    assert (await member.delete(f"{URL}/{view['id']}")).status_code == 403
    assert (await owner.delete(f"{URL}/{view['id']}")).status_code == 204
    assert (await owner.get(f"{URL}/{view['id']}")).status_code == 404


# --- opening a view whose data changed


async def test_a_deleted_run_is_left_out(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    view = await _create(client, _protocol(w["p"], w["runs"]))
    await _sql(session_factory, "DELETE FROM runs WHERE id = :r", r=w["runs"][0])

    body = (await client.get(f"{URL}/{view['id']}")).json()

    assert body["dataset"]["source"]["run_ids"] == [str(r) for r in w["runs"][1:]]
    assert body["unresolved"] == [
        "1 of the 3 runs this view was saved with no longer exists; it was left out."
    ]


async def test_an_edit_answers_with_what_still_exists(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    view = await _create(client, _protocol(w["p"], w["runs"][:2]))
    await _sql(session_factory, "DELETE FROM runs WHERE id = :r", r=w["runs"][0])

    renamed = await client.patch(
        f"{URL}/{view['id']}", json={"expected_version": 1, "name": "Renamed"}
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["dataset"]["source"]["run_ids"] == [str(w["runs"][1])]
    assert renamed.json()["unresolved"] == [
        "1 of the 2 runs this view was saved with no longer exists; it was left out."
    ]


async def test_all_runs_deleted_opens_every_current_run(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    view = await _create(client, _protocol(w["p"], w["runs"]))
    await _sql(session_factory, "DELETE FROM runs WHERE protocol_id = :p", p=w["p"])

    body = (await client.get(f"{URL}/{view['id']}")).json()

    assert body["dataset"]["source"]["run_ids"] is None
    assert body["unresolved"] == [
        "None of the 3 runs this view was saved with exist any more; "
        "showing every current run of the protocol."
    ]


async def test_a_deleted_protocol_leaves_no_dataset(client, session_factory, fake_auth):
    w = await _seed(session_factory, fake_auth.workspace_id)
    by_protocol = await _create(client, _protocol(w["q"]))
    by_run = await _create(client, {"kind": "run", "run_id": str(w["q_run"])})
    await _sql(session_factory, "DELETE FROM runs WHERE protocol_id = :p", p=w["q"])
    await _sql(session_factory, "DELETE FROM protocols WHERE id = :p", p=w["q"])

    protocol_view = (await client.get(f"{URL}/{by_protocol['id']}")).json()
    run_view = (await client.get(f"{URL}/{by_run['id']}")).json()

    assert protocol_view["dataset"] is None
    assert protocol_view["unresolved"] == ["The protocol this view was built on no longer exists."]
    assert run_view["dataset"] is None
    assert run_view["unresolved"] == ["The run this view was built on no longer exists."]
