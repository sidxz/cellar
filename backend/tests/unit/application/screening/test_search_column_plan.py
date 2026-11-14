"""SearchColumnPlanner — which runs feed each search column, and how a split groups them."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from cellar.application.screening.search_column_plan import SearchColumnPlanner
from cellar.domain.screening_assay.activity_types import RunHeader
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
P_A, P_B = uuid.uuid4(), uuid.uuid4()
RD_A, RD_B = uuid.uuid4(), uuid.uuid4()


def _cond(name, data_type="text", unit=None, pick_list_values=None):
    return SimpleNamespace(
        name=name, data_type=data_type, unit=unit, pick_list_values=pick_list_values
    )


class FakeProtocols:
    def __init__(self, conditions=None):
        self._conditions = conditions or {}

    async def find_ids_by_readout_definition_ids(self, ws, rd_ids):
        known = {RD_A: P_A, RD_B: P_B}
        return {rd: known[rd] for rd in rd_ids if rd in known}

    async def find_by_ids(self, ws, ids):
        return [
            SimpleNamespace(id=i, condition_definitions=self._conditions.get(i, [])) for i in ids
        ]


def _header(run_date, *, status="completed", conditions=None, barcodes=(), created=None):
    return RunHeader(
        id=uuid.uuid4(),
        protocol_id=P_A,
        run_date=run_date,
        created_at=created or datetime(2026, 1, 1),
        status=status,
        operator=None,
        notes=None,
        conditions=conditions,
        plate_barcodes=list(barcodes),
    )


class FakeRuns:
    def __init__(self, headers=()):
        self.headers = {h.id: h for h in headers}
        self.measuring_calls: list[tuple] = []

    async def find_headers(self, ws, ids):
        return {i: self.headers[i] for i in ids if i in self.headers}

    async def find_runs_measuring(self, ws, protocol_id, molecule_ids, *, run_scope):
        self.measuring_calls.append((protocol_id, list(molecule_ids), run_scope))
        return list(self.headers.values())


class MatchingIds:
    def __init__(self, ids=None):
        self.ids = ids or [uuid.uuid4()]
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.ids


def _criterion(protocol_id, *, run_scope=None, split=None):
    c = {"type": "activity", "protocol_id": str(protocol_id)}
    if run_scope is not None:
        c["run_scope"] = run_scope
    if split is not None:
        c["split"] = split
    return c


async def _plan(tokens, criteria, *, runs=None, protocols=None, matching=None):
    planner = SearchColumnPlanner(protocols or FakeProtocols(), runs or FakeRuns())
    return await planner.plan(
        WS, tokens, criteria=criteria, matching_ids=matching or MatchingIds()
    )


async def test_each_column_uses_its_own_protocols_run_scope():
    r1 = uuid.uuid4()
    plan = await _plan(
        [f"drc:{RD_A}", f"rd:{P_B}:{RD_B}"],
        [
            _criterion(P_A, run_scope={"mode": "specific", "run_ids": [str(r1)]}),
            _criterion(P_B, run_scope={"mode": "latest"}),
        ],
    )
    by_token = {c.token: c for c in plan.columns}
    assert by_token[f"drc:{RD_A}"].protocol_id == P_A
    assert by_token[f"drc:{RD_A}"].run_scope == RunScope.run_ids([r1])
    assert by_token[f"rd:{P_B}:{RD_B}"].run_scope == RunScope.latest_of_protocol()


async def test_unsplit_column_has_one_implicit_group_keyed_by_its_token():
    plan = await _plan([f"drc:{RD_A}", "any"], [])
    (col,) = plan.columns
    (group,) = col.groups
    assert col.key(group) == f"drc:{RD_A}"
    assert group.run_ids is None
    assert col.run_scope == RunScope.all()
    assert plan.protocol_groups == {}
    assert plan.want_any is True


async def test_legacy_and_normalized_rd_tokens_resolve():
    plan = await _plan([f"rd:{RD_A}", f"rd:{P_B}:{RD_B}:percent_inhibition"], [])
    by_token = {c.token: c for c in plan.columns}
    assert by_token[f"rd:{RD_A}"].protocol_id == P_A
    assert by_token[f"rd:{RD_A}"].kind == "rd"
    assert by_token[f"rd:{P_B}:{RD_B}:percent_inhibition"].normalization == "percent_inhibition"


async def test_split_by_run_orders_oldest_first_and_labels_same_date_runs():
    late = _header(date(2026, 5, 2))
    a = _header(date(2026, 3, 1), barcodes=["PLT-A"], created=datetime(2026, 3, 1, 9))
    b = _header(date(2026, 3, 1), barcodes=["PLT-B"], created=datetime(2026, 3, 1, 10))
    runs = FakeRuns([late, a, b])
    ids = [str(late.id), str(a.id), str(b.id)]
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, run_scope={"mode": "specific", "run_ids": ids}, split={"by": "run"})],
        runs=runs,
    )
    groups = plan.protocol_groups[P_A].groups
    assert [g.key for g in groups] == [f"run:{a.id}", f"run:{b.id}", f"run:{late.id}"]
    assert [g.label for g in groups] == ["2026-03-01 · PLT-A", "2026-03-01 · PLT-B", "2026-05-02"]
    assert all(g.run_count == 1 for g in groups)
    (col,) = plan.columns
    assert col.key(groups[0]) == f"drc:{RD_A}@run:{a.id}"


async def test_split_by_run_keeps_rejected_and_missing_picks_as_flagged_groups():
    bad = _header(date(2026, 2, 1), status="rejected")
    gone = uuid.uuid4()
    plan = await _plan(
        [f"drc:{RD_A}"],
        [
            _criterion(
                P_A,
                run_scope={"mode": "specific", "run_ids": [str(bad.id), str(gone)]},
                split={"by": "run"},
            )
        ],
        runs=FakeRuns([bad]),
    )
    flags = {g.key: g.flags for g in plan.protocol_groups[P_A].groups}
    assert flags == {f"run:{bad.id}": ("rejected",), f"run:{gone}": ("deleted",)}


async def test_split_by_run_requires_hand_picked_runs():
    with pytest.raises(ValidationError, match="pick"):
        await _plan([f"drc:{RD_A}"], [_criterion(P_A, split={"by": "run"})])


ATP = [_cond("ATP Concentration", "numeric", "uM")]


async def test_condition_groups_come_from_runs_measuring_the_matching_compounds():
    runs = FakeRuns([_header(date(2026, 1, 1), conditions={"ATP Concentration": "10 uM"})])
    matching = MatchingIds()
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "ATP Concentration"})],
        runs=runs,
        protocols=FakeProtocols({P_A: ATP}),
        matching=matching,
    )
    assert runs.measuring_calls == [(P_A, matching.ids, RunScope.all())]
    (group,) = plan.protocol_groups[P_A].groups
    assert group.run_ids == frozenset(runs.headers)


async def test_condition_groups_canonicalize_unit_spelling():
    runs = FakeRuns(
        [
            _header(date(2026, 1, 1), conditions={"ATP Concentration": "10 uM"}),
            _header(date(2026, 1, 2), conditions={"ATP Concentration": "10 µM"}),
            _header(date(2026, 1, 3), conditions={"ATP Concentration": "10.0uM"}),
        ]
    )
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "ATP Concentration"})],
        runs=runs,
        protocols=FakeProtocols({P_A: ATP}),
    )
    (group,) = plan.protocol_groups[P_A].groups
    assert (group.label, group.run_count) == ("10 µM", 3)


async def test_condition_groups_order_numerically_with_not_recorded_last():
    runs = FakeRuns(
        [
            _header(date(2026, 1, 1), conditions={"ATP Concentration": "100 uM"}),
            _header(date(2026, 1, 2), conditions={"ATP Concentration": "9 uM"}),
            _header(date(2026, 1, 3), conditions=None),
            _header(date(2026, 1, 4), conditions={"ATP Concentration": " "}),
        ]
    )
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "ATP Concentration"})],
        runs=runs,
        protocols=FakeProtocols({P_A: ATP}),
    )
    groups = plan.protocol_groups[P_A].groups
    assert [(g.label, g.run_count) for g in groups] == [
        ("9 µM", 1),
        ("100 µM", 1),
        ("Not recorded", 2),
    ]
    assert groups[-1].key == "cond:"


async def test_pick_list_conditions_keep_pick_list_order():
    strain = [_cond("Strain", "pick_list", pick_list_values=["H37Rv", "Erdman", "CDC1551"])]
    runs = FakeRuns(
        [
            _header(date(2026, 1, 1), conditions={"Strain": "CDC1551"}),
            _header(date(2026, 1, 2), conditions={"Strain": "H37Rv"}),
        ]
    )
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "Strain"})],
        runs=runs,
        protocols=FakeProtocols({P_A: strain}),
    )
    assert [g.label for g in plan.protocol_groups[P_A].groups] == ["H37Rv", "CDC1551"]


async def test_condition_split_with_no_runs_has_no_groups():
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "ATP Concentration"})],
        runs=FakeRuns([]),
        protocols=FakeProtocols({P_A: ATP}),
    )
    assert plan.protocol_groups[P_A].groups == ()
    assert plan.columns[0].groups == ()


async def test_unknown_condition_is_rejected():
    with pytest.raises(ValidationError, match="Temperature"):
        await _plan(
            [f"drc:{RD_A}"],
            [_criterion(P_A, split={"by": "condition", "condition": "Temperature"})],
            protocols=FakeProtocols({P_A: ATP}),
        )


async def test_condition_split_rejects_the_latest_run_filter():
    with pytest.raises(ValidationError, match="Latest run"):
        await _plan(
            [f"drc:{RD_A}"],
            [
                _criterion(
                    P_A,
                    run_scope={"mode": "latest"},
                    split={"by": "condition", "condition": "ATP Concentration"},
                )
            ],
            protocols=FakeProtocols({P_A: ATP}),
        )


async def test_conflicting_criteria_on_one_protocol_are_rejected():
    with pytest.raises(ValidationError, match="run filter"):
        await _plan(
            [f"drc:{RD_A}"],
            [_criterion(P_A, run_scope={"mode": "latest"}), _criterion(P_A)],
        )


async def test_identical_criteria_on_one_protocol_are_fine():
    criteria = [{"logic": "or", "criteria": [_criterion(P_A), _criterion(P_A)]}]
    plan = await _plan([f"drc:{RD_A}"], criteria)
    assert plan.columns[0].run_scope == RunScope.all()


async def test_matching_ids_are_not_fetched_without_a_condition_split():
    matching = MatchingIds()
    await _plan(
        [f"drc:{RD_A}"], [_criterion(P_A, run_scope={"mode": "latest"})], matching=matching
    )
    assert matching.calls == 0


async def test_plan_from_scopes_uses_the_given_scopes_and_never_splits():
    planner = SearchColumnPlanner(FakeProtocols(), FakeRuns())
    plan = await planner.plan_from_scopes(
        WS, [f"drc:{RD_A}"], {f"drc:{RD_A}": RunScope.latest_of_protocol()}
    )
    (col,) = plan.columns
    assert col.run_scope == RunScope.latest_of_protocol()
    assert plan.protocol_groups == {}


async def test_condition_groups_compare_values_across_units_of_one_family():
    runs = FakeRuns(
        [
            _header(date(2026, 1, 1), conditions={"ATP Concentration": "1 mM"}),
            _header(date(2026, 1, 2), conditions={"ATP Concentration": "10 uM"}),
        ]
    )
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "ATP Concentration"})],
        runs=runs,
        protocols=FakeProtocols({P_A: ATP}),
    )
    assert [g.label for g in plan.protocol_groups[P_A].groups] == ["10 µM", "1 mM"]


async def test_conflicting_criteria_on_a_protocol_without_columns_are_fine():
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_B, run_scope={"mode": "latest"}), _criterion(P_B)],
    )
    assert [c.protocol_id for c in plan.columns] == [P_A]


@pytest.mark.parametrize("value", ["1:100", "2026-05-13", "10-15 min", "Human"])
async def test_condition_values_that_are_not_a_number_and_unit_keep_their_text(value):
    runs = FakeRuns([_header(date(2026, 1, 1), conditions={"Dilution": value})])
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "Dilution"})],
        runs=runs,
        protocols=FakeProtocols({P_A: [_cond("Dilution")]}),
    )
    assert [g.label for g in plan.protocol_groups[P_A].groups] == [value]


async def test_condition_values_keep_full_precision():
    runs = FakeRuns(
        [
            _header(date(2026, 1, 1), conditions={"ATP Concentration": "1234567 nM"}),
            _header(date(2026, 1, 2), conditions={"ATP Concentration": "1234568 nM"}),
        ]
    )
    plan = await _plan(
        [f"drc:{RD_A}"],
        [_criterion(P_A, split={"by": "condition", "condition": "ATP Concentration"})],
        runs=runs,
        protocols=FakeProtocols({P_A: ATP}),
    )
    assert [g.label for g in plan.protocol_groups[P_A].groups] == ["1234567 nM", "1234568 nM"]
