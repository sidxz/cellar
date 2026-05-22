"""Unit tests for SyncBatchIdentifierMirrors collaborator."""

from __future__ import annotations

import uuid

import pytest

from cellar.application.inventory.sync_batch_identifier_mirrors import (
    MirrorSummary,
    SyncBatchIdentifierMirrors,
)
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber


WS = uuid.UUID("11111111-1111-1111-1111-111111111111")
MOL = uuid.UUID("22222222-2222-2222-2222-222222222222")
ACTOR = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _batch(number: str, batch_id: uuid.UUID | None = None) -> Batch:
    return Batch(
        workspace_id=WS,
        molecule_id=MOL,
        batch_number=BatchNumber(value=number),
        amount=Amount(value=10.0, unit=AmountUnit.MG),
        source=BatchSource.SYNTHESIZED,
        chemist=ACTOR,
        id=batch_id or uuid.uuid4(),
    )


def _identifier(value: str, ident_id: uuid.UUID | None = None) -> MoleculeIdentifier:
    return MoleculeIdentifier(
        id=ident_id or uuid.uuid4(),
        molecule_id=MOL,
        identifier=value,
        identifier_type="custom",
        source="Registration",
        registered_by=ACTOR,
    )


class _FakeBatchRepo:
    """Captures saved batches; returns None on alias lookup."""

    def __init__(self) -> None:
        self.saved: list[Batch] = []

    async def save(self, batch: Batch) -> None:
        self.saved.append(batch)

    async def find_by_external_identifier(self, workspace_id, identifier):
        return None


@pytest.mark.asyncio
async def test_fan_out_for_new_identifier_creates_one_mirror_per_batch():
    ident = _identifier("SACC-0001")
    batches = [_batch("CC-000001-001"), _batch("CC-000001-002")]
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=batches, actor=ACTOR,
    )

    assert summary.created == 2
    assert summary.skipped == []
    saved_strings = {bi.identifier for b in repo.saved for bi in b.identifiers}
    assert saved_strings == {"SACC-0001-001", "SACC-0001-002"}
    for b in repo.saved:
        for bi in b.identifiers:
            assert bi.identifier_type == "custom"
            assert bi.source == "compound-syn"
            assert bi.derived_from_molecule_identifier_id == ident.id


@pytest.mark.asyncio
async def test_fan_out_for_new_batch_appends_mirrors_in_memory_without_saving():
    batch = _batch("CC-000001-001")
    idents = [_identifier("SACC-0001"), _identifier("VENDOR-FOO")]
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_batch(
        workspace_id=WS, batch=batch, identifiers=idents, actor=ACTOR,
    )

    assert summary.created == 2
    assert summary.skipped == []
    # Pure mutator — does NOT save; caller saves the batch.
    assert repo.saved == []
    mirror_strings = {bi.identifier for bi in batch.identifiers}
    assert mirror_strings == {"SACC-0001-001", "VENDOR-FOO-001"}


@pytest.mark.asyncio
async def test_malformed_batch_number_recorded_as_skip():
    ident = _identifier("SACC-0001")
    batches = [_batch("LEGACY-NO-SUFFIX"), _batch("ALSO_BAD"), _batch("CC-000001-005")]
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=batches, actor=ACTOR,
    )

    assert summary.created == 1
    reasons = {s.reason for s in summary.skipped}
    assert reasons == {"malformed_batch_number"}
    assert len(summary.skipped) == 2


@pytest.mark.asyncio
async def test_already_mapped_on_batch_is_skipped():
    ident = _identifier("SACC-0001")
    batch = _batch("CC-000001-001")
    batch.identifiers.append(
        BatchIdentifier.create(
            batch_id=batch.id,
            identifier="SACC-0001-001",
            identifier_type="external_lot",
            source="chemist input",
            registered_by=ACTOR,
        )
    )
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=[batch], actor=ACTOR,
    )

    assert summary.created == 0
    assert len(summary.skipped) == 1
    assert summary.skipped[0].reason == "already_mapped"
    # Pre-existing manual identifier is preserved (1 entry, untouched).
    assert len(batch.identifiers) == 1
    assert batch.identifiers[0].derived_from_molecule_identifier_id is None


@pytest.mark.asyncio
async def test_workspace_conflict_is_skipped():
    ident = _identifier("SACC-0001")
    other_batch = _batch("CC-999999-099", batch_id=uuid.uuid4())
    target_batch = _batch("CC-000001-001")

    class _Repo(_FakeBatchRepo):
        async def find_by_external_identifier(self, workspace_id, identifier):
            if identifier == "SACC-0001-001":
                return other_batch
            return None

    repo = _Repo()
    sync = SyncBatchIdentifierMirrors(repo)
    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=[target_batch], actor=ACTOR,
    )

    assert summary.created == 0
    assert summary.skipped[0].reason == "workspace_conflict"


@pytest.mark.asyncio
async def test_synonym_with_internal_hyphens_round_trips():
    ident = _identifier("SACC-0036913")
    batch = _batch("CC-036715-001")
    repo = _FakeBatchRepo()
    sync = SyncBatchIdentifierMirrors(repo)

    summary = await sync.fan_out_for_new_identifier(
        workspace_id=WS, identifier=ident, batches=[batch], actor=ACTOR,
    )

    assert summary.created == 1
    assert repo.saved[0].identifiers[-1].identifier == "SACC-0036913-001"


def test_mirror_summary_combines():
    a = MirrorSummary(created=2, skipped=[])
    b = MirrorSummary.empty()
    assert (a + b).created == 2
    assert (a + b).skipped == []
