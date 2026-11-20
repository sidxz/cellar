"""One default per category, enforced in the use case and the database."""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

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
_M089 = Path(__file__).parents[2] / "alembic" / "versions" / "089_protocol_form_category.py"


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


def _load_m089():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m089", _M089)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_migration_keeps_one_default_per_workspace(session_factory, workspace_id):
    """089's upgrade, run over two legacy defaults in one workspace."""
    m089 = _load_m089()
    insert = text(
        "insert into protocol_forms (id, workspace_id, name, is_default, "
        "readout_templates, version, created_at, updated_at) values "
        "(gen_random_uuid(), :ws, :n, true, '[]'::jsonb, 1, :ts, :ts)"
    )

    def run(sync_conn) -> dict[str, bool]:  # type: ignore[no-untyped-def]
        with Operations.context(MigrationContext.configure(sync_conn)):
            m089.downgrade()
            for name, ts in (
                ("old", datetime(2026, 1, 1, tzinfo=UTC)),
                ("new", datetime(2026, 2, 1, tzinfo=UTC)),
            ):
                sync_conn.execute(insert, {"ws": workspace_id, "n": name, "ts": ts})
            m089.upgrade()
        rows = sync_conn.execute(
            text("select name, is_default from protocol_forms where workspace_id=:ws"),
            {"ws": workspace_id},
        ).all()
        return dict(rows)

    async with session_factory() as s:
        rows = await s.run_sync(lambda sync: run(sync.connection()))
        await s.rollback()  # DDL is transactional: the shared test schema stays at head
    assert rows == {"old": False, "new": True}
