"""Compound + batch reference resolution for run-file import.

The run-import wizard exposes two compound-identification roles:

  - **Batch Ref** — a specific batch (lot). Direct ``batch_number`` lookup.
  - **Compound Ref** — a molecule identifier (name / synonym / external id /
    registration number). Resolves to a molecule, then derives the batch
    via inventory lookup.

This module is the **pure** decision layer. Async repository calls happen
in ``import_run_file._build_compound_index``; the resolver itself takes
pre-loaded indexes and is fully deterministic.

Per-row precedence (matches design spec):

  1. ``batch_ref`` set → look up in ``batch_index``. Hit = use it.
     Miss = unmatched.
  2. ``compound_ref`` set → look up molecule. If override exists, use it.
     Else if exactly 1 batch → auto-pick. Else N>1 → ambiguous.
     Else 0 → unmatched.
  3. Both set → resolve each independently. If they agree on molecule,
     use the batch; if they disagree, row conflict.
  4. Neither set → resolution is empty (caller decides whether to drop
     the row based on well type — sample rows drop, control rows keep).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from cellar.application.screening.long_format_normalizer import (
    LongFormatRow,
)

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchSummary:
    """Lightweight batch shape used by the picker UI and the resolver.

    Carries enough to let a chemist pick a lot ("most recent / 90% pure /
    HCl salt form") without fetching the full Batch aggregate.
    """

    batch_id: uuid.UUID
    batch_number: str
    salt_form: str | None
    purity: float | None
    created_at: datetime


@dataclass(frozen=True)
class CompoundCandidate:
    """A molecule that an input ``compound_ref`` resolved to, with its
    full inventory of batches in the same workspace."""

    molecule_id: uuid.UUID
    molecule_name: str
    batches: tuple[BatchSummary, ...]


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

ResolveErrorKind = Literal[
    "unmatched_batch_ref",
    "unmatched_compound_ref",
    "ambiguous_compound",
    "row_conflict",
    "missing_refs",
]


@dataclass(frozen=True)
class ResolveError:
    kind: ResolveErrorKind
    detail: str = ""


@dataclass(frozen=True)
class RowResolution:
    """Per-row outcome after applying both refs + overrides.

    ``batch_id`` and ``molecule_id`` are set when the row resolved to a
    concrete batch. ``error`` is set when the row could not be resolved;
    callers (the conflict scanner) decide whether to drop the row based
    on the row's well-type classification.
    """

    batch_id: uuid.UUID | None
    molecule_id: uuid.UUID | None
    source: Literal["batch_ref", "compound_ref", "override"] | None
    error: ResolveError | None


@dataclass(frozen=True)
class AmbiguousCompound:
    """One ambiguous molecule, NOT one per row.

    The wizard renders one picker per ``AmbiguousCompound``; the chemist's
    choice applies to all ``affected_row_count`` rows for that compound.
    """

    compound_ref: str  # the input string the user typed (preserved for display)
    molecule_id: uuid.UUID
    molecule_name: str
    batch_options: tuple[BatchSummary, ...]
    affected_row_count: int


@dataclass(frozen=True)
class RowConflict:
    """Both refs set but they point to different molecules.

    Hard error, parity with pick-list violations: the import refuses to
    commit until the file is fixed.
    """

    plate_name: str
    well_label: str
    batch_ref: str
    compound_ref: str
    reason: str


@dataclass(frozen=True)
class Resolutions:
    """Output of ``resolve_rows``.

    ``per_row`` is parallel to the input ``rows`` (same length, same order).
    """

    per_row: tuple[RowResolution, ...]
    unmatched_batch_refs: frozenset[str]
    unmatched_compound_refs: frozenset[str]
    ambiguous_compounds: tuple[AmbiguousCompound, ...]
    row_conflicts: tuple[RowConflict, ...]
    matched_compound_count: int


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def resolve_rows(
    rows: Sequence[LongFormatRow],
    *,
    batch_index: Mapping[str, tuple[uuid.UUID, uuid.UUID]],
    compound_index: Mapping[str, CompoundCandidate],
    overrides: Mapping[uuid.UUID, uuid.UUID] | None = None,
) -> Resolutions:
    """Decide a per-row resolution for every row.

    Args:
        rows: Normalized rows from the run file.
        batch_index: ``batch_ref`` (raw string) → ``(batch_id, molecule_id)``.
            Pre-built by the importer via ``_build_batch_lookup``.
        compound_index: ``compound_ref`` (raw string) → ``CompoundCandidate``.
            Pre-built via ``_build_compound_index``.
        overrides: ``molecule_id`` → ``batch_id``. The chemist's
            disambiguation picks from a previous preview pass. None on
            first pass.
    """
    overrides = overrides or {}
    per_row: list[RowResolution] = []
    unmatched_batches: set[str] = set()
    unmatched_compounds: set[str] = set()
    ambiguous_by_molecule: dict[uuid.UUID, _AmbiguousAccumulator] = {}
    row_conflicts: list[RowConflict] = []
    matched_compounds: set[uuid.UUID] = set()

    for row in rows:
        resolution = _resolve_one(
            row,
            batch_index=batch_index,
            compound_index=compound_index,
            overrides=overrides,
        )
        per_row.append(resolution)

        # Aggregate side effects.
        err = resolution.error
        if err is None:
            if (
                resolution.source in ("compound_ref", "override")
                and resolution.molecule_id is not None
            ):
                matched_compounds.add(resolution.molecule_id)
            continue

        if err.kind == "unmatched_batch_ref" and row.batch_ref:
            unmatched_batches.add(row.batch_ref)
        elif err.kind == "unmatched_compound_ref" and row.compound_ref:
            unmatched_compounds.add(row.compound_ref)
        elif err.kind == "ambiguous_compound" and row.compound_ref:
            cand = compound_index.get(row.compound_ref)
            if cand is not None:
                acc = ambiguous_by_molecule.setdefault(
                    cand.molecule_id,
                    _AmbiguousAccumulator(
                        compound_ref=row.compound_ref,
                        candidate=cand,
                        affected=0,
                    ),
                )
                acc.affected += 1
        elif err.kind == "row_conflict":
            row_conflicts.append(
                RowConflict(
                    plate_name=row.plate_name,
                    well_label=row.well.label,
                    batch_ref=row.batch_ref or "",
                    compound_ref=row.compound_ref or "",
                    reason=err.detail,
                )
            )

    ambiguous = tuple(
        AmbiguousCompound(
            compound_ref=acc.compound_ref,
            molecule_id=acc.candidate.molecule_id,
            molecule_name=acc.candidate.molecule_name,
            batch_options=acc.candidate.batches,
            affected_row_count=acc.affected,
        )
        for acc in ambiguous_by_molecule.values()
    )

    return Resolutions(
        per_row=tuple(per_row),
        unmatched_batch_refs=frozenset(unmatched_batches),
        unmatched_compound_refs=frozenset(unmatched_compounds),
        ambiguous_compounds=ambiguous,
        row_conflicts=tuple(row_conflicts),
        matched_compound_count=len(matched_compounds),
    )


# ---------------------------------------------------------------------------
# Per-row decision
# ---------------------------------------------------------------------------


@dataclass
class _AmbiguousAccumulator:
    compound_ref: str
    candidate: CompoundCandidate
    affected: int


def _resolve_one(
    row: LongFormatRow,
    *,
    batch_index: Mapping[str, tuple[uuid.UUID, uuid.UUID]],
    compound_index: Mapping[str, CompoundCandidate],
    overrides: Mapping[uuid.UUID, uuid.UUID],
) -> RowResolution:
    batch_ref = row.batch_ref
    compound_ref = row.compound_ref

    # Pre-resolve each ref independently. Batch ref is binary
    # (resolves or doesn't); compound ref has three outcomes
    # (resolves to single batch, resolves but ambiguous, doesn't resolve).
    batch_hit: tuple[uuid.UUID, uuid.UUID] | None = None
    if batch_ref:
        batch_hit = batch_index.get(batch_ref)

    compound_candidate: CompoundCandidate | None = None
    if compound_ref:
        compound_candidate = compound_index.get(compound_ref)

    # --- Both refs set -----------------------------------------------------
    if batch_ref and compound_ref:
        if batch_hit is None:
            return RowResolution(
                batch_id=None,
                molecule_id=None,
                source=None,
                error=ResolveError(kind="unmatched_batch_ref"),
            )
        if compound_candidate is None:
            # Batch ref resolves; compound ref doesn't. The batch's
            # molecule is authoritative — the compound ref is just bad
            # data, not a conflict. Report compound miss but use batch.
            return RowResolution(
                batch_id=batch_hit[0],
                molecule_id=batch_hit[1],
                source="batch_ref",
                error=ResolveError(kind="unmatched_compound_ref"),
            )
        if batch_hit[1] != compound_candidate.molecule_id:
            return RowResolution(
                batch_id=None,
                molecule_id=None,
                source=None,
                error=ResolveError(
                    kind="row_conflict",
                    detail=(
                        f"Batch Ref {batch_ref!r} → molecule {batch_hit[1]}; "
                        f"Compound Ref {compound_ref!r} → "
                        f"molecule {compound_candidate.molecule_id} "
                        f"({compound_candidate.molecule_name})"
                    ),
                ),
            )
        # Both agree → batch ref wins as the more specific reference.
        return RowResolution(
            batch_id=batch_hit[0],
            molecule_id=batch_hit[1],
            source="batch_ref",
            error=None,
        )

    # --- Only batch ref ----------------------------------------------------
    if batch_ref:
        if batch_hit is None:
            return RowResolution(
                batch_id=None,
                molecule_id=None,
                source=None,
                error=ResolveError(kind="unmatched_batch_ref"),
            )
        return RowResolution(
            batch_id=batch_hit[0],
            molecule_id=batch_hit[1],
            source="batch_ref",
            error=None,
        )

    # --- Only compound ref -------------------------------------------------
    if compound_ref:
        if compound_candidate is None:
            return RowResolution(
                batch_id=None,
                molecule_id=None,
                source=None,
                error=ResolveError(kind="unmatched_compound_ref"),
            )
        override_batch_id = overrides.get(compound_candidate.molecule_id)
        if override_batch_id is not None and any(
            b.batch_id == override_batch_id for b in compound_candidate.batches
        ):
            return RowResolution(
                batch_id=override_batch_id,
                molecule_id=compound_candidate.molecule_id,
                source="override",
                error=None,
            )
        if len(compound_candidate.batches) == 1:
            return RowResolution(
                batch_id=compound_candidate.batches[0].batch_id,
                molecule_id=compound_candidate.molecule_id,
                source="compound_ref",
                error=None,
            )
        if len(compound_candidate.batches) == 0:
            # Molecule exists but has no batches — same surface as no
            # match (chemist needs to register a batch first).
            return RowResolution(
                batch_id=None,
                molecule_id=None,
                source=None,
                error=ResolveError(
                    kind="unmatched_compound_ref",
                    detail=f"molecule {compound_candidate.molecule_name!r} has no batches",
                ),
            )
        # N > 1 batches and no override → ambiguous.
        return RowResolution(
            batch_id=None,
            molecule_id=None,
            source=None,
            error=ResolveError(kind="ambiguous_compound"),
        )

    # --- Neither ref set ---------------------------------------------------
    return RowResolution(
        batch_id=None,
        molecule_id=None,
        source=None,
        error=ResolveError(kind="missing_refs"),
    )
