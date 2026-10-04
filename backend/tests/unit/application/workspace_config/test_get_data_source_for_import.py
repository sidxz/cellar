"""GetDataSourceForImport resolves a data source's API key secret, so it needs
the role of the CDD import use cases that call it (editor), not viewer."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
    GetDataSourceForImportQuery,
)
from cellar.domain.shared.errors import AuthorizationError
from tests.fakes.fake_auth import FakeAuth


def _query(workspace_id: uuid.UUID) -> GetDataSourceForImportQuery:
    return GetDataSourceForImportQuery(workspace_id=workspace_id, source_type="cdd_vault")


def _use_case(secrets: AsyncMock) -> GetDataSourceForImport:
    return GetDataSourceForImport(
        uow=AsyncMock(), ds_repo=AsyncMock(), api_key_repo=AsyncMock(), secret_provider=secrets
    )


async def test_viewer_cannot_resolve_the_import_api_key() -> None:
    workspace_id = uuid.uuid4()
    secrets = AsyncMock()
    with pytest.raises(AuthorizationError):
        await _use_case(secrets)(
            _query(workspace_id), auth=FakeAuth(role="viewer", workspace_id=workspace_id)
        )
    secrets.get_secret.assert_not_awaited()


async def test_editor_resolves_the_import_api_key() -> None:
    workspace_id = uuid.uuid4()
    secrets = AsyncMock()
    secrets.get_secret.return_value = "cdd-key"
    result = await _use_case(secrets)(
        _query(workspace_id), auth=FakeAuth(role="editor", workspace_id=workspace_id)
    )
    assert result.unwrap().api_key == "cdd-key"
