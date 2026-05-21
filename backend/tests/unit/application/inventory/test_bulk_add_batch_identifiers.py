"""Unit tests for BulkAddBatchIdentifiers use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Success

from cellar.application.inventory.bulk_add_batch_identifiers import (
    BulkAddBatchIdentifiers,
    BulkAddBatchIdentifiersCommand,
    BulkIdentifierRow,
    RowOutcome,
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


def _settings_repo_default():
    repo = AsyncMock()
    repo.find_by_workspace_id = AsyncMock(return_value=None)
    return repo


@pytest.mark.asyncio
class TestBulkAddBatchIdentifiers:

    async def test_resolved_via_canonical_batch_number_dry_run(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        existing = _make_batch(ws, mol, "CC-000001-001")
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=existing)
        repo.find_by_external_identifier = AsyncMock(return_value=None)
        repo.save = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import 2026-05-21",
            dry_run=True,
            rows=[BulkIdentifierRow(
                row_index=0,
                cellar_batch_number="CC-000001-001",
                cellar_molecule_reg_number=None,
                cellar_batch_sequence=None,
                external_identifier="SACC-0001-001",
                identifier_type="external_lot",
                source=None,
            )],
        ))
        out = result.unwrap()
        assert len(out.outcomes) == 1
        assert out.outcomes[0].status == "resolved"
        assert out.outcomes[0].batch_id == existing.id
        assert out.counts["resolved"] == 1
        repo.save.assert_not_awaited()

    async def test_resolved_via_molecule_reg_plus_sequence(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        existing = _make_batch(ws, mol, "CC-000002-001")
        repo = AsyncMock()
        async def _find_bn(_ws, bn):
            return existing if bn == "CC-000002-001" else None
        repo.find_by_batch_number = AsyncMock(side_effect=_find_bn)
        repo.find_by_external_identifier = AsyncMock(return_value=None)
        repo.save = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import",
            dry_run=True,
            rows=[BulkIdentifierRow(
                row_index=0,
                cellar_batch_number=None,
                cellar_molecule_reg_number="CC-000002",
                cellar_batch_sequence=1,
                external_identifier="SACC-0002-A",
                identifier_type="external_lot",
                source=None,
            )],
        ))
        out = result.unwrap()
        assert out.outcomes[0].status == "resolved"
        assert out.outcomes[0].resolved_batch_number == "CC-000002-001"

    async def test_not_found_when_neither_path_resolves(self) -> None:
        ws = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=None)
        repo.find_by_external_identifier = AsyncMock(return_value=None)
        repo.save = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import",
            dry_run=True,
            rows=[BulkIdentifierRow(
                row_index=0,
                cellar_batch_number="CC-099999-099",
                cellar_molecule_reg_number=None,
                cellar_batch_sequence=None,
                external_identifier="X",
                identifier_type="external_lot",
                source=None,
            )],
        ))
        out = result.unwrap()
        assert out.outcomes[0].status == "not_found"
        assert out.counts["not_found"] == 1

    async def test_conflict_when_alias_on_another_batch(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        target = _make_batch(ws, mol, "CC-000001-001")
        other = _make_batch(ws, mol, "CC-000099-001")
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=target)
        repo.find_by_external_identifier = AsyncMock(return_value=other)
        repo.save = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import",
            dry_run=True,
            rows=[BulkIdentifierRow(
                row_index=0,
                cellar_batch_number="CC-000001-001",
                cellar_molecule_reg_number=None,
                cellar_batch_sequence=None,
                external_identifier="TAKEN-LOT",
                identifier_type="external_lot",
                source=None,
            )],
        ))
        out = result.unwrap()
        assert out.outcomes[0].status == "conflict"
        assert out.outcomes[0].conflict_batch_number == "CC-000099-001"

    async def test_already_mapped_when_alias_on_same_batch(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        target = _make_batch(ws, mol, "CC-000001-001")
        target.add_identifier(BatchIdentifier.create(
            batch_id=target.id, identifier="ALREADY-X",
            identifier_type="external_lot", source="prior import",
            registered_by=uuid.uuid4(),
        ))
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock(return_value=target)
        repo.find_by_external_identifier = AsyncMock(return_value=target)
        repo.save = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import",
            dry_run=True,
            rows=[BulkIdentifierRow(
                row_index=0,
                cellar_batch_number="CC-000001-001",
                cellar_molecule_reg_number=None,
                cellar_batch_sequence=None,
                external_identifier="ALREADY-X",
                identifier_type="external_lot",
                source=None,
            )],
        ))
        out = result.unwrap()
        assert out.outcomes[0].status == "already_mapped"

    async def test_error_when_neither_locator_provided(self) -> None:
        ws = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_batch_number = AsyncMock()
        repo.find_by_external_identifier = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import",
            dry_run=True,
            rows=[BulkIdentifierRow(
                row_index=0,
                cellar_batch_number=None,
                cellar_molecule_reg_number=None,
                cellar_batch_sequence=None,
                external_identifier="X",
                identifier_type="external_lot",
                source=None,
            )],
        ))
        out = result.unwrap()
        assert out.outcomes[0].status == "error"
        assert "locator" in out.outcomes[0].message.lower()

    async def test_commit_path_calls_save_only_for_resolved(self) -> None:
        ws = uuid.uuid4()
        mol = uuid.uuid4()
        target = _make_batch(ws, mol, "CC-000001-001")
        other = _make_batch(ws, mol, "CC-000099-001")
        target2 = _make_batch(ws, mol, "CC-000002-001")
        repo = AsyncMock()
        async def _find_bn(_ws, bn):
            return {"CC-000001-001": target, "CC-000002-001": target2}.get(bn)
        async def _find_alias(_ws, alias):
            return {"WILL-CONFLICT": other}.get(alias)
        repo.find_by_batch_number = AsyncMock(side_effect=_find_bn)
        repo.find_by_external_identifier = AsyncMock(side_effect=_find_alias)
        repo.save = AsyncMock()

        uc = BulkAddBatchIdentifiers(
            uow=_mock_uow(),
            batch_repo=repo,
            settings_repo=_settings_repo_default(),
        )
        result = await uc(BulkAddBatchIdentifiersCommand(
            workspace_id=ws,
            importing_user_id=uuid.uuid4(),
            source_default="CSV import",
            dry_run=False,
            rows=[
                BulkIdentifierRow(
                    row_index=0,
                    cellar_batch_number="CC-000001-001",
                    cellar_molecule_reg_number=None,
                    cellar_batch_sequence=None,
                    external_identifier="OK-LOT",
                    identifier_type="external_lot",
                    source=None,
                ),
                BulkIdentifierRow(
                    row_index=1,
                    cellar_batch_number="CC-000002-001",
                    cellar_molecule_reg_number=None,
                    cellar_batch_sequence=None,
                    external_identifier="WILL-CONFLICT",
                    identifier_type="external_lot",
                    source=None,
                ),
            ],
        ))
        out = result.unwrap()
        assert out.counts["resolved"] == 1
        assert out.counts["conflict"] == 1
        assert repo.save.await_count == 1
