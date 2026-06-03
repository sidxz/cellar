"""Identifier-aware resolution + value planning for summary-results import.

The summary (wide-format) import writes one well-less ``ReadoutData`` row per
``(compound[/batch], readout-definition)`` cell. Historically it resolved
``compound_ref`` only via exact registration-number match, which FAILS for files
keyed by custom identifiers (e.g. ``SACC-0501058``, stored as a molecule
*identifier*, not the ``CC-…`` reg number). The PLATE import path already
resolves identifier-aware, via ``molecule_repo.find_by_identifier`` +
``resolve_batch_ref``.

This module mirrors that plate path's split:

  - **Async index builders** (``build_compound_index`` / ``build_batch_index``)
    do the repository calls, deduplicating distinct refs, exactly like
    ``import_run_file_mapper._build_compound_index`` / ``_build_batch_lookup``.
  - **A pure planner** (``plan_summary_rows``) takes the pre-built indexes and
    is fully deterministic — no DB. It mirrors
    ``compound_ref_resolver._resolve_one`` precedence, ADAPTED to molecule-level
    summary storage (NO batch auto-pick / ambiguous machinery: summary stores at
    the molecule level, so a resolved compound never needs a batch).

Per-row precedence (planner):

  1. Both refs set → resolve each. Batch authoritative: if batch resolves, use
     its ``(batch_id, molecule_id)``. If compound also resolves and DISAGREES on
     molecule → ``row_conflict``. If compound unmatched but batch matched → use
     batch. If batch unmatched → ``unmatched_batch_ref`` for the row.
  2. Only compound ref → resolve via ``compound_index`` → ``molecule_id``,
     ``batch_id=None``. Miss → ``unmatched_compound_ref``.
  3. Only batch ref → resolve via ``batch_index`` → ``(batch_id, molecule_id)``.
     Miss → ``unmatched_batch_ref``.
  4. Neither ref → row skipped (counted in ``rows_skipped``; not an error).

Value routing is kept BYTE-FOR-BYTE identical to ``import_summary_file`` (same
``_NUMERIC_RE``, same qualifier-symbol mapping, same TEXT routing) so T15 can
delete the duplicated logic there and call this planner with no behaviour change.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from cellar.application.screening.summary_import_models import SummaryColumnMapping
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.enums import ReadoutDataType

# Optional qualifier symbol + a signed int/float/scientific number. Kept
# identical to import_summary_file._NUMERIC_RE.
_NUMERIC_RE = re.compile(r"^\s*(<=|>=|<|>|=)?\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*$")


# ---------------------------------------------------------------------------
# Protocols (structural typing for the planner's def lookup)
# ---------------------------------------------------------------------------


class _ReadoutDefLike(Protocol):
    """Minimal shape the planner needs from a ReadoutDefinition."""

    name: str
    data_type: ReadoutDataType


# ---------------------------------------------------------------------------
# Async index builders (repo-calling — mirror plate path)
# ---------------------------------------------------------------------------


async def build_compound_index(
    refs: Iterable[str],
    workspace_id: uuid.UUID,
    molecule_repo: MoleculeRepository,
) -> dict[str, uuid.UUID]:
    """Resolve every distinct non-empty ``compound_ref`` → ``molecule.id``.

    One ``find_by_identifier`` per distinct ref (distinct refs are cached so a
    repeated ref never refetches). Identifier-aware: matches name, synonym,
    external id, OR registration number. Refs that resolve to no molecule are
    omitted; the planner surfaces them as ``unmatched_compound_refs``.

    Mirrors ``import_run_file_mapper._build_compound_index`` (minus the per-
    molecule batch fan-out, which summary-level storage does not need).
    """
    out: dict[str, uuid.UUID] = {}
    seen: set[str] = set()
    for raw in refs:
        ref = (raw or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        molecule = await molecule_repo.find_by_identifier(workspace_id, ref)
        if molecule is not None:
            out[ref] = molecule.id
    return out


async def build_batch_index(
    refs: Iterable[str],
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
) -> dict[str, tuple[uuid.UUID, uuid.UUID]]:
    """Resolve every distinct non-empty ``batch_ref`` → ``(batch.id, molecule_id)``.

    One ``resolve_batch_ref`` per distinct ref (canonical batch_number then
    external alias). Unmatched refs are omitted; the planner surfaces them as
    ``unmatched_batch_refs``.

    Mirrors ``import_run_file_mapper._build_batch_lookup``.
    """
    from cellar.application.inventory.resolve_batch_ref import resolve_batch_ref

    out: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}
    seen: set[str] = set()
    for raw in refs:
        ref = (raw or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        batch = await resolve_batch_ref(batch_repo, workspace_id, ref)
        if batch is not None:
            out[ref] = (batch.id, batch.molecule_id)
    return out


# ---------------------------------------------------------------------------
# Planner outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryPlanItem:
    """One resolved ``(compound[/batch], readout-def)`` value ready to upsert.

    ``batch_id`` is None for molecule-only (compound_ref) rows. ``source_row``
    is the 1-based file row this value came from (for error reporting).
    """

    molecule_id: uuid.UUID
    batch_id: uuid.UUID | None
    readout_definition_id: uuid.UUID
    value_numeric: float | None
    value_qualifier: str | None
    value_text: str | None
    source_row: int


@dataclass(frozen=True)
class SummaryRowConflict:
    """Both refs set but they point to different molecules — hard error."""

    source_row: int
    batch_ref: str
    compound_ref: str
    reason: str


@dataclass(frozen=True)
class SummaryPlan:
    """Output of ``plan_summary_rows`` — deterministic, DB-free.

    ``items`` is deduped on the RESOLVED key ``(molecule_id, batch_id,
    readout_definition_id)`` with last-occurrence-wins.
    """

    items: list[SummaryPlanItem] = field(default_factory=list)
    unmatched_compound_refs: frozenset[str] = frozenset()
    unmatched_batch_refs: frozenset[str] = frozenset()
    row_conflicts: list[SummaryRowConflict] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    rows_skipped: int = 0
    matched_compound_count: int = 0


# ---------------------------------------------------------------------------
# Pure planner
# ---------------------------------------------------------------------------


def plan_summary_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    mapping: SummaryColumnMapping,
    defs_by_id: Mapping[uuid.UUID, _ReadoutDefLike],
    compound_index: Mapping[str, uuid.UUID],
    batch_index: Mapping[str, tuple[uuid.UUID, uuid.UUID]],
) -> SummaryPlan:
    """Plan summary-import value writes from parsed rows + pre-built indexes.

    Pure + deterministic (no DB). For each row resolves the compound/batch ref
    to ``(molecule_id, batch_id)`` (precedence mirrors
    ``compound_ref_resolver._resolve_one``, adapted to molecule-level storage),
    then routes each readout cell value by ``data_type`` and dedups on the
    resolved key with last-occurrence-wins.
    """
    # Deduped on the RESOLVED key; insertion order is first-seen but the value
    # is the LAST item so a later row overrides an earlier one.
    _ResolvedKey = tuple[uuid.UUID, uuid.UUID | None, uuid.UUID]
    deduped: dict[_ResolvedKey, SummaryPlanItem] = {}
    errors: list[dict[str, str]] = []
    row_conflicts: list[SummaryRowConflict] = []
    unmatched_compounds: set[str] = set()
    unmatched_batches: set[str] = set()
    matched_compounds: set[uuid.UUID] = set()
    rows_skipped = 0

    for ridx, row in enumerate(rows):
        source_row = ridx + 1
        compound_ref = ""
        if mapping.compound_ref:
            compound_ref = (row.get(mapping.compound_ref) or "").strip()
        batch_ref = ""
        if mapping.batch_ref:
            batch_ref = (row.get(mapping.batch_ref) or "").strip()

        # --- Neither ref → skip (not an error) -----------------------------
        if not compound_ref and not batch_ref:
            rows_skipped += 1
            continue

        resolved = _resolve_row(
            compound_ref=compound_ref,
            batch_ref=batch_ref,
            compound_index=compound_index,
            batch_index=batch_index,
            source_row=source_row,
        )
        if resolved.error is not None:
            errors.append(resolved.error)
        if resolved.conflict is not None:
            row_conflicts.append(resolved.conflict)
        if resolved.unmatched_compound_ref:
            unmatched_compounds.add(resolved.unmatched_compound_ref)
        if resolved.unmatched_batch_ref:
            unmatched_batches.add(resolved.unmatched_batch_ref)
        if resolved.molecule_id is None:
            continue

        molecule_id = resolved.molecule_id
        batch_id = resolved.batch_id
        matched_compounds.add(molecule_id)

        for header, rdef_id in mapping.readout_columns.items():
            raw = (row.get(header) or "").strip()
            if not raw:
                continue

            d = defs_by_id.get(rdef_id)
            if d is None:
                errors.append({"row": str(source_row), "error": "unknown readout def"})
                continue

            value_numeric: float | None = None
            value_qualifier: str | None = None
            value_text: str | None = None

            if d.data_type == ReadoutDataType.TEXT:
                value_text = raw
            else:
                m = _NUMERIC_RE.match(raw)
                if m is None:
                    errors.append(
                        {"row": str(source_row), "error": f"'{raw}' not numeric for {d.name}"}
                    )
                    continue
                value_qualifier = m.group(1) or "="
                value_numeric = float(m.group(2))

            key: _ResolvedKey = (molecule_id, batch_id, rdef_id)
            deduped[key] = SummaryPlanItem(
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rdef_id,
                value_numeric=value_numeric,
                value_qualifier=value_qualifier,
                value_text=value_text,
                source_row=source_row,
            )

    return SummaryPlan(
        items=list(deduped.values()),
        unmatched_compound_refs=frozenset(unmatched_compounds),
        unmatched_batch_refs=frozenset(unmatched_batches),
        row_conflicts=row_conflicts,
        errors=errors,
        rows_skipped=rows_skipped,
        matched_compound_count=len(matched_compounds),
    )


# ---------------------------------------------------------------------------
# Per-row decision (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RowOutcome:
    molecule_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    error: dict[str, str] | None = None
    conflict: SummaryRowConflict | None = None
    unmatched_compound_ref: str = ""
    unmatched_batch_ref: str = ""


def _resolve_row(
    *,
    compound_ref: str,
    batch_ref: str,
    compound_index: Mapping[str, uuid.UUID],
    batch_index: Mapping[str, tuple[uuid.UUID, uuid.UUID]],
    source_row: int,
) -> _RowOutcome:
    """Resolve one row's refs to ``(molecule_id, batch_id)``.

    Mirrors ``compound_ref_resolver._resolve_one`` precedence, adapted to
    molecule-level summary storage (compound-only rows resolve to a molecule
    with ``batch_id=None`` — no auto-pick / ambiguous machinery).
    """
    batch_hit = batch_index.get(batch_ref) if batch_ref else None
    compound_hit = compound_index.get(compound_ref) if compound_ref else None

    # --- Both refs set -----------------------------------------------------
    if batch_ref and compound_ref:
        if batch_hit is None:
            # Batch is the authoritative reference; if it can't resolve the
            # row is unmatched even if the compound ref alone would have.
            return _RowOutcome(
                molecule_id=None,
                batch_id=None,
                error={"row": str(source_row), "error": f"unmatched batch ref {batch_ref!r}"},
                unmatched_batch_ref=batch_ref,
            )
        if compound_hit is None:
            # Batch resolves; compound ref doesn't. Batch's molecule is
            # authoritative — the compound ref is just bad data, not a conflict.
            return _RowOutcome(
                molecule_id=batch_hit[1],
                batch_id=batch_hit[0],
                unmatched_compound_ref=compound_ref,
            )
        if batch_hit[1] != compound_hit:
            return _RowOutcome(
                molecule_id=None,
                batch_id=None,
                conflict=SummaryRowConflict(
                    source_row=source_row,
                    batch_ref=batch_ref,
                    compound_ref=compound_ref,
                    reason=(
                        f"Batch Ref {batch_ref!r} → molecule {batch_hit[1]}; "
                        f"Compound Ref {compound_ref!r} → molecule {compound_hit}"
                    ),
                ),
            )
        # Both agree → batch wins as the more specific reference.
        return _RowOutcome(molecule_id=batch_hit[1], batch_id=batch_hit[0])

    # --- Only batch ref ----------------------------------------------------
    if batch_ref:
        if batch_hit is None:
            return _RowOutcome(
                molecule_id=None,
                batch_id=None,
                error={"row": str(source_row), "error": f"unmatched batch ref {batch_ref!r}"},
                unmatched_batch_ref=batch_ref,
            )
        return _RowOutcome(molecule_id=batch_hit[1], batch_id=batch_hit[0])

    # --- Only compound ref -------------------------------------------------
    # (compound_ref must be set here — neither-ref is handled by the caller.)
    if compound_hit is None:
        return _RowOutcome(
            molecule_id=None,
            batch_id=None,
            error={"row": str(source_row), "error": f"unmatched compound ref {compound_ref!r}"},
            unmatched_compound_ref=compound_ref,
        )
    return _RowOutcome(molecule_id=compound_hit, batch_id=None)
