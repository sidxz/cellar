"""join_protocol_datasets: Compounds datasets of several protocols on the first one's rows."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    DRAggRow,
    NumericReadoutRow,
)
from cellar.application.visualization.aggregated_dataset import build_aggregated_dataset
from cellar.application.visualization.cross_protocol import delta_qualifier, join_protocol_datasets
from cellar.application.visualization.dataset import DatasetProtocol
from cellar.application.visualization.dataset_reader import CompoundInfo, ReadoutDefInfo, RunInfo

M1, M2, M3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
MOLECULES = {
    m: CompoundInfo(f"CEL-00000{i}", "CCO", 300.0, 1.0, 20.0, 1, 2, 3, 1)
    for i, m in enumerate((M1, M2, M3), start=1)
}


def _protocol(name: str) -> tuple[DatasetProtocol, ReadoutDefInfo, ReadoutDefInfo]:
    """A protocol with a dose-response "IC50" (µM) and a numeric "Potency" (µM)."""
    pid = uuid.uuid4()
    ic50 = ReadoutDefInfo(
        id=uuid.uuid4(),
        protocol_id=pid,
        name="IC50",
        data_type="dose_response",
        unit=None,
        display_order=0,
        dose_unit="uM",
        curve_type="ic50",
    )
    potency = ReadoutDefInfo(
        id=uuid.uuid4(),
        protocol_id=pid,
        name="Potency",
        data_type="numeric",
        unit="µM",
        display_order=1,
    )
    return DatasetProtocol(id=pid, name=name), ic50, potency


A, A_IC50, A_POT = _protocol("A")
B, B_IC50, B_POT = _protocol("B")


def _part(proto, defs, *, dr=(), numeric=()):
    run = RunInfo(
        id=uuid.uuid4(),
        protocol_id=proto.id,
        run_date=date(2026, 11, 12),
        operator_id=uuid.uuid4(),
        status="approved",
        conditions=None,
        created_at=datetime(2026, 11, 12, tzinfo=UTC),
    )
    ds = build_aggregated_dataset(
        "compounds",
        [run],
        list(defs),
        ActivityAggregates(numeric_rows=list(numeric), dr_agg_rows=list(dr)),
        [],
        MOLECULES,
        {},
    )
    return proto, ds


def _ic50(rd: ReadoutDefInfo, mol: uuid.UUID, um: float | None, **kw) -> DRAggRow:
    return DRAggRow(
        molecule_id=mol,
        readout_definition_id=rd.id,
        best=um,
        geo_mean=um,
        n_tested=1,
        n_used=1 if um is not None else 0,
        **kw,
    )


def _potency(rd: ReadoutDefInfo, mol: uuid.UUID, **kw) -> NumericReadoutRow:
    base = dict(
        molecule_id=mol,
        readout_name="Potency",
        best=None,
        mean=None,
        n=0,
        sd=None,
        low=None,
        layer=None,
        readout_definition_id=rd.id,
    )
    base.update(kw)
    return NumericReadoutRow(**base)


def _p(rd: ReadoutDefInfo) -> str:
    return f"dr:{rd.id}:p"


def _sel(a: ReadoutDefInfo, b: ReadoutDefInfo) -> str:
    return f"sel:{_p(a)}|{_p(b)}"


def _col(ds, key):
    return next(c for c in ds.columns if c.key == key)


def _approx(values):
    return [None if v is None else pytest.approx(v) for v in values]


# A {m1 pIC50 7.0, m2 pIC50 6.0}; B {m1 pIC50 5.0, m3 pIC50 6.5}
PART_A = _part(A, [A_IC50], dr=[_ic50(A_IC50, M1, 0.1), _ic50(A_IC50, M2, 1.0)])
PART_B = _part(B, [B_IC50], dr=[_ic50(B_IC50, M1, 10.0), _ic50(B_IC50, M3, 10**-0.5)])


def test_rows_come_from_the_first_protocol_and_the_second_is_mapped_by_compound():
    ds = join_protocol_datasets([PART_A, PART_B])

    assert ds.row_ids == [str(M1), str(M2)]  # m3 is only in B
    assert ds.values["compound"] == ["CEL-000001", "CEL-000002"]
    assert ds.values[f"tested:{B.id}"] == ["Tested", "Not tested"]
    assert ds.values[_p(B_IC50)] == _approx([5.0, None])
    assert ds.values[_sel(A_IC50, B_IC50)] == _approx([2.0, None])
    assert ds.protocols == [A, B]
    assert ds.level == "compounds"


def test_tested_column_names_the_protocol_it_tells_about():
    ds = join_protocol_datasets([PART_A, PART_B])

    tested = _col(ds, f"tested:{B.id}")
    assert (tested.label, tested.kind, tested.group) == ("Tested in B", "category", "B")
    assert tested.provenance.protocol_id == B.id


def test_same_readout_name_in_two_protocols_gets_distinct_prefixed_labels():
    ds = join_protocol_datasets([PART_A, PART_B])

    a, b = _col(ds, _p(A_IC50)), _col(ds, _p(B_IC50))
    assert a.label.startswith("A · ") and b.label.startswith("B · ")
    assert a.label != b.label
    assert (a.group, b.group) == ("A", "B")
    assert (a.provenance.protocol_id, b.provenance.protocol_id) == (A.id, B.id)
    # keys never change, and every protocol-owned column follows its protocol
    a_alone = PART_A[1]
    assert {c.key for c in a_alone.columns} <= {c.key for c in ds.columns}
    for key in (f"dr:{A_IC50.id}", f"dr:{A_IC50.id}:n_tested"):
        assert _col(ds, key).label == f"A · {_col(a_alone, key).label}"
    assert _col(ds, "compound").label == "Compound"  # identity stays unprefixed


def test_selectivity_column_names_both_p_columns():
    ds = join_protocol_datasets([PART_A, PART_B])

    sel = _col(ds, _sel(A_IC50, B_IC50))
    a, b = _col(ds, _p(A_IC50)), _col(ds, _p(B_IC50))
    assert sel.label == f"Δ ({a.label}) − ({b.label})"  # noqa: RUF001
    assert (sel.kind, sel.unit, sel.group) == ("number", "log units", "Selectivity")
    assert sel.provenance.aggregation == "selectivity" and sel.provenance.stat is None


def test_only_p_values_are_paired_never_their_siblings_or_raw_values():
    ds = join_protocol_datasets([PART_A, PART_B])

    assert [k for k in ds.values if k.startswith("sel:")] == [_sel(A_IC50, B_IC50)]


def test_a_second_protocol_sharing_no_compounds_marks_every_row_not_tested():
    b_only_m3 = _part(B, [B_IC50], dr=[_ic50(B_IC50, M3, 1.0)])

    ds = join_protocol_datasets([PART_A, b_only_m3])

    assert len(ds.row_ids) == len(PART_A[1].row_ids)
    assert ds.values[f"tested:{B.id}"] == ["Not tested", "Not tested"]
    assert ds.values[_sel(A_IC50, B_IC50)] == [None, None]
    assert ds.values[_p(B_IC50)] == [None, None]


def test_tested_without_a_value_is_not_the_same_as_not_tested():
    inactive_m1 = _part(B, [B_IC50], dr=[_ic50(B_IC50, M1, None, n_inactive=1)])

    ds = join_protocol_datasets([PART_A, inactive_m1])

    assert ds.values[f"tested:{B.id}"] == ["Tested", "Not tested"]
    assert ds.values[_sel(A_IC50, B_IC50)] == [None, None]


def test_a_censored_p_value_gives_a_bounded_selectivity():
    # A: m1 IC50 > 10 µM → pIC50 < 5; B: m1 pIC50 4.0
    a = _part(A, [A_IC50], dr=[_ic50(A_IC50, M1, None, n_censored=1, censored_bound=10.0)])
    b = _part(B, [B_IC50], dr=[_ic50(B_IC50, M1, 100.0)])

    ds = join_protocol_datasets([a, b])

    key = _sel(A_IC50, B_IC50)
    assert ds.values[key] == _approx([1.0])
    assert ds.values[f"{key}:q"] == ["<"]
    q = _col(ds, f"{key}:q")
    assert (q.kind, q.group, q.provenance.stat) == ("category", "Selectivity", "qualifier")


def test_an_inclusive_bound_gives_an_inclusive_selectivity():
    # A: m1 Potency >= 10 µM → pPotency <= 5 (inclusive); B: m1 pPotency 4.0
    a = _part(
        A, [A_POT], numeric=[_potency(A_POT, M1, gt_count=1, gt_bound=10.0, gt_inclusive=True)]
    )
    b = _part(B, [B_POT], numeric=[_potency(B_POT, M1, n=1, mean=100.0, best=100.0, low=100.0)])

    ds = join_protocol_datasets([a, b])

    key = f"sel:rd:{A_POT.id}:raw:p|rd:{B_POT.id}:raw:p"
    assert ds.values[key] == _approx([1.0])
    assert ds.values[f"{key}:q"] == ["<="]


def test_a_censored_value_in_the_added_protocol_bounds_the_other_way():
    # A: m1 pIC50 7.0; B: m1 IC50 > 10 µM → pIC50 < 5, so A - B > 2
    b = _part(B, [B_IC50], dr=[_ic50(B_IC50, M1, None, n_censored=1, censored_bound=10.0)])

    ds = join_protocol_datasets([PART_A, b])

    key = _sel(A_IC50, B_IC50)
    assert ds.values[key] == _approx([2.0, None])
    assert ds.values[f"{key}:q"] == [">", None]


def test_censored_in_opposite_directions_gives_no_selectivity():
    # A pIC50 < 5, B pIC50 < 5 (both IC50 > 10 µM): a - b can be anything
    censored = dict(n_censored=1, censored_bound=10.0)
    a = _part(A, [A_IC50], dr=[_ic50(A_IC50, M1, None, **censored)])
    b = _part(B, [B_IC50], dr=[_ic50(B_IC50, M1, None, **censored)])

    ds = join_protocol_datasets([a, b])

    key = _sel(A_IC50, B_IC50)
    assert ds.values[key] == [None]
    assert f"{key}:q" not in ds.values


def test_uncensored_pairs_have_no_qualifier_column():
    ds = join_protocol_datasets([PART_A, PART_B])

    assert f"{_sel(A_IC50, B_IC50)}:q" not in ds.values


@pytest.mark.parametrize(
    ("qa", "qb", "expected"),
    [
        (None, None, (True, None)),
        (None, "<", (True, ">")),
        (">", None, (True, ">")),
        ("<", None, (True, "<")),
        (None, ">", (True, "<")),
        (">", ">", (False, None)),
        ("<", "<", (False, None)),
        (">", "<", (True, ">")),
        ("<", ">", (True, "<")),
        (">=", None, (True, ">=")),
        (None, "<=", (True, ">=")),
        ("<=", ">=", (True, "<=")),
        (">=", "<", (True, ">")),
        ("<", ">=", (True, "<")),
        (">=", ">", (False, None)),
    ],
)
def test_delta_qualifier(qa, qb, expected):
    assert delta_qualifier(qa, qb) == expected


def test_one_protocol_is_unchanged_but_names_its_protocol():
    ds = join_protocol_datasets([PART_A])

    alone = PART_A[1]
    assert ds.protocols == [A]
    assert (ds.columns, ds.values, ds.row_ids, ds.revision) == (
        alone.columns,
        alone.values,
        alone.row_ids,
        alone.revision,
    )


def test_revision_follows_every_part():
    joined = join_protocol_datasets([PART_A, PART_B]).revision
    other_b = _part(B, [B_IC50], dr=[_ic50(B_IC50, M2, 1.0)])

    assert joined == join_protocol_datasets([PART_A, PART_B]).revision
    assert joined != PART_A[1].revision
    assert joined != join_protocol_datasets([PART_A, other_b]).revision


def test_every_column_has_its_values_and_every_value_list_is_row_length():
    ds = join_protocol_datasets([PART_A, PART_B])

    keys = [c.key for c in ds.columns]
    assert len(keys) == len(set(keys)) and set(keys) == set(ds.values)
    assert all(len(v) == len(ds.row_ids) for v in ds.values.values())
