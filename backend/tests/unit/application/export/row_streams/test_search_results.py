from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.row_streams.search_results import SearchResultsRowStream


# ---------------------------------------------------------------------------
# Regression: total_count() must populate columns so RenderExport can pass
# stream.columns to the renderer BEFORE iter_batches() is called.
# See: application/export/render_export.py — renderer.render(columns=stream.columns, ...)
# is called right after `await stream.total_count()`, before iter_batches.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_total_count_populates_columns_before_iter_batches():
    """Calling total_count() must build stream.columns even if iter_batches is never called.

    This is the regression guard for the bug where the renderer received an
    empty columns list, producing a blank Data sheet in XLSX/PDF exports.
    """
    workspace = uuid.uuid4()
    rd_id = uuid.uuid4()

    # Minimal intercept stubs — _expand_protocol_column reads .kind.value and .level.
    ic_ec50 = MagicMock()
    ic_ec50.kind.value = "ec"
    ic_ec50.level = 50.0
    ic_ec50.label = None

    ic_ec90 = MagicMock()
    ic_ec90.kind.value = "ec"
    ic_ec90.level = 90.0
    ic_ec90.label = None

    # Minimal readout-def stub — _expand_protocol_column reads .id, .name, .unit,
    # and getattr(rd, "dose_response_config", None).intercepts.
    drc_cfg = MagicMock()
    drc_cfg.intercepts = [ic_ec50, ic_ec90]

    rd = MagicMock()
    rd.id = rd_id
    rd.name = "Resazurin"
    rd.unit = "µM"
    rd.dose_response_config = drc_cfg

    proto = MagicMock()
    proto.id = uuid.uuid4()
    proto.name = "Mtb_WCA"
    proto.readout_definitions = [rd]

    page_one = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    execute = AsyncMock(return_value=_success(page_one))
    protocols_reader = AsyncMock(return_value=[proto])

    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={
            "query": {"criteria": []},
            "protocol_columns": [f"drc:{rd_id}"],
        },
        execute_search=execute,
        protocols_reader=protocols_reader,
        requested_by=uuid.uuid4(),
    )

    # Columns must be empty before any call.
    assert stream.columns == []

    # --- call ONLY total_count, do NOT touch iter_batches ---
    total = await stream.total_count()
    assert total == 1

    # Columns must now be populated: 10 base columns + 5 per intercept × 2 intercepts + 1 plot = 21
    assert len(stream.columns) > 0, (
        "stream.columns was still empty after total_count(); the renderer would have "
        "received an empty column list and produced a blank Data sheet"
    )
    col_keys = [c.key for c in stream.columns]
    assert f"drc:{rd_id}:ec:50.0::value" in col_keys
    assert f"drc:{rd_id}:ec:90.0::value" in col_keys
    assert f"drc:{rd_id}::plot" in col_keys


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
