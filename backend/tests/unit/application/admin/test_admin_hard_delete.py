import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.admin.admin_delete_registry import register_admin_delete
from chem_vault.application.admin.admin_hard_delete import (
    AdminHardDelete,
    AdminHardDeleteCommand,
    BlockedByDependenciesError,
)
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)


def _auth(workspace_id, role="admin"):
    a = MagicMock()
    a.workspace_id = workspace_id
    a.user_id = uuid.uuid4()
    a.workspace_role = role
    a.is_admin = role == "admin"
    a.has_role = lambda r: True if role == "admin" else (r != "admin")
    return a


@pytest.mark.asyncio
async def test_non_admin_blocked():
    uc = AdminHardDelete(uow=MagicMock(), audit=MagicMock(), container=MagicMock())
    result = await uc(
        AdminHardDeleteCommand(
            workspace_id=uuid.uuid4(),
            entity_type="vocabulary",
            entity_id=uuid.uuid4(),
            reason="x",
        ),
        auth=_auth(uuid.uuid4(), role="editor"),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), AuthorizationError)


@pytest.mark.asyncio
async def test_empty_reason_rejected():
    register_admin_delete(
        entity_type="vocabulary",
        table="controlled_vocabularies",
        label_field="name",
        repo_resolver=lambda c: MagicMock(),
    )
    uc = AdminHardDelete(uow=MagicMock(), audit=MagicMock(), container=MagicMock())
    result = await uc(
        AdminHardDeleteCommand(
            workspace_id=uuid.uuid4(),
            entity_type="vocabulary",
            entity_id=uuid.uuid4(),
            reason="   ",
        ),
        auth=_auth(uuid.uuid4()),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)


@pytest.mark.asyncio
async def test_unknown_entity_type_404():
    uc = AdminHardDelete(uow=MagicMock(), audit=MagicMock(), container=MagicMock())
    result = await uc(
        AdminHardDeleteCommand(
            workspace_id=uuid.uuid4(),
            entity_type="not_a_real_thing",
            entity_id=uuid.uuid4(),
            reason="r",
        ),
        auth=_auth(uuid.uuid4()),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
