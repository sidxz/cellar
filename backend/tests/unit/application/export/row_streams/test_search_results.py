from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.row_streams.search_results import SearchResultsRowStream


@pytest.mark.asyncio
async def test_iter_batches_walks_cursor():
    workspace = uuid.uuid4()
    cursor_uuid = str(uuid.uuid4())
    # total_count() calls _fetch_page(limit=1) — needs its own mock response
    page_total = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=4)
    page1 = MagicMock(items=[_mol("CV-1"), _mol("CV-2")], next_cursor=cursor_uuid, total_count=4)
    page2 = MagicMock(items=[_mol("CV-3"), _mol("CV-4")], next_cursor=None, total_count=4)
    execute = AsyncMock()
    execute.side_effect = [_success(page_total), _success(page1), _success(page2)]

    protocols_reader = AsyncMock(return_value=[])
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={"query": {"criteria": []}, "protocol_columns": []},
        execute_search=execute,
        protocols_reader=protocols_reader,
        requested_by=uuid.uuid4(),
    )
    total = await stream.total_count()
    assert total == 4

    batches = []
    async for b in stream.iter_batches(batch_size=2):
        batches.append([r.raw["registration_number"] for r in b])
    assert batches == [["CV-1", "CV-2"], ["CV-3", "CV-4"]]


def _mol(reg: str):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.registration_number.value = reg
    m.name = f"Mol {reg}"
    m.structure.smiles = "CCO"
    m.structure.inchi_key = "X"
    m.descriptors.molecular_weight = 46.0
    m.descriptors.logp = -0.3
    m.descriptors.hbd = 1
    m.descriptors.hba = 1
    m.descriptors.tpsa = 20.2
    m.descriptors.molecular_formula = "C2H6O"
    return m


def _success(page):
    from returns.result import Success
    from cellar.application.shared.pagination import EnrichedPageResult
    return Success(EnrichedPageResult(
        items=page.items,
        next_cursor=page.next_cursor,
        total_count=page.total_count,
        activity_data=None,
        similarity_scores=None,
    ))
