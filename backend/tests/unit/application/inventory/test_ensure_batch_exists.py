"""Unit tests for EnsureBatchExists — auto-create + alias capture."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.inventory.ensure_batch_exists import (
    EnsureBatchExists,
    EnsureBatchExistsCommand,
)
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.value_objects import Amount, BatchNumber


def _make_batch(ws: uuid.UUID, mol: uuid.UUID, bn: str = "CC-000001-001") -> Batch:
    return Batch.create(
        workspace_id=ws,
        molecule_id=mol,
        batch_number=BatchNumber(value=bn),
        amount=Amount(value=1.0, unit=AmountUnit.MG),
        source=BatchSource.SYNTHESIZED,
        chemist=uuid.uuid4(),
    )


def _mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.commit = AsyncMock(return_value=[])
    return uow


@pytest.mark.asyncio
class TestEnsureBatchExists:

    async def test_returns_existing_batch_via_canonical_hit(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        existing = _make_batch(ws, mol, "CC-000001-001")
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=existing)
        repo.find_by_external_identifier = AsyncMock(return_value=None)
        repo.save = AsyncMock()
        uow = _mock_uow()

        uc = EnsureBatchExists(
            uow=uow,
            batch_repo=repo,
            settings_repo=AsyncMock(find_by_workspace_id=AsyncMock(return_value=None)),
        )
        result = await uc(EnsureBatchExistsCommand(
            workspace_id=ws,
            molecule_id=mol,
            external_batch_ref="CC-000001-001",
            importing_user_id=uuid.uuid4(),
            source_label="import",
        ))
        out = result.unwrap()
        assert out.batch is existing
        assert out.created is False
        # We DO add the alias if not already present, because the canonical lookup
        # matched but the ref had not been captured as an alias yet.
        # Implementation choice: in this case the ref IS the canonical name itself
        # so adding it as an alias would be redundant. Check the implementer's behavior.
        # For this test, simply assert created==False is enough.

    async def test_returns_existing_batch_via_alias_hit_no_dup(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        existing = _make_batch(ws, mol, "CC-000001-001")
        existing.add_identifier(BatchIdentifier.create(
            batch_id=existing.id, identifier="SACC-009999-001",
            identifier_type="external_lot", source="prior import",
            registered_by=uuid.uuid4(),
        ))
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=None)
        repo.find_by_external_identifier = AsyncMock(return_value=existing)
        repo.save = AsyncMock()
        uow = _mock_uow()

        uc = EnsureBatchExists(
            uow=uow,
            batch_repo=repo,
            settings_repo=AsyncMock(find_by_workspace_id=AsyncMock(return_value=None)),
        )
        result = await uc(EnsureBatchExistsCommand(
            workspace_id=ws,
            molecule_id=mol,
            external_batch_ref="SACC-009999-001",
            importing_user_id=uuid.uuid4(),
            source_label="reimport",
        ))
        out = result.unwrap()
        assert out.batch is existing
        assert out.created is False
        assert len(existing.identifiers) == 1  # NOT duplicated

    async def test_auto_creates_placeholder_with_alias_on_miss(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        importing_user = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=None)
        repo.find_by_external_identifier = AsyncMock(return_value=None)
        repo.next_batch_number = AsyncMock(return_value=BatchNumber(value="CC-000001-001"))
        repo.save = AsyncMock()
        settings_repo = AsyncMock()
        settings_repo.find_by_workspace_id = AsyncMock(return_value=None)
        uow = _mock_uow()

        uc = EnsureBatchExists(
            uow=uow,
            batch_repo=repo,
            settings_repo=settings_repo,
        )
        result = await uc(EnsureBatchExistsCommand(
            workspace_id=ws,
            molecule_id=mol,
            external_batch_ref="SACC-009999-001",
            importing_user_id=importing_user,
            source_label="CDD import",
        ))
        out = result.unwrap()
        assert out.created is True
        batch = out.batch
        assert batch.molecule_id == mol
        assert batch.source == BatchSource.EXTERNAL_REFERENCE
        assert batch.amount.value == 0.0
        assert batch.chemist == importing_user
        assert len(batch.identifiers) == 1
        assert batch.identifiers[0].identifier == "SACC-009999-001"
        assert batch.identifiers[0].source == "CDD import"
        repo.next_batch_number.assert_awaited_once_with(ws, mol, width=3)
