"""Unit tests for the UpdateDataSource use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Any, Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from chem_vault.application.workspace_config.update_data_source import (
    UpdateDataSource,
    UpdateDataSourceCommand,
)
from chem_vault.domain.workspace_config.data_source import DataSource
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    async def commit(self) -> list:
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


def _make_ds(workspace_id: uuid.UUID, config: dict[str, Any] | None = None) -> DataSource:
    return DataSource(
        workspace_id=workspace_id,
        name="CDD Vault",
        source_type="cdd_vault",
        config=config or {"vault_id": "old-1"},
        created_by=uuid.uuid4(),
    )


def _build_uc(ds: DataSource) -> UpdateDataSource:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=ds)
    repo.save = AsyncMock()

    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()

    return UpdateDataSource(uow=FakeUoW(), repo=repo, dispatcher=dispatcher)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateDataSource:
    @pytest.mark.asyncio
    async def test_update_config_only(self) -> None:
        """Patching config alone replaces the config dict."""
        auth = FakeAuth(role="admin")
        ds = _make_ds(auth.workspace_id, config={"vault_id": "old-1"})
        uc = _build_uc(ds)

        result = await uc(
            UpdateDataSourceCommand(
                workspace_id=auth.workspace_id,
                data_source_id=ds.id,
                config={"vault_id": "new-2"},
            ),
            auth=auth,
        )

        assert isinstance(result, Success)
        assert ds.config == {"vault_id": "new-2"}

    @pytest.mark.asyncio
    async def test_update_create_batch_on_duplicate_only(self) -> None:
        """Patching create_batch_on_duplicate alone merges into existing config."""
        auth = FakeAuth(role="admin")
        ds = _make_ds(auth.workspace_id, config={"vault_id": "old-1"})
        uc = _build_uc(ds)

        result = await uc(
            UpdateDataSourceCommand(
                workspace_id=auth.workspace_id,
                data_source_id=ds.id,
                create_batch_on_duplicate=True,
            ),
            auth=auth,
        )

        assert isinstance(result, Success)
        assert ds.config == {"vault_id": "old-1", "create_batch_on_duplicate": True}

    @pytest.mark.asyncio
    async def test_update_with_both_config_and_create_batch_on_duplicate_preserves_both(
        self,
    ) -> None:
        """When config and create_batch_on_duplicate arrive in the same PATCH,
        both changes must land — config must not be silently discarded."""
        auth = FakeAuth(role="admin")
        ds = _make_ds(auth.workspace_id, config={"vault_id": "old-1"})
        uc = _build_uc(ds)

        result = await uc(
            UpdateDataSourceCommand(
                workspace_id=auth.workspace_id,
                data_source_id=ds.id,
                config={"vault_id": "new-2"},
                create_batch_on_duplicate=True,
            ),
            auth=auth,
        )

        assert isinstance(result, Success)
        assert ds.config == {"vault_id": "new-2", "create_batch_on_duplicate": True}
