"""One default per category, enforced in the use case and the database."""

import uuid
from datetime import UTC, datetime

from cellar.application.workspace_config.create_protocol_form import (
    CreateProtocolForm,
    CreateProtocolFormCommand,
)
from cellar.application.workspace_config.protocol_categories import (
    DeleteProtocolCategory,
    DeleteProtocolCategoryCommand,
)
from cellar.application.workspace_config.update_protocol_form import (
    UpdateProtocolForm,
    UpdateProtocolFormCommand,
)
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_category_repository import (  # noqa: E501
    SQLAlchemyProtocolCategoryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_form_repository import (  # noqa: E501
    SQLAlchemyProtocolFormRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests._auth import admin_auth

READOUT = [{"name": "Signal", "data_type": "numeric"}]


class _NoEvents:
    async def dispatch_all(self, events):
        return None


async def _create_result(session_factory, ws, auth, **kw):
    uow = AsyncUnitOfWork(session_factory)
    uc = CreateProtocolForm(
        uow,
        SQLAlchemyProtocolFormRepository(uow),
        _NoEvents(),
        category_repo=SQLAlchemyProtocolCategoryRepository(uow),
    )
    command = CreateProtocolFormCommand(workspace_id=ws, readout_templates=READOUT, **kw)
    return await uc(command, auth=auth)


async def _create(session_factory, ws, auth, **kw):
    return (await _create_result(session_factory, ws, auth, **kw)).unwrap()


async def _update_result(session_factory, ws, auth, form_id, **kw):
    uow = AsyncUnitOfWork(session_factory)
    uc = UpdateProtocolForm(
        uow,
        SQLAlchemyProtocolFormRepository(uow),
        _NoEvents(),
        category_repo=SQLAlchemyProtocolCategoryRepository(uow),
    )
    return await uc(UpdateProtocolFormCommand(workspace_id=ws, form_id=form_id, **kw), auth=auth)


async def _category(session_factory, ws, label):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        cat = ProtocolCategory.create(workspace_id=ws, label=label)
        await SQLAlchemyProtocolCategoryRepository(uow).save(cat)
        await uow.commit()
    return cat


async def _forms(session_factory, ws):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        return await SQLAlchemyProtocolFormRepository(uow).find_by_workspace(ws)


async def test_a_new_default_replaces_the_categorys_old_default(
    session_factory, workspace_id, user_id
):
    auth = admin_auth(workspace_id, user_id)
    cat = await _category(session_factory, workspace_id, "Enzyme inhibition")
    first = await _create(
        session_factory, workspace_id, auth, name="A", category_id=cat.id, is_default=True
    )
    second = await _create(
        session_factory, workspace_id, auth, name="B", category_id=cat.id, is_default=True
    )
    generic = await _create(session_factory, workspace_id, auth, name="G", is_default=True)
    by_id = {f.id: f for f in await _forms(session_factory, workspace_id)}
    assert not by_id[first.id].is_default and by_id[second.id].is_default
    assert by_id[generic.id].is_default  # other scope untouched


async def test_deleting_a_category_turns_its_forms_generic_without_a_second_default(
    session_factory, workspace_id, user_id
):
    auth = admin_auth(workspace_id, user_id)
    cat = await _category(session_factory, workspace_id, "Binding")
    own = await _create(
        session_factory, workspace_id, auth, name="Kd", category_id=cat.id, is_default=True
    )
    await _create(session_factory, workspace_id, auth, name="G", is_default=True)
    uow = AsyncUnitOfWork(session_factory)
    uc = DeleteProtocolCategory(
        uow,
        SQLAlchemyProtocolCategoryRepository(uow),
        SQLAlchemyProtocolRepository(uow),
        form_repo=SQLAlchemyProtocolFormRepository(uow),
    )
    command = DeleteProtocolCategoryCommand(workspace_id=workspace_id, category_id=cat.id)
    (await uc(command, auth=auth)).unwrap()
    by_id = {f.id: f for f in await _forms(session_factory, workspace_id)}
    assert by_id[own.id].category_id is None and not by_id[own.id].is_default


async def test_a_form_cannot_point_at_another_workspaces_category(
    session_factory, workspace_id, user_id
):
    auth = admin_auth(workspace_id, user_id)
    foreign = await _category(session_factory, uuid.uuid4(), "Binding")
    own = await _create(session_factory, workspace_id, auth, name="Own")

    for category_id in (foreign.id, uuid.uuid4()):
        created = await _create_result(
            session_factory, workspace_id, auth, name="X", category_id=category_id
        )
        assert isinstance(created.failure(), NotFoundError)
        updated = await _update_result(
            session_factory, workspace_id, auth, own.id, category_id=category_id
        )
        assert isinstance(updated.failure(), NotFoundError)

    forms = await _forms(session_factory, workspace_id)
    assert [(f.name, f.category_id) for f in forms] == [("Own", None)]


async def test_migration_keeps_one_default_per_workspace(session_factory, workspace_id):
    """089's dedupe statement, run against two legacy defaults."""
    from sqlalchemy import text

    async with session_factory() as s:
        await s.execute(text("drop index if exists ux_protocol_form_default"))
        for name, ts in (
            ("old", datetime(2026, 1, 1, tzinfo=UTC)),
            ("new", datetime(2026, 2, 1, tzinfo=UTC)),
        ):
            await s.execute(
                text(
                    "insert into protocol_forms (id, workspace_id, name, is_default, "
                    "readout_templates, version, created_at, updated_at) values "
                    "(gen_random_uuid(), :ws, :n, true, '[]'::jsonb, 1, :ts, :ts)"
                ),
                {"ws": workspace_id, "n": name, "ts": ts},
            )
        await s.execute(
            text(
                "update protocol_forms f set is_default = false where f.is_default and exists ("
                "select 1 from protocol_forms g where g.workspace_id = f.workspace_id "
                "and g.is_default and (g.updated_at, g.id) > (f.updated_at, f.id))"
            )
        )
        rows = dict(
            (
                await s.execute(
                    text("select name, is_default from protocol_forms where workspace_id=:ws"),
                    {"ws": workspace_id},
                )
            ).all()
        )
        await s.rollback()
    assert rows == {"old": False, "new": True}
