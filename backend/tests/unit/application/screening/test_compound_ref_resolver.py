"""Unit tests for the compound + batch ref resolver."""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.application.screening.compound_ref_resolver import (
    BatchSummary,
    CompoundCandidate,
    resolve_rows,
)
from cellar.application.screening.long_format_normalizer import (
    LongFormatRow,
    WellPosition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    *,
    well: str = "A1",
    batch_ref: str | None = None,
    compound_ref: str | None = None,
    plate: str = "Plate-1",
) -> LongFormatRow:
    return LongFormatRow(
        plate_name=plate,
        well=WellPosition(row=well[0], column=int(well[1:])),
        batch_ref=batch_ref,
        compound_ref=compound_ref,
        concentration=1.0,
        readouts={},
    )


def _summary(idx: int) -> BatchSummary:
    return BatchSummary(
        batch_id=uuid.UUID(int=idx),
        batch_number=f"CV-00001-{idx:03d}",
        salt_form=None,
        purity=99.0,
        created_at=datetime(2026, 1, idx),
    )


def _candidate(
    molecule_id: uuid.UUID, *, batches: tuple[BatchSummary, ...] = ()
) -> CompoundCandidate:
    return CompoundCandidate(
        molecule_id=molecule_id, molecule_name="MOL-A", batches=batches
    )


# ---------------------------------------------------------------------------
# Batch ref only
# ---------------------------------------------------------------------------


class TestBatchRefOnly:
    def test_resolves(self) -> None:
        batch_id = uuid.uuid4()
        molecule_id = uuid.uuid4()
        rows = [_row(batch_ref="CV-00001-001")]
        out = resolve_rows(
            rows,
            batch_index={"CV-00001-001": (batch_id, molecule_id)},
            compound_index={},
        )
        assert out.per_row[0].batch_id == batch_id
        assert out.per_row[0].molecule_id == molecule_id
        assert out.per_row[0].source == "batch_ref"
        assert out.per_row[0].error is None
        assert out.unmatched_batch_refs == frozenset()

    def test_unmatched_records_in_set(self) -> None:
        rows = [_row(batch_ref="MISSING")]
        out = resolve_rows(rows, batch_index={}, compound_index={})
        assert out.per_row[0].batch_id is None
        assert out.per_row[0].error is not None
        assert out.per_row[0].error.kind == "unmatched_batch_ref"
        assert "MISSING" in out.unmatched_batch_refs


# ---------------------------------------------------------------------------
# Compound ref only — auto-pick / ambiguous / unmatched / no batches
# ---------------------------------------------------------------------------


class TestCompoundRefOnly:
    def test_single_batch_auto_picks(self) -> None:
        molecule_id = uuid.uuid4()
        batch = _summary(1)
        rows = [_row(compound_ref="MOL-A")]
        out = resolve_rows(
            rows,
            batch_index={},
            compound_index={"MOL-A": _candidate(molecule_id, batches=(batch,))},
        )
        assert out.per_row[0].batch_id == batch.batch_id
        assert out.per_row[0].molecule_id == molecule_id
        assert out.per_row[0].source == "compound_ref"
        assert out.matched_compound_count == 1

    def test_n_batches_is_ambiguous(self) -> None:
        molecule_id = uuid.uuid4()
        b1, b2 = _summary(1), _summary(2)
        rows = [_row(compound_ref="MOL-A"), _row(well="B2", compound_ref="MOL-A")]
        out = resolve_rows(
            rows,
            batch_index={},
            compound_index={
                "MOL-A": _candidate(molecule_id, batches=(b1, b2)),
            },
        )
        assert all(r.error is not None for r in out.per_row)
        assert all(r.error.kind == "ambiguous_compound" for r in out.per_row)
        # One AmbiguousCompound entry per molecule, not per row.
        assert len(out.ambiguous_compounds) == 1
        amb = out.ambiguous_compounds[0]
        assert amb.affected_row_count == 2
        assert {b.batch_id for b in amb.batch_options} == {b1.batch_id, b2.batch_id}

    def test_override_picks_specific_batch(self) -> None:
        molecule_id = uuid.uuid4()
        b1, b2 = _summary(1), _summary(2)
        rows = [_row(compound_ref="MOL-A")]
        out = resolve_rows(
            rows,
            batch_index={},
            compound_index={
                "MOL-A": _candidate(molecule_id, batches=(b1, b2)),
            },
            overrides={molecule_id: b2.batch_id},
        )
        assert out.per_row[0].batch_id == b2.batch_id
        assert out.per_row[0].source == "override"
        assert len(out.ambiguous_compounds) == 0

    def test_override_with_unknown_batch_id_falls_back_to_ambiguous(self) -> None:
        molecule_id = uuid.uuid4()
        b1, b2 = _summary(1), _summary(2)
        rows = [_row(compound_ref="MOL-A")]
        out = resolve_rows(
            rows,
            batch_index={},
            compound_index={
                "MOL-A": _candidate(molecule_id, batches=(b1, b2)),
            },
            overrides={molecule_id: uuid.UUID(int=99)},
        )
        # Override doesn't match — treat as if user hadn't picked.
        assert out.per_row[0].error is not None
        assert out.per_row[0].error.kind == "ambiguous_compound"

    def test_unmatched_compound_ref(self) -> None:
        rows = [_row(compound_ref="UNKNOWN")]
        out = resolve_rows(rows, batch_index={}, compound_index={})
        assert out.per_row[0].error is not None
        assert out.per_row[0].error.kind == "unmatched_compound_ref"
        assert "UNKNOWN" in out.unmatched_compound_refs

    def test_molecule_with_no_batches_is_unmatched(self) -> None:
        molecule_id = uuid.uuid4()
        rows = [_row(compound_ref="MOL-A")]
        out = resolve_rows(
            rows,
            batch_index={},
            compound_index={"MOL-A": _candidate(molecule_id, batches=())},
        )
        assert out.per_row[0].error is not None
        assert out.per_row[0].error.kind == "unmatched_compound_ref"


# ---------------------------------------------------------------------------
# Both refs set — agree / disagree / batch-wins
# ---------------------------------------------------------------------------


class TestBothRefs:
    def test_both_agree_uses_batch(self) -> None:
        batch_id = uuid.uuid4()
        molecule_id = uuid.uuid4()
        rows = [_row(batch_ref="CV-00001-001", compound_ref="MOL-A")]
        out = resolve_rows(
            rows,
            batch_index={"CV-00001-001": (batch_id, molecule_id)},
            compound_index={
                "MOL-A": _candidate(molecule_id, batches=(_summary(1),)),
            },
        )
        assert out.per_row[0].batch_id == batch_id
        assert out.per_row[0].source == "batch_ref"
        assert out.per_row[0].error is None
        assert len(out.row_conflicts) == 0

    def test_disagree_is_row_conflict(self) -> None:
        batch_id = uuid.uuid4()
        mol_a = uuid.uuid4()
        mol_b = uuid.uuid4()
        rows = [_row(batch_ref="CV-00001-001", compound_ref="MOL-B")]
        out = resolve_rows(
            rows,
            batch_index={"CV-00001-001": (batch_id, mol_a)},
            compound_index={"MOL-B": _candidate(mol_b)},
        )
        assert out.per_row[0].error is not None
        assert out.per_row[0].error.kind == "row_conflict"
        assert len(out.row_conflicts) == 1
        assert out.row_conflicts[0].batch_ref == "CV-00001-001"
        assert out.row_conflicts[0].compound_ref == "MOL-B"

    def test_batch_resolves_compound_misses_uses_batch(self) -> None:
        batch_id = uuid.uuid4()
        molecule_id = uuid.uuid4()
        rows = [_row(batch_ref="CV-00001-001", compound_ref="MISSING")]
        out = resolve_rows(
            rows,
            batch_index={"CV-00001-001": (batch_id, molecule_id)},
            compound_index={},
        )
        assert out.per_row[0].batch_id == batch_id
        assert out.per_row[0].source == "batch_ref"
        # Still surface the compound miss so the chemist sees the bad data.
        assert "MISSING" in out.unmatched_compound_refs


# ---------------------------------------------------------------------------
# Neither ref set
# ---------------------------------------------------------------------------


class TestMissingRefs:
    def test_no_refs_marks_missing(self) -> None:
        rows = [_row()]
        out = resolve_rows(rows, batch_index={}, compound_index={})
        assert out.per_row[0].error is not None
        assert out.per_row[0].error.kind == "missing_refs"
