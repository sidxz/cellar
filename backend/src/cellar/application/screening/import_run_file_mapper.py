"""Row → resolution helpers for the run-file importer.

Extracted from ``import_run_file.py``. These helpers translate the
chemist-confirmed (or auto-guessed) ``ColumnMapping`` and the
``NormalizedTable`` rows into the lookup indexes the resolver consumes,
and shape resolver outputs into DTOs for the wire format.

Specifically:

- ``_build_guess_mapping`` — preview-time best-guess ``ColumnMapping``
  built from the inferred header roles. Readout columns get throwaway
  UUIDs because preview cannot bind to real readout-definition ids.
- ``_build_batch_lookup`` — strict batch-number resolution.
- ``_build_compound_index`` — compound-ref → ``CompoundCandidate``
  lookup, threading molecule batches in via ``BatchSummary``.
- ``_summarize_plates`` — per-plate well/sample/blank counts for the
  preview panel.
- ``_to_ambiguous_dto`` — resolver internal → wire DTO shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from cellar.application.screening.compound_ref_resolver import (
    AmbiguousCompound,
    BatchSummary,
    CompoundCandidate,
)
from cellar.application.screening.long_format_normalizer import (
    ColumnMapping,
    LongFormatRow,
    ReadoutColumn,
    SuggestedMapping,
)
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.enums import PlateFormat


def _build_guess_mapping(suggested: SuggestedMapping) -> ColumnMapping | None:
    """Build a best-guess ColumnMapping from a SuggestedMapping.

    Used by the preview phase only — readout columns get throwaway UUIDs
    because preview cannot bind to real readout-definition ids.
    """
    well_header = suggested.first("well")
    if well_header is None:
        return None

    readouts = suggested.by_role("readout")
    return ColumnMapping(
        well=well_header,
        plate_name=suggested.first("plate_name"),
        concentration=suggested.first("concentration"),
        batch_ref=suggested.first("batch_ref"),
        compound_ref=suggested.first("compound_ref"),
        readout_columns=tuple(
            ReadoutColumn(header=s.header, readout_definition_id=uuid.uuid4()) for s in readouts
        ),
    )


async def _build_batch_lookup(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    batch_repo: BatchRepository,
) -> dict[str, tuple[uuid.UUID, uuid.UUID]]:
    """Resolve every distinct ``batch_ref`` to ``(batch_id, molecule_id)``.

    Lookup order per ref:
      1. canonical batch_number (find_by_batch_number)
      2. external alias (find_by_external_identifier)
      3. unmatched (omitted from dict)
    """
    from cellar.application.inventory.resolve_batch_ref import resolve_batch_ref

    out: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}
    seen: set[str] = set()
    for r in rows:
        if not r.batch_ref or r.batch_ref in seen:
            continue
        seen.add(r.batch_ref)
        batch = await resolve_batch_ref(batch_repo, workspace_id, r.batch_ref)
        if batch is not None:
            out[r.batch_ref] = (batch.id, batch.molecule_id)
    return out


async def _build_compound_index(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    molecule_repo: MoleculeRepository,
    batch_repo: BatchRepository,
) -> dict[str, CompoundCandidate]:
    """Resolve every distinct ``compound_ref`` to a ``CompoundCandidate``.

    One ``find_by_identifier`` per distinct compound_ref + one
    ``find_by_molecule`` per distinct molecule_id (so re-listed compounds
    don't re-fetch). Identifiers that resolve to no molecule are simply
    omitted; the resolver then surfaces them as ``unmatched_compound_refs``.
    """
    out: dict[str, CompoundCandidate] = {}
    seen_refs: set[str] = set()
    batches_by_molecule: dict[uuid.UUID, tuple[BatchSummary, ...]] = {}
    for r in rows:
        if not r.compound_ref or r.compound_ref in seen_refs:
            continue
        seen_refs.add(r.compound_ref)
        molecule = await molecule_repo.find_by_identifier(workspace_id, r.compound_ref)
        if molecule is None:
            continue
        cached = batches_by_molecule.get(molecule.id)
        if cached is None:
            batches = await batch_repo.find_by_molecule(workspace_id, molecule.id)
            cached = tuple(
                BatchSummary(
                    batch_id=b.id,
                    batch_number=b.batch_number.value,
                    salt_form=b.salt_name,
                    purity=b.purity,
                    created_at=b.created_at,
                )
                for b in batches
            )
            batches_by_molecule[molecule.id] = cached
        out[r.compound_ref] = CompoundCandidate(
            molecule_id=molecule.id,
            molecule_name=molecule.name,
            batches=cached,
        )
    return out


def _to_ambiguous_dto(amb: AmbiguousCompound):
    """Resolver internal → wire DTO shape.

    Imported lazily to keep the DTO module the single source of truth
    for the wire types — see ``import_run_file_dtos.AmbiguousCompoundDTO``
    and ``BatchOption``.
    """
    from cellar.application.screening.import_run_file_dtos import (
        AmbiguousCompoundDTO,
        BatchOption,
    )

    return AmbiguousCompoundDTO(
        compound_ref=amb.compound_ref,
        molecule_id=amb.molecule_id,
        molecule_name=amb.molecule_name,
        batch_options=tuple(
            BatchOption(
                batch_id=b.batch_id,
                batch_number=b.batch_number,
                salt_form=b.salt_form,
                purity=b.purity,
                created_at=b.created_at,
            )
            for b in amb.batch_options
        ),
        affected_row_count=amb.affected_row_count,
    )


def _summarize_plates(
    rows: Iterable[LongFormatRow],
    plate_formats: dict[str, PlateFormat],
):
    """Per-plate well/sample/blank counts for the preview panel.

    Returns a tuple of ``PlatePreview`` — imported lazily to keep DTO
    definitions in one place.
    """
    from cellar.application.screening.import_run_file_dtos import PlatePreview

    by_plate: dict[str, list[LongFormatRow]] = {}
    for r in rows:
        by_plate.setdefault(r.plate_name, []).append(r)

    out: list[PlatePreview] = []
    for plate, plate_rows in sorted(by_plate.items()):
        out.append(
            PlatePreview(
                plate_name=plate,
                plate_format=plate_formats.get(plate, PlateFormat.F96).value,
                well_count=len(plate_rows),
                sample_count=sum(1 for r in plate_rows if r.batch_ref),
                blank_count=sum(1 for r in plate_rows if not r.batch_ref),
            )
        )
    return tuple(out)
