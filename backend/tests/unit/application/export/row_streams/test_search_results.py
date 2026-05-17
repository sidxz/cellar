from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.row_streams.search_results import (
    SearchResultsRowStream,
    _activity_parent_token,
    _cell_value,
)
from cellar.application.export.row_streams.base import ColumnSpec


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


# ---------------------------------------------------------------------------
# Bug #1 regression — narrowed drc col_token must look up the parent
# ActivityValue in raw["activity"], not the narrowed key.
# ---------------------------------------------------------------------------

def test_activity_parent_token_strips_intercept_suffix():
    """_activity_parent_token must strip kind+level from a narrowed drc token."""
    rd_id = "abc123"
    assert _activity_parent_token(f"drc:{rd_id}:ec:50.0") == f"drc:{rd_id}"
    assert _activity_parent_token(f"drc:{rd_id}:ic:90.0") == f"drc:{rd_id}"


def test_activity_parent_token_passthrough_for_non_drc():
    """Non-drc tokens and bare drc:<rd_id> tokens must pass through unchanged."""
    assert _activity_parent_token("rd:proto:def") == "rd:proto:def"
    assert _activity_parent_token("drc:someid") == "drc:someid"


def test_cell_value_narrowed_drc_resolves_intercept():
    """A ColumnSpec with key 'drc:<rd_id>:ec:50.0::value' must find the
    ActivityValue keyed by 'drc:<rd_id>' in raw['activity'] and return the
    matching intercept_values entry.

    This is the direct regression guard for Bug #1: before the fix, col_token
    was used as the activity-dict key directly, always yielding None because
    execute_search keys by the parent token 'drc:<rd_id>'.
    """
    rd_id = "abc-def-123"
    narrowed_key = f"drc:{rd_id}:ec:50.0::value"
    parent_key = f"drc:{rd_id}"

    # ActivityValue wire shape (result of dataclasses.asdict on ActivityValue)
    # keyed by the *parent* token — matching what execute_search produces.
    av = {
        "value": 9.99,  # primary fitted value (not the intercept-specific value)
        "qualifier": None,
        "unit": "uM",
        "source": "dose_response",
        "intercept_values": [
            {
                "spec": {"kind": "ec", "level": 50.0, "basis": "response", "label": "EC50"},
                "value": 1.23,
                "confidence_interval_low": 0.9,
                "confidence_interval_high": 1.6,
                "at_bound": False,
            },
            {
                "spec": {"kind": "ec", "level": 90.0, "basis": "response", "label": "EC90"},
                "value": 4.56,
                "confidence_interval_low": None,
                "confidence_interval_high": None,
                "at_bound": False,
            },
        ],
        "curve_params": {"hill_slope": 1.2, "top": 100.0, "bottom": 0.0,
                         "num_points": 8, "curve_class": "active",
                         "confidence_interval_low": None,
                         "confidence_interval_high": None,
                         "fit_quality_warnings": None},
        "run_count": 1,
        "selection_rule": None,
        "runs": None,
        "intercept_aggregates": None,
        "disagreement_flag": False,
        "additional_curves": None,
        "aggregate": None,
    }

    raw = {"activity": {parent_key: av}}

    spec = ColumnSpec(key=narrowed_key, header="Mtb::EC50", kind="number", unit="uM")
    assert _cell_value(spec, raw) == 1.23, (
        "Bug #1: _cell_value should have found the EC50 intercept_values entry "
        "via the parent token 'drc:<rd_id>', not the narrowed 'drc:<rd_id>:ec:50.0'"
    )


def test_cell_value_narrowed_drc_qualifier_column():
    """The ::qualifier suffix must also derive from the correct intercept entry."""
    rd_id = "rd-qualifier"
    parent_key = f"drc:{rd_id}"
    av = {
        "value": None,
        "qualifier": "nd",
        "unit": "uM",
        "source": "dose_response",
        "intercept_values": [
            {
                "spec": {"kind": "ic", "level": 50.0, "basis": "response", "label": "IC50"},
                "value": None,
                "confidence_interval_low": None,
                "confidence_interval_high": None,
                "at_bound": False,
            },
        ],
        "curve_params": {"hill_slope": 0.0, "top": 0.0, "bottom": 0.0,
                         "num_points": 6, "curve_class": "inactive",
                         "confidence_interval_low": None,
                         "confidence_interval_high": None,
                         "fit_quality_warnings": None},
        "run_count": 1,
        "selection_rule": None,
        "runs": None,
        "intercept_aggregates": None,
        "disagreement_flag": False,
        "additional_curves": None,
        "aggregate": None,
    }
    raw = {"activity": {parent_key: av}}
    spec = ColumnSpec(key=f"drc:{rd_id}:ic:50.0::qualifier", header="Mtb::IC50::qualifier", kind="qualifier")
    # intercept_values[0].value is None and at_bound is False → ND
    assert _cell_value(spec, raw) == "ND"


# ---------------------------------------------------------------------------
# reportConfig honoring — columns reflect visibleFields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_config_visible_fields_trims_property_columns():
    """When payload carries reportConfig.visibleFields, the column builder must
    drop properties the chemist hid on the grid (e.g. MW off → no MW column)."""
    workspace = uuid.uuid4()
    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    execute = AsyncMock(return_value=_success(page))
    protocols_reader = AsyncMock(return_value=[])

    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={
            "query": {"criteria": []},
            "protocol_columns": [],
            "reportConfig": {
                "imageSize": "medium",
                "visibleFields": {
                    "structure": ["structure", "registration_number"],
                    # MW intentionally OFF
                    "properties": ["logp", "tpsa"],
                    "molecule": ["name"],
                    "collections": False,
                    "protocols": {},
                },
            },
        },
        execute_search=execute,
        protocols_reader=protocols_reader,
        requested_by=uuid.uuid4(),
    )
    await stream.total_count()
    keys = [c.key for c in stream.columns]
    assert "structure" in keys, "structure column must be emitted when visibleFields.structure includes 'structure'"
    assert "registration_number" in keys
    assert "name" in keys
    assert "logp" in keys
    assert "tpsa" in keys
    assert "molecular_weight" not in keys, "MW must be dropped when not in visibleFields.properties"
    # The structure column should be of the new image_structure kind so the
    # XLSX/PDF renderer knows to embed a PNG.
    structure_col = next(c for c in stream.columns if c.key == "structure")
    assert structure_col.kind == "image_structure"


@pytest.mark.asyncio
async def test_report_config_omitted_falls_back_to_legacy_columns():
    """Without reportConfig, the column set matches the pre-fidelity default
    (Reg #, Name, SMILES, InChIKey, Formula, MW, LogP, HBD, HBA, TPSA)."""
    workspace = uuid.uuid4()
    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    execute = AsyncMock(return_value=_success(page))
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={"query": {"criteria": []}, "protocol_columns": []},
        execute_search=execute,
        protocols_reader=AsyncMock(return_value=[]),
        requested_by=uuid.uuid4(),
    )
    await stream.total_count()
    keys = {c.key for c in stream.columns}
    assert keys == {
        "registration_number", "name", "smiles", "inchi_key",
        "molecular_formula", "molecular_weight", "logp", "hbd", "hba", "tpsa",
    }


# ---------------------------------------------------------------------------
# Compact intercept columns — one ::value per intercept, no qualifier/unit
# sub-columns. Plot column carries the protocol-group label.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intercepts_collapse_to_one_column_per_label():
    workspace = uuid.uuid4()
    rd_id = uuid.uuid4()

    ic_ec50 = MagicMock(); ic_ec50.kind.value = "ec"; ic_ec50.level = 50.0; ic_ec50.label = None
    ic_ec90 = MagicMock(); ic_ec90.kind.value = "ec"; ic_ec90.level = 90.0; ic_ec90.label = None
    drc_cfg = MagicMock(); drc_cfg.intercepts = [ic_ec50, ic_ec90]
    rd = MagicMock(); rd.id = rd_id; rd.name = "Resazurin"; rd.unit = "µM"; rd.dose_response_config = drc_cfg
    proto = MagicMock(); proto.id = uuid.uuid4(); proto.name = "Mtb_WCA"; proto.readout_definitions = [rd]

    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={"query": {"criteria": []}, "protocol_columns": [f"drc:{rd_id}"]},
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[proto]),
        requested_by=uuid.uuid4(),
    )
    await stream.total_count()

    plot_cols = [c for c in stream.columns if c.key == f"drc:{rd_id}::plot"]
    assert len(plot_cols) == 1
    assert plot_cols[0].header == "Plot"
    assert plot_cols[0].group == "Mtb_WCA"

    intercept_cols = [
        c for c in stream.columns
        if c.key.startswith(f"drc:{rd_id}:") and c not in plot_cols
    ]
    # Only ::value suffix should be present for the intercepts.
    suffixes = {c.key.rsplit("::", 1)[1] for c in intercept_cols}
    assert suffixes == {"value"}, f"Expected only ::value suffix, got {suffixes}"
    assert {c.header for c in intercept_cols} == {"EC50", "EC90"}
    assert all(c.group == "Mtb_WCA" for c in intercept_cols)
    assert all(c.unit == "µM" for c in intercept_cols)


# ---------------------------------------------------------------------------
# _display_value chemist-mirror — inactive → "ND", at_bound → ">value",
# scalar → number.
# ---------------------------------------------------------------------------

def test_cell_value_inactive_shows_nd_text():
    from cellar.application.export.row_streams.search_results import _display_value
    iv_inactive = {"value": None, "at_bound": False,
                   "spec": {"kind": "ec", "level": 50.0}}
    assert _display_value({}, iv_inactive) == "ND"


def test_cell_value_at_bound_shows_gt_value():
    from cellar.application.export.row_streams.search_results import _display_value
    iv_at_bound = {"value": 100.0, "at_bound": True,
                   "spec": {"kind": "ec", "level": 50.0}}
    assert _display_value({}, iv_at_bound) == ">100.0"


def test_cell_value_active_returns_scalar():
    from cellar.application.export.row_streams.search_results import _display_value
    iv_eq = {"value": 67.4, "at_bound": False,
             "spec": {"kind": "ec", "level": 50.0}}
    assert _display_value({}, iv_eq) == 67.4


def test_cell_value_legacy_inactive_fallback():
    from cellar.application.export.row_streams.search_results import _display_value
    av = {"value": None, "curve_params": {"curve_class": "inactive"}}
    assert _display_value(av, None) == "ND"


# ---------------------------------------------------------------------------
# Format hint forces SMILES on for CSV/SDF even when chemist hid it.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_csv_format_forces_smiles_on():
    workspace = uuid.uuid4()
    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={
            "query": {"criteria": []},
            "protocol_columns": [],
            "reportConfig": {
                "visibleFields": {
                    "structure": ["registration_number"],   # SMILES intentionally hidden
                    "properties": [], "molecule": [],
                    "collections": False, "protocols": {},
                },
            },
        },
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[]),
        requested_by=uuid.uuid4(),
        format="csv",
    )
    await stream.total_count()
    assert "smiles" in {c.key for c in stream.columns}


@pytest.mark.asyncio
async def test_pdf_format_honors_smiles_hidden():
    workspace = uuid.uuid4()
    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={
            "query": {"criteria": []},
            "protocol_columns": [],
            "reportConfig": {
                "visibleFields": {
                    "structure": ["structure", "registration_number"],
                    "properties": [], "molecule": [],
                    "collections": False, "protocols": {},
                },
            },
        },
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[]),
        requested_by=uuid.uuid4(),
        format="pdf",
    )
    await stream.total_count()
    assert "smiles" not in {c.key for c in stream.columns}
