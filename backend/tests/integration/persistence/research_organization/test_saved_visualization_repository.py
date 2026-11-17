"""Integration tests for SQLAlchemySavedVisualizationRepository."""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.saved_visualization import SavedVisualization
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.saved_visualization_repository import (  # noqa: E501
    SQLAlchemySavedVisualizationRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

A = uuid.uuid4()
B = uuid.uuid4()


def _config() -> dict:
    return {
        "config_version": 1,
        "panels": [
            {"id": "p1", "type": "scatter", "x": "dose", "logX": True, "overlay": {"fit": "4pl"}}
        ],
        "filters": [{"id": "f1", "kind": "category", "key": "well_type", "values": ["sample"]}],
        "labels": {"rd:X:raw": "Signal"},
    }


def _view(
    ws: uuid.UUID,
    name: str,
    *,
    owner: uuid.UUID = A,
    protocol_ids: tuple[uuid.UUID, ...] = (),
    project_id: uuid.UUID | None = None,
) -> SavedVisualization:
    protocols = protocol_ids or (uuid.uuid4(),)
    return SavedVisualization.create(
        workspace_id=ws,
        name=name,
        source={"kind": "protocol", "protocol_id": str(protocols[0]), "run_ids": None},
        protocol_ids=protocols,
        level="wells",
        config=_config(),
        visibility=SearchVisibility.PROJECT if project_id else SearchVisibility.PRIVATE,
        project_id=project_id,
        created_by=owner,
    )


async def _seed(uow: AsyncUnitOfWork, ws: uuid.UUID, *views: SavedVisualization) -> None:
    async with uow:
        repo = SQLAlchemySavedVisualizationRepository(uow)
        for view in views:
            await repo.save(view)
        await uow.commit()


async def _project(uow: AsyncUnitOfWork, ws: uuid.UUID, name: str) -> uuid.UUID:
    project = Project.create(workspace_id=ws, name=name, created_by=A)
    async with uow:
        await SQLAlchemyProjectRepository(uow).save(project)
        await uow.commit()
    return project.id


async def _visible(uow: AsyncUnitOfWork, ws: uuid.UUID, user: uuid.UUID, **kw) -> list[str]:
    async with uow:
        views = await SQLAlchemySavedVisualizationRepository(uow).find_visible(ws, user, **kw)
    return [v.name for v in views]


async def test_round_trip_keeps_source_config_protocols_and_level(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    view = _view(ws, "IC50 overview", protocol_ids=(p1, p2))
    await _seed(uow, ws, view)

    async with uow:
        loaded = await SQLAlchemySavedVisualizationRepository(uow).find_by_id_in_workspace(
            ws, view.id
        )

    assert loaded is not None
    assert loaded.source == view.source
    assert loaded.config == _config()
    assert loaded.config["panels"][0]["overlay"] == {"fit": "4pl"}
    assert loaded.protocol_ids == (p1, p2)
    assert loaded.level == "wells"
    assert loaded.visibility == SearchVisibility.PRIVATE
    assert loaded.created_by == A
    assert loaded.version == 1


async def test_update_bumps_version(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    view = _view(ws, "Old")
    await _seed(uow, ws, view)

    async with uow:
        repo = SQLAlchemySavedVisualizationRepository(uow)
        loaded = await repo.find_by_id_in_workspace(ws, view.id)
        assert loaded is not None
        loaded.update(expected_version=1, name="New", level="compounds")
        await repo.save(loaded)
        await uow.commit()

    async with uow:
        reloaded = await SQLAlchemySavedVisualizationRepository(uow).find_by_id_in_workspace(
            ws, view.id
        )
    assert reloaded is not None
    assert (reloaded.name, reloaded.level, reloaded.version) == ("New", "compounds", 2)


async def test_find_visible_member_sees_own_and_their_projects(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    x = await _project(uow, ws, "X")
    y = await _project(uow, ws, "Y")
    await _seed(
        uow,
        ws,
        _view(ws, "a private"),
        _view(ws, "b private", owner=B),
        _view(ws, "b on X", owner=B, project_id=x),
        _view(ws, "b on Y", owner=B, project_id=y),
    )

    assert await _visible(uow, ws, A, project_ids=[x]) == ["a private", "b on X"]
    assert await _visible(uow, ws, A, project_ids=[]) == ["a private"]


async def test_find_visible_admin_sees_every_project_view_but_no_one_elses_private(
    uow: AsyncUnitOfWork,
) -> None:
    ws = uuid.uuid4()
    x = await _project(uow, ws, "X")
    y = await _project(uow, ws, "Y")
    await _seed(
        uow,
        ws,
        _view(ws, "a private"),
        _view(ws, "b private", owner=B),
        _view(ws, "b on X", owner=B, project_id=x),
        _view(ws, "b on Y", owner=B, project_id=y),
    )

    assert await _visible(uow, ws, A, project_ids=None) == ["a private", "b on X", "b on Y"]


async def test_find_visible_by_protocol(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    p, q = uuid.uuid4(), uuid.uuid4()
    await _seed(
        uow,
        ws,
        _view(ws, "on p", protocol_ids=(p,)),
        _view(ws, "on q with p added", protocol_ids=(q, p)),
        _view(ws, "on q", protocol_ids=(q,)),
    )

    assert await _visible(uow, ws, A, project_ids=None, protocol_id=p) == [
        "on p",
        "on q with p added",
    ]


async def test_find_visible_never_crosses_workspaces(uow: AsyncUnitOfWork) -> None:
    ws, other = uuid.uuid4(), uuid.uuid4()
    p = uuid.uuid4()
    other_project = await _project(uow, other, "Elsewhere")
    await _seed(uow, other, _view(other, "foreign", protocol_ids=(p,), project_id=other_project))
    await _seed(uow, other, _view(other, "foreign private", protocol_ids=(p,)))

    assert await _visible(uow, ws, A, project_ids=None) == []
    assert await _visible(uow, ws, A, project_ids=[other_project], protocol_id=p) == []
    async with uow:
        repo = SQLAlchemySavedVisualizationRepository(uow)
        assert await repo.find_by_id_in_workspace(ws, uuid.uuid4()) is None


async def test_project_view_whose_project_is_gone_loads_as_private(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    x = await _project(uow, ws, "X")
    view = _view(ws, "shared", owner=B, project_id=x)
    await _seed(uow, ws, view)
    async with uow:
        await uow.session.execute(
            sa.text("UPDATE saved_visualizations SET project_id = NULL WHERE id = :id"),
            {"id": view.id},
        )
        await uow.commit()

    async with uow:
        loaded = await SQLAlchemySavedVisualizationRepository(uow).find_by_id_in_workspace(
            ws, view.id
        )
    assert loaded is not None
    assert (loaded.visibility, loaded.project_id) == (SearchVisibility.PRIVATE, None)
    # No longer shared: only its owner sees it.
    assert await _visible(uow, ws, A, project_ids=None) == []
    assert await _visible(uow, ws, B, project_ids=[]) == ["shared"]


async def test_delete_is_workspace_scoped(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    view = _view(ws, "keep")
    await _seed(uow, ws, view)

    async with uow:
        repo = SQLAlchemySavedVisualizationRepository(uow)
        await repo.delete(uuid.uuid4(), view.id)
        await uow.commit()
    assert await _visible(uow, ws, A, project_ids=[]) == ["keep"]

    async with uow:
        repo = SQLAlchemySavedVisualizationRepository(uow)
        await repo.delete(ws, view.id)
        await uow.commit()
    assert await _visible(uow, ws, A, project_ids=[]) == []
