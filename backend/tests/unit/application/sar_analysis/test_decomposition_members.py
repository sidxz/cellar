from __future__ import annotations

import uuid

import pytest

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream


class FakeMoleculeFetcher:
    """Returns (id, smiles, version); honors NULL smiles; drops unknown ids."""

    def __init__(self, table: dict[uuid.UUID, tuple[str | None, int]]) -> None:
        self._table = table
        self.calls: list[list[uuid.UUID]] = []

    async def fetch_for_decomposition(self, *, molecule_ids, workspace_id):
        self.calls.append(list(molecule_ids))
        return [
            (mid, self._table[mid][0], self._table[mid][1])
            for mid in molecule_ids
            if mid in self._table
        ]


class FakeCollectionReader:
    """Pages a fixed id list via offset/limit."""

    def __init__(self, ids: list[uuid.UUID]) -> None:
        self._ids = ids

    async def get_molecule_ids(self, workspace_id, collection_id, *, offset, limit):
        return self._ids[offset : offset + limit]


async def _drain(stream, **kwargs):
    out = []
    async for batch in stream.stream(**kwargs):
        out.append(batch)
    return out


@pytest.mark.asyncio
async def test_ad_hoc_ids_are_chunked_by_page_size():
    ids = [uuid.uuid4() for _ in range(5)]
    table = {mid: ("Fc1ccccc1", 1) for mid in ids}
    fetcher = FakeMoleculeFetcher(table)
    stream = DecompositionMemberStream(
        molecule_fetcher=fetcher, collection_reader=FakeCollectionReader([]), page_size=2
    )
    batches = await _drain(stream, workspace_id=uuid.uuid4(), collection_id=None, molecule_ids=ids)
    assert [len(b) for b in batches] == [2, 2, 1]
    flat = [row for b in batches for row in b]
    assert {r[0] for r in flat} == set(ids)


@pytest.mark.asyncio
async def test_collection_source_pages_then_stops_on_short_page():
    ids = [uuid.uuid4() for _ in range(3)]
    table = {ids[0]: ("Fc1ccccc1", 2), ids[1]: (None, 1), ids[2]: ("Clc1ccccc1", 1)}
    fetcher = FakeMoleculeFetcher(table)
    stream = DecompositionMemberStream(
        molecule_fetcher=fetcher,
        collection_reader=FakeCollectionReader(ids),
        page_size=2,
    )
    batches = await _drain(
        stream, workspace_id=uuid.uuid4(), collection_id=uuid.uuid4(), molecule_ids=None
    )
    flat = [row for b in batches for row in b]
    assert len(flat) == 3
    by_id = {mid: (smi, ver) for (mid, smi, ver) in flat}
    assert by_id[ids[1]] == (None, 1)
    assert by_id[ids[0]] == ("Fc1ccccc1", 2)


@pytest.mark.asyncio
async def test_collection_source_handles_exact_multiple_page_boundary():
    ids = [uuid.uuid4() for _ in range(4)]
    table = {mid: ("CCO", 1) for mid in ids}
    stream = DecompositionMemberStream(
        molecule_fetcher=FakeMoleculeFetcher(table),
        collection_reader=FakeCollectionReader(ids),
        page_size=2,
    )
    batches = await _drain(
        stream, workspace_id=uuid.uuid4(), collection_id=uuid.uuid4(), molecule_ids=None
    )
    flat = [row for b in batches for row in b]
    assert len(flat) == 4


@pytest.mark.asyncio
async def test_empty_ad_hoc_source_yields_nothing():
    stream = DecompositionMemberStream(
        molecule_fetcher=FakeMoleculeFetcher({}),
        collection_reader=FakeCollectionReader([]),
    )
    batches = await _drain(
        stream, workspace_id=uuid.uuid4(), collection_id=None, molecule_ids=None
    )
    assert batches == []
