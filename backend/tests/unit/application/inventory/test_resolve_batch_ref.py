"""Unit tests for resolve_batch_ref helper."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from cellar.application.inventory.resolve_batch_ref import resolve_batch_ref
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.value_objects import Amount, BatchNumber


def _make_batch() -> Batch:
    return Batch.create(
        workspace_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
        batch_number=BatchNumber(value="CC-000001-001"),
        amount=Amount(value=1.0, unit=AmountUnit.MG),
        source=BatchSource.SYNTHESIZED,
        chemist=uuid.uuid4(),
    )


@pytest.mark.asyncio
class TestResolveBatchRef:

    async def test_hits_canonical_first(self) -> None:
        ws = uuid.uuid4()
        canon = _make_batch()
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=canon)
        repo.find_by_external_identifier = AsyncMock(return_value=None)

        out = await resolve_batch_ref(repo, ws, "CC-000001-001")
        assert out is canon
        repo.find_by_external_identifier.assert_not_awaited()

    async def test_falls_back_to_alias(self) -> None:
        ws = uuid.uuid4()
        aliased = _make_batch()
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=None)
        repo.find_by_external_identifier = AsyncMock(return_value=aliased)

        out = await resolve_batch_ref(repo, ws, "SACC-009999-001")
        assert out is aliased
        repo.find_by_external_identifier.assert_awaited_once_with(ws, "SACC-009999-001")

    async def test_returns_none_on_complete_miss(self) -> None:
        ws = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=None)
        repo.find_by_external_identifier = AsyncMock(return_value=None)

        out = await resolve_batch_ref(repo, ws, "NOTHING")
        assert out is None
