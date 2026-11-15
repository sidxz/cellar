from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.export.row_streams.base import ColumnSpec
from cellar.application.export.row_streams.search_results import (
    SearchResultsRowStream,
    _activity_parent_token,
    _cell_value,
    _expand_protocol_column,
)


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
    proto.code = None
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

    return Success(
        EnrichedPageResult(
            items=page.items,
            next_cursor=page.next_cursor,
            total_count=page.total_count,
            activity_data=None,
            similarity_scores=None,
            # Only a page built with explicit groups carries them (MagicMock would
            # invent an attribute).
            column_groups=page.column_groups if isinstance(page.column_groups, dict) else None,
        )
    )


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
        "curve_params": {
            "hill_slope": 1.2,
            "top": 100.0,
            "bottom": 0.0,
            "num_points": 8,
            "curve_class": "active",
            "confidence_interval_low": None,
            "confidence_interval_high": None,
            "fit_quality_warnings": None,
        },
        "run_count": 1,
        "selection_rule": None,
        "runs": None,
        "intercept_aggregates": [
            {
                "spec": {"kind": "ec", "level": 50.0},
                "selected_value": 1.23,
                "selected_qualifier": "=",
            },
            {
                "spec": {"kind": "ec", "level": 90.0},
                "selected_value": 4.56,
                "selected_qualifier": "=",
            },
        ],
        "disagreement_flag": False,
        "additional_curves": None,
        "aggregate": None,
    }

    raw = {"activity": {parent_key: av}}

    spec = ColumnSpec(key=narrowed_key, header="Mtb::EC50", kind="number", unit="uM")
    assert _cell_value(spec, raw) == 1.23, (
        "Bug #1: _cell_value should have found the EC50 intercept aggregate "
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
        "curve_params": {
            "hill_slope": 0.0,
            "top": 0.0,
            "bottom": 0.0,
            "num_points": 6,
            "curve_class": "inactive",
            "confidence_interval_low": None,
            "confidence_interval_high": None,
            "fit_quality_warnings": None,
        },
        "run_count": 1,
        "selection_rule": None,
        "runs": None,
        "intercept_aggregates": [
            {
                "spec": {"kind": "ic", "level": 50.0},
                "selected_value": None,
                "selected_qualifier": "nd",
            }
        ],
        "disagreement_flag": False,
        "additional_curves": None,
        "aggregate": None,
    }
    raw = {"activity": {parent_key: av}}
    spec = ColumnSpec(
        key=f"drc:{rd_id}:ic:50.0::qualifier", header="Mtb::IC50::qualifier", kind="qualifier"
    )
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
    assert "structure" in keys, (
        "structure column must be emitted when visibleFields.structure includes 'structure'"
    )
    assert "registration_number" in keys
    assert "name" in keys
    assert "logp" in keys
    assert "tpsa" in keys
    assert "molecular_weight" not in keys, (
        "MW must be dropped when not in visibleFields.properties"
    )
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
        "registration_number",
        "name",
        "smiles",
        "inchi_key",
        "molecular_formula",
        "molecular_weight",
        "logp",
        "hbd",
        "hba",
        "tpsa",
    }


# ---------------------------------------------------------------------------
# Compact intercept columns — one ::value per intercept, no qualifier/unit
# sub-columns. Plot column carries the protocol-group label.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intercepts_collapse_to_one_column_per_label():
    workspace = uuid.uuid4()
    rd_id = uuid.uuid4()

    ic_ec50 = MagicMock()
    ic_ec50.kind.value = "ec"
    ic_ec50.level = 50.0
    ic_ec50.label = None
    ic_ec90 = MagicMock()
    ic_ec90.kind.value = "ec"
    ic_ec90.level = 90.0
    ic_ec90.label = None
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
    proto.code = None
    proto.dose_unit = "uM"  # potencies are labelled with the protocol dose unit

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
        c for c in stream.columns if c.key.startswith(f"drc:{rd_id}:") and c not in plot_cols
    ]
    # Only ::value suffix should be present for the intercepts.
    suffixes = {c.key.rsplit("::", 1)[1] for c in intercept_cols}
    assert suffixes == {"value"}, f"Expected only ::value suffix, got {suffixes}"
    assert {c.header for c in intercept_cols} == {"EC50", "EC90"}
    assert all(c.group == "Mtb_WCA" for c in intercept_cols)
    assert all(c.unit == "uM" for c in intercept_cols)


# ---------------------------------------------------------------------------
# _display chemist-mirror — inactive → "ND", at_bound → ">value",
# scalar → number.
# ---------------------------------------------------------------------------


def test_display_shows_nd_bounds_and_numbers():
    from cellar.application.export.row_streams.search_results import _display

    assert _display(None, "nd") == "ND"
    assert _display(100.0, ">") == ">100.0"
    assert _display(0.1, "<") == "<0.1"
    assert _display(67.4, "=") == 67.4
    assert _display(67.4, None) == 67.4
    assert _display(None, None) is None


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
                    "structure": ["registration_number"],  # SMILES intentionally hidden
                    "properties": [],
                    "molecule": [],
                    "collections": False,
                    "protocols": {},
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
                    "properties": [],
                    "molecule": [],
                    "collections": False,
                    "protocols": {},
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


def test_any_token_expands_to_one_text_column():
    cols = _expand_protocol_column("any", {})
    assert [(c.key, c.header, c.kind) for c in cols] == [("any::text", "Active in", "text")]


def test_cell_value_any_joins_entries():
    spec = ColumnSpec(key="any::text", header="Active in", kind="text")
    raw = {
        "activity": {
            "any": {
                "entries": [
                    {
                        "protocol_name": "Beta",
                        "label": "IC50",
                        "value": 5.0,
                        "unit": "nM",
                        "qualifier": None,
                    },
                    {
                        "protocol_name": "Alpha",
                        "label": "IC50",
                        "value": 5.0,
                        "unit": "uM",
                        "qualifier": ">",
                    },
                    {
                        "protocol_name": "Gamma",
                        "label": "% Inhibition",
                        "value": None,
                        "unit": "%",
                        "qualifier": None,
                    },
                ]
            }
        }
    }
    assert _cell_value(spec, raw) == "Beta: IC50 5 nM; Alpha: IC50 >5 uM; Gamma: % Inhibition —"


@pytest.mark.asyncio
async def test_every_customizer_field_reaches_the_export_row():
    """Each option the Customize Report panel offers must produce a filled
    column — Stage and the extra descriptors used to export blank."""
    mol = _mol("CV-2")
    mol.lifecycle_stage = "lead"
    mol.descriptors.ro5_violations = 1
    mol.descriptors.heavy_atom_count = 3
    page = MagicMock(items=[mol], next_cursor=None, total_count=1)
    stream = SearchResultsRowStream(
        workspace_id=uuid.uuid4(),
        payload={
            "query": {"criteria": []},
            "protocol_columns": [],
            "reportConfig": {
                "imageSize": "small",
                "visibleFields": {
                    "structure": ["registration_number"],
                    "properties": ["ro5_violations", "heavy_atom_count"],
                    "molecule": ["lifecycle_stage"],
                },
            },
        },
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[]),
        requested_by=uuid.uuid4(),
    )
    rows = [row async for batch in stream.iter_batches(10) for row in batch]
    assert rows[0].cells["lifecycle_stage"] == "lead"
    assert rows[0].cells["ro5_violations"] == 1
    assert rows[0].cells["heavy_atom_count"] == 3


async def test_protocol_column_group_carries_the_code():
    workspace = uuid.uuid4()
    rd_id = uuid.uuid4()
    ic50 = MagicMock()
    ic50.kind.value = "ic"
    ic50.level = 50.0
    ic50.label = None
    drc_cfg = MagicMock()
    drc_cfg.intercepts = [ic50]
    rd = MagicMock()
    rd.id = rd_id
    rd.name = "Signal"
    rd.unit = "µM"
    rd.dose_response_config = drc_cfg
    proto = MagicMock()
    proto.id = uuid.uuid4()
    proto.name = "PptT inhibition [FP]"
    proto.code = "PRT-00042"
    proto.readout_definitions = [rd]
    proto.dose_unit = "uM"

    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1)
    stream = SearchResultsRowStream(
        workspace_id=workspace,
        payload={"query": {"criteria": []}, "protocol_columns": [f"drc:{rd_id}"]},
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[proto]),
        requested_by=uuid.uuid4(),
    )
    await stream.total_count()

    value_col = next(c for c in stream.columns if c.key.endswith("::value"))
    assert value_col.group == "PRT-00042 PptT inhibition [FP]"
    assert value_col.flat_header == "IC50 (uM) [PRT-00042]"


@pytest.mark.asyncio
async def test_split_protocol_exports_one_column_set_per_group():
    rd_id, proto_id = uuid.uuid4(), uuid.uuid4()
    rd = MagicMock(id=rd_id, unit="µM", dose_response_config=None)
    rd.name = "MIC"
    proto = MagicMock(id=proto_id, code=None, readout_definitions=[rd])
    proto.name = "Mtb WCA"
    token = f"rd:{proto_id}:{rd_id}"
    groups = {
        str(proto_id): {
            "split": {"by": "condition", "condition": "ATP"},
            "groups": [
                {
                    "key": "cond:10 µM",
                    "label": "10 µM",
                    "run_ids": [],
                    "run_count": 1,
                    "flags": [],
                },
                {"key": "cond:1 mM", "label": "1 mM", "run_ids": [], "run_count": 1, "flags": []},
            ],
        }
    }
    page = MagicMock(items=[_mol("CV-1")], next_cursor=None, total_count=1, column_groups=groups)
    stream = SearchResultsRowStream(
        workspace_id=uuid.uuid4(),
        payload={
            "query": {"criteria": []},
            "protocol_columns": [token],
            "sort_by": token,
            "sort_dir": "desc",
        },
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[proto]),
        requested_by=uuid.uuid4(),
    )
    await stream.total_count()

    split = [c for c in stream.columns if c.key.startswith(token)]
    assert [(c.key, c.group, c.subgroup) for c in split] == [
        (f"{token}@cond:10 µM::value", "Mtb WCA · by ATP", "10 µM"),
        (f"{token}@cond:1 mM::value", "Mtb WCA · by ATP", "1 mM"),
    ]
    # One group row (Excel) names both; a flat header (CSV) tells them apart.
    assert split[0].group_label == "Mtb WCA · by ATP · 10 µM"
    assert [c.flat_header for c in split] == ["MIC (µM) [10 µM]", "MIC (µM) [1 mM]"]
    raw = {"activity": {f"{token}@cond:1 mM": {"value": 4.0, "qualifier": None, "unit": "µM"}}}
    assert _cell_value(split[1], raw) == 4.0
    assert _cell_value(split[0], raw) is None
    cmd = stream.execute_search.await_args.args[0]
    assert (cmd.sort_by, cmd.sort_dir) == (token, "desc")


def test_single_point_cell_exports_its_qualifier_and_nd():
    spec = ColumnSpec(key="rd:p:rd::value", header="MIC", kind="number")
    assert (
        _cell_value(spec, {"activity": {"rd:p:rd": {"value": 50.0, "qualifier": ">"}}}) == ">50.0"
    )
    assert _cell_value(spec, {"activity": {"rd:p:rd": {"value": None, "qualifier": "nd"}}}) == "ND"
    assert _cell_value(spec, {"activity": {"rd:p:rd": {"value": 12.5, "qualifier": None}}}) == 12.5


def test_intercept_cell_exports_the_value_the_grid_shows():
    spec = ColumnSpec(key="drc:rd:ic:50.0::value", header="IC50", kind="number")
    av = {
        "value": 30.0,
        "qualifier": None,
        # The representative curve's own intercept…
        "intercept_values": [{"spec": {"kind": "ic", "level": 50.0}, "value": 5.0}],
        # …is not what a mean cell shows: the selected aggregate is.
        "intercept_aggregates": [
            {
                "spec": {"kind": "ic", "level": 50.0},
                "selected_value": 30.0,
                "selected_qualifier": "=",
            }
        ],
    }
    assert _cell_value(spec, {"activity": {"drc:rd": av}}) == 30.0
    gt = {
        **av,
        "intercept_aggregates": [
            {
                "spec": {"kind": "ic", "level": 50.0},
                "selected_value": 100.0,
                "selected_qualifier": ">",
            }
        ],
    }
    assert _cell_value(spec, {"activity": {"drc:rd": gt}}) == ">100.0"


# ---------------------------------------------------------------------------
# The grid's display settings: Compact hides plots, Overlay puts a split
# protocol's curves on one plot after its groups, properties in grid order.
# ---------------------------------------------------------------------------


def _dr_protocol(n_readouts: int = 1):
    proto_id = uuid.uuid4()
    readouts = []
    for i in range(n_readouts):
        ic50 = MagicMock()
        ic50.kind.value = "ic"
        ic50.level = 50.0
        ic50.label = None
        rd = MagicMock(id=uuid.uuid4(), unit="µM")
        rd.name = f"Signal {i + 1}"
        rd.dose_response_config = MagicMock(intercepts=[ic50])
        readouts.append(rd)
    proto = MagicMock(id=proto_id, code="PRT-1", readout_definitions=readouts, dose_unit="µM")
    proto.name = "InhA"
    return proto


def _split(proto, n_groups: int) -> dict:
    labels = ["10 µM", "1 mM", *[f"{i} mM" for i in range(2, n_groups)]][:n_groups]
    return {
        str(proto.id): {
            "split": {"by": "condition", "condition": "ATP"},
            "groups": [
                {
                    "key": f"cond:{label}",
                    "label": label,
                    "run_ids": [],
                    "run_count": 1,
                    "flags": [],
                }
                for label in labels
            ],
        }
    }


async def _columns(proto, tokens, report_config, column_groups=None):
    page = MagicMock(
        items=[_mol("CV-1")], next_cursor=None, total_count=1, column_groups=column_groups
    )
    stream = SearchResultsRowStream(
        workspace_id=uuid.uuid4(),
        payload={
            "query": {"criteria": []},
            "protocol_columns": tokens,
            "reportConfig": {
                "visibleFields": {"structure": [], "properties": []},
                **report_config,
            },
        },
        execute_search=AsyncMock(return_value=_success(page)),
        protocols_reader=AsyncMock(return_value=[proto]),
        requested_by=uuid.uuid4(),
        format="pdf",
    )
    await stream.total_count()
    return stream.columns


async def test_overlay_draws_every_group_on_one_plot_after_the_groups():
    proto = _dr_protocol()
    rd = proto.readout_definitions[0].id
    cols = await _columns(
        proto,
        [f"drc:{rd}"],
        {"displayPreset": "detailed", "plotLayout": "overlay"},
        _split(proto, 2),
    )
    assert [(c.key, c.kind) for c in cols] == [
        (f"drc:{rd}:ic:50.0@cond:10 µM::value", "number"),
        (f"drc:{rd}:ic:50.0@cond:1 mM::value", "number"),
        (f"drc:{rd}::overlay", "image_curve"),
    ]
    # Each group's header carries its curve's colour, as in the grid.
    assert [c.group_color for c in cols[:2]] == ["#3b6fb6", "#18974c"]
    plot = cols[2]
    assert plot.header == "Plot"
    assert (plot.group, plot.subgroup) == ("PRT-1 InhA · by ATP", None)
    assert [c.subgroup for c in cols[:2]] == ["10 µM", "1 mM"]
    assert plot.overlay_of == (f"drc:{rd}@cond:10 µM", f"drc:{rd}@cond:1 mM")


async def test_overlay_names_the_readout_when_a_protocol_has_several():
    proto = _dr_protocol(2)
    tokens = [f"drc:{rd.id}" for rd in proto.readout_definitions]
    cols = await _columns(proto, tokens, {"plotLayout": "overlay"}, _split(proto, 2))
    assert [c.header for c in cols if c.overlay_of] == ["Plot · Signal 1", "Plot · Signal 2"]


async def test_compact_drops_every_plot():
    proto = _dr_protocol()
    rd = proto.readout_definitions[0].id
    for groups in (None, _split(proto, 2)):
        cols = await _columns(
            proto, [f"drc:{rd}"], {"displayPreset": "compact", "plotLayout": "overlay"}, groups
        )
        assert [c.kind for c in cols] == ["number"] * (1 if groups is None else 2)


async def test_overlay_stays_side_by_side_past_eight_groups_or_without_a_split():
    proto = _dr_protocol()
    rd = proto.readout_definitions[0].id
    nine = await _columns(proto, [f"drc:{rd}"], {"plotLayout": "overlay"}, _split(proto, 9))
    assert sum(c.kind == "image_curve" for c in nine) == 9
    assert not any(c.overlay_of or c.group_color for c in nine)

    flat = await _columns(proto, [f"drc:{rd}"], {"plotLayout": "overlay"})
    assert [(c.key, c.kind) for c in flat] == [
        (f"drc:{rd}:ic:50.0::value", "number"),
        (f"drc:{rd}::plot", "image_curve"),
    ]


async def test_split_protocol_lists_its_columns_group_by_group_like_the_grid():
    proto = _dr_protocol(2)
    a, b = (rd.id for rd in proto.readout_definitions)
    cols = await _columns(
        proto, [f"drc:{a}", f"drc:{b}"], {"displayPreset": "compact"}, _split(proto, 2)
    )
    assert [c.key for c in cols] == [
        f"drc:{a}:ic:50.0@cond:10 µM::value",
        f"drc:{b}:ic:50.0@cond:10 µM::value",
        f"drc:{a}:ic:50.0@cond:1 mM::value",
        f"drc:{b}:ic:50.0@cond:1 mM::value",
    ]


async def test_properties_follow_the_grid_order_headers_and_digits():
    stream = SearchResultsRowStream(
        workspace_id=uuid.uuid4(),
        payload={
            "query": {"criteria": []},
            "reportConfig": {
                "visibleFields": {
                    "structure": [],
                    "properties": [
                        "molecular_weight",
                        "logp",
                        "hbd",
                        "hba",
                        "tpsa",
                        "aromatic_rings",
                    ],
                }
            },
        },
        execute_search=AsyncMock(
            return_value=_success(MagicMock(items=[], next_cursor=None, total_count=0))
        ),
        protocols_reader=AsyncMock(return_value=[]),
        requested_by=uuid.uuid4(),
    )
    await stream.total_count()
    assert [(c.header, c.digits) for c in stream.columns] == [
        ("MW", 1),
        ("LogP", 2),
        ("TPSA", 1),
        ("HBD", None),
        ("HBA", None),
        ("Aromatic Rings", None),
    ]


async def test_activity_values_carry_the_grids_four_significant_figures():
    proto = _dr_protocol()
    rd = proto.readout_definitions[0].id
    cols = await _columns(proto, [f"drc:{rd}"], {})
    assert cols[0].precision == 4
