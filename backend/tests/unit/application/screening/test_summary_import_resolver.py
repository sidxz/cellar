"""Unit tests for the summary-import resolver (pure planner).

The planner is DB-free: tests pass in-memory ``compound_index`` / ``batch_index``
dicts and fake readout-def objects. Async builders are covered by a lightweight
in-memory fake-repo test at the bottom.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.application.screening.summary_import_models import SummaryColumnMapping
from cellar.application.screening.summary_import_resolver import (
    build_batch_index,
    build_compound_index,
    plan_summary_rows,
)
from cellar.domain.screening_assay.enums import ReadoutDataType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOL_A = uuid.UUID(int=1)
MOL_B = uuid.UUID(int=2)
BATCH_1 = uuid.UUID(int=11)
RDEF_NUM = uuid.UUID(int=100)
RDEF_TXT = uuid.UUID(int=101)


@dataclass
class _FakeDef:
    name: str
    data_type: ReadoutDataType


_DEFS = {
    RDEF_NUM: _FakeDef(name="IC50", data_type=ReadoutDataType.NUMERIC),
    RDEF_TXT: _FakeDef(name="Notes", data_type=ReadoutDataType.TEXT),
}


def _plan(
    rows,
    *,
    compound_ref_header="Compound",
    batch_ref_header=None,
    readout_columns=None,
    compound_index=None,
    batch_index=None,
    defs_by_id=None,
):
    mapping = SummaryColumnMapping(
        compound_ref=compound_ref_header,
        batch_ref=batch_ref_header,
        readout_columns=readout_columns if readout_columns is not None else {"IC50": RDEF_NUM},
    )
    return plan_summary_rows(
        rows,
        mapping=mapping,
        defs_by_id=defs_by_id if defs_by_id is not None else _DEFS,
        compound_index=compound_index or {},
        batch_index=batch_index or {},
    )


# ---------------------------------------------------------------------------
# 1. compound-only row → molecule_id, batch_id=None
# ---------------------------------------------------------------------------


def test_compound_only_resolves_to_molecule_with_no_batch():
    plan = _plan(
        [{"Compound": "SACC-0501058", "IC50": "12.5"}],
        compound_index={"SACC-0501058": MOL_A},
    )
    assert len(plan.items) == 1
    item = plan.items[0]
    assert item.molecule_id == MOL_A
    assert item.batch_id is None
    assert item.readout_definition_id == RDEF_NUM
    assert item.value_numeric == 12.5
    assert item.value_qualifier == "="
    assert plan.matched_compound_count == 1
    assert not plan.errors


# ---------------------------------------------------------------------------
# 2. unmatched compound ref → unmatched set + no items
# ---------------------------------------------------------------------------


def test_unmatched_compound_ref_produces_no_items():
    plan = _plan(
        [{"Compound": "NOPE-1", "IC50": "5"}],
        compound_index={},
    )
    assert plan.items == []
    assert "NOPE-1" in plan.unmatched_compound_refs
    assert plan.matched_compound_count == 0
    assert any(e["error"].startswith("unmatched compound ref") for e in plan.errors)


# ---------------------------------------------------------------------------
# 3. batch-only row → (batch_id, molecule_id)
# ---------------------------------------------------------------------------


def test_batch_only_resolves_to_batch_and_molecule():
    plan = _plan(
        [{"Batch": "CV-1-001", "IC50": "3.0"}],
        compound_ref_header=None,
        batch_ref_header="Batch",
        batch_index={"CV-1-001": (BATCH_1, MOL_A)},
    )
    assert len(plan.items) == 1
    item = plan.items[0]
    assert item.batch_id == BATCH_1
    assert item.molecule_id == MOL_A


def test_unmatched_batch_only():
    plan = _plan(
        [{"Batch": "GHOST", "IC50": "3.0"}],
        compound_ref_header=None,
        batch_ref_header="Batch",
        batch_index={},
    )
    assert plan.items == []
    assert "GHOST" in plan.unmatched_batch_refs


# ---------------------------------------------------------------------------
# 4. both refs: agree → uses batch; disagree → row_conflict
# ---------------------------------------------------------------------------


def test_both_refs_agree_uses_batch():
    plan = _plan(
        [{"Compound": "SACC-1", "Batch": "CV-1-001", "IC50": "7"}],
        compound_ref_header="Compound",
        batch_ref_header="Batch",
        compound_index={"SACC-1": MOL_A},
        batch_index={"CV-1-001": (BATCH_1, MOL_A)},
    )
    assert len(plan.items) == 1
    item = plan.items[0]
    assert item.batch_id == BATCH_1
    assert item.molecule_id == MOL_A
    assert not plan.row_conflicts


def test_both_refs_disagree_row_conflict():
    plan = _plan(
        [{"Compound": "SACC-B", "Batch": "CV-1-001", "IC50": "7"}],
        compound_ref_header="Compound",
        batch_ref_header="Batch",
        compound_index={"SACC-B": MOL_B},  # resolves to MOL_B
        batch_index={"CV-1-001": (BATCH_1, MOL_A)},  # resolves to MOL_A
    )
    assert plan.items == []
    assert len(plan.row_conflicts) == 1
    conflict = plan.row_conflicts[0]
    assert conflict.batch_ref == "CV-1-001"
    assert conflict.compound_ref == "SACC-B"


def test_both_refs_compound_unmatched_uses_batch():
    plan = _plan(
        [{"Compound": "BADREF", "Batch": "CV-1-001", "IC50": "7"}],
        compound_ref_header="Compound",
        batch_ref_header="Batch",
        compound_index={},
        batch_index={"CV-1-001": (BATCH_1, MOL_A)},
    )
    assert len(plan.items) == 1
    assert plan.items[0].batch_id == BATCH_1
    assert plan.items[0].molecule_id == MOL_A
    assert "BADREF" in plan.unmatched_compound_refs


def test_both_refs_batch_unmatched_is_error():
    plan = _plan(
        [{"Compound": "SACC-1", "Batch": "GHOST", "IC50": "7"}],
        compound_ref_header="Compound",
        batch_ref_header="Batch",
        compound_index={"SACC-1": MOL_A},
        batch_index={},
    )
    assert plan.items == []
    assert "GHOST" in plan.unmatched_batch_refs


# ---------------------------------------------------------------------------
# 5. value routing: numeric, qualifier, text, bad numeric
# ---------------------------------------------------------------------------


def test_value_routing_numeric_qualifier_text_and_bad():
    rows = [
        {"Compound": "A", "IC50": "12.5", "Notes": "potent"},
        {"Compound": "B", "IC50": ">100", "Notes": "weak"},
        {"Compound": "C", "IC50": "not-a-number", "Notes": "x"},
    ]
    plan = _plan(
        rows,
        readout_columns={"IC50": RDEF_NUM, "Notes": RDEF_TXT},
        compound_index={"A": uuid.UUID(int=10), "B": uuid.UUID(int=20), "C": uuid.UUID(int=30)},
    )

    by_mol = {(i.molecule_id, i.readout_definition_id): i for i in plan.items}

    a_num = by_mol[(uuid.UUID(int=10), RDEF_NUM)]
    assert a_num.value_numeric == 12.5
    assert a_num.value_qualifier == "="
    a_txt = by_mol[(uuid.UUID(int=10), RDEF_TXT)]
    assert a_txt.value_text == "potent"
    assert a_txt.value_numeric is None

    b_num = by_mol[(uuid.UUID(int=20), RDEF_NUM)]
    assert b_num.value_numeric == 100.0
    assert b_num.value_qualifier == ">"

    # C's IC50 is bad → error, no IC50 item; Notes still produced.
    assert (uuid.UUID(int=30), RDEF_NUM) not in by_mol
    assert (uuid.UUID(int=30), RDEF_TXT) in by_mol
    assert any("not numeric for IC50" in e["error"] for e in plan.errors)


def test_unknown_readout_def_is_error():
    plan = _plan(
        [{"Compound": "A", "IC50": "5"}],
        readout_columns={"IC50": uuid.UUID(int=999)},  # not in defs
        compound_index={"A": MOL_A},
    )
    assert plan.items == []
    assert any(e["error"] == "unknown readout def" for e in plan.errors)


# ---------------------------------------------------------------------------
# 6. dedup on resolved key — last wins
# ---------------------------------------------------------------------------


def test_dedup_resolved_key_last_wins():
    # Two distinct refs that resolve to the SAME molecule + same def.
    rows = [
        {"Compound": "SYN-OLD", "IC50": "1.0"},
        {"Compound": "SYN-NEW", "IC50": "9.0"},
    ]
    plan = _plan(
        rows,
        compound_index={"SYN-OLD": MOL_A, "SYN-NEW": MOL_A},
    )
    assert len(plan.items) == 1
    assert plan.items[0].value_numeric == 9.0  # last occurrence wins
    assert plan.items[0].source_row == 2


# ---------------------------------------------------------------------------
# 7. neither ref → rows_skipped
# ---------------------------------------------------------------------------


def test_neither_ref_skips_row():
    plan = _plan(
        [{"Compound": "", "IC50": "5"}, {"Compound": "A", "IC50": "5"}],
        compound_index={"A": MOL_A},
    )
    assert plan.rows_skipped == 1
    assert len(plan.items) == 1


def test_whitespace_only_ref_skips_row():
    plan = _plan(
        [{"Compound": "   ", "IC50": "5"}],
        compound_index={"A": MOL_A},
    )
    assert plan.rows_skipped == 1
    assert plan.items == []


# ---------------------------------------------------------------------------
# Async index builders — in-memory fake repos
# ---------------------------------------------------------------------------


@dataclass
class _FakeMol:
    id: uuid.UUID


class _FakeMoleculeRepo:
    def __init__(self, by_ident):
        self._by_ident = by_ident
        self.calls: list[str] = []

    async def find_by_identifier(self, workspace_id, identifier):
        self.calls.append(identifier)
        mid = self._by_ident.get(identifier)
        return _FakeMol(id=mid) if mid else None


@dataclass
class _FakeBatch:
    id: uuid.UUID
    molecule_id: uuid.UUID


class _FakeBatchRepo:
    def __init__(self, by_number):
        self._by_number = by_number
        self.calls: list[str] = []

    async def find_by_batch_number(self, workspace_id, ref):
        self.calls.append(ref)
        hit = self._by_number.get(ref)
        return _FakeBatch(*hit) if hit else None

    async def find_by_external_identifier(self, workspace_id, ref):
        return None


async def test_build_compound_index_dedups_and_omits_unmatched():
    repo = _FakeMoleculeRepo({"SACC-1": MOL_A})
    ws = uuid.uuid4()
    idx = await build_compound_index(["SACC-1", "SACC-1", "MISS", "  ", ""], ws, repo)
    assert idx == {"SACC-1": MOL_A}
    # Distinct refs only fetched once each (SACC-1 once, MISS once).
    assert repo.calls == ["SACC-1", "MISS"]


async def test_build_batch_index_dedups_and_omits_unmatched():
    repo = _FakeBatchRepo({"CV-1-001": (BATCH_1, MOL_A)})
    ws = uuid.uuid4()
    idx = await build_batch_index(["CV-1-001", "CV-1-001", "GHOST"], ws, repo)
    assert idx == {"CV-1-001": (BATCH_1, MOL_A)}
    assert repo.calls == ["CV-1-001", "GHOST"]
