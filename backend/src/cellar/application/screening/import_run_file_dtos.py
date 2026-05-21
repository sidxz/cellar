"""Command / query / result DTOs for the run-file importer.

Extracted from ``import_run_file.py`` so the use case file stays focused
on orchestration. The wire-format types live here:

- Queries / commands: ``PreviewRunFileQuery``, ``RepreviewRunFileQuery``,
  ``ImportRunFileCommand``.
- Result shapes: ``PreviewRunFileResult``, ``ImportRunFileResult``.
- Preview-panel children: ``PlatePreview``, ``BatchOption``,
  ``AmbiguousCompoundDTO``.

The use case file re-exports these names at the original module path so
existing callers / tests keep working.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cellar.application.screening.import_plan import ReadoutConflict, WellConflict
from cellar.application.screening.long_format_normalizer import (
    ColumnMapping,
    HeaderSuggestion,
)
from cellar.application.shared.command import Command


@dataclass(frozen=True, kw_only=True)
class PreviewRunFileQuery(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    file_content: bytes
    filename: str = ""
    content_type: str = ""
    # When True and EnsureBatchExists is wired, the preview phase will
    # auto-create placeholder batches for unmatched refs whose compound
    # resolves to a known molecule. No-op when False (default).
    auto_create_unmatched_batches: bool = False


@dataclass(frozen=True)
class PlatePreview:
    plate_name: str
    plate_format: str
    well_count: int
    sample_count: int
    blank_count: int


@dataclass(frozen=True)
class BatchOption:
    """One option offered to the chemist when disambiguating a compound."""

    batch_id: uuid.UUID
    batch_number: str
    salt_form: str | None
    purity: float | None
    created_at: datetime


@dataclass(frozen=True)
class AmbiguousCompoundDTO:
    """One molecule that needs the chemist to pick a batch.

    The picker UI renders one row per ``AmbiguousCompoundDTO``; the
    chemist's choice flows back as ``compound_batch_overrides`` on the
    import command.
    """

    compound_ref: str
    molecule_id: uuid.UUID
    molecule_name: str
    batch_options: tuple[BatchOption, ...]
    affected_row_count: int


@dataclass(frozen=True)
class PreviewRunFileResult:
    preview_id: uuid.UUID
    headers: tuple[str, ...]
    suggestions: tuple[HeaderSuggestion, ...]
    sample_rows: tuple[dict[str, str], ...]
    plates: tuple[PlatePreview, ...]
    matched_batches: int
    unmatched_batches: tuple[str, ...]
    total_rows: int
    expires_in_seconds: int
    validation_errors: tuple[str, ...] = ()
    will_create_plates: int = 0
    will_create_wells: int = 0
    will_create_readouts: int = 0
    will_skip_wells: tuple[WellConflict, ...] = ()
    will_skip_readouts: tuple[ReadoutConflict, ...] = ()
    matched_compounds: int = 0
    unmatched_compound_refs: tuple[str, ...] = ()
    ambiguous_compounds: tuple[AmbiguousCompoundDTO, ...] = ()
    row_conflicts: tuple[str, ...] = ()
    # Number of placeholder batches auto-created during this preview pass.
    # Always 0 when auto_create_unmatched_batches=False on the query.
    auto_created_batches: int = 0


@dataclass(frozen=True, kw_only=True)
class RepreviewRunFileQuery(Command):
    """Re-run resolution against a cached preview using a refined mapping.

    Fired when the chemist edits the column-role assignments in the
    wizard's mapping step (e.g. switches a column from Batch Ref to
    Compound Ref) and the preview panel needs to reflect the new
    resolution outcome before they commit the import.
    """

    workspace_id: uuid.UUID
    run_id: uuid.UUID
    preview_id: uuid.UUID
    mapping: ColumnMapping


@dataclass(frozen=True, kw_only=True)
class ImportRunFileCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    preview_id: uuid.UUID
    mapping: ColumnMapping
    # User's per-molecule batch picks from the disambiguation panel.
    # ``molecule_id → batch_id``. Empty when no disambiguation was needed.
    compound_batch_overrides: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    # When True and EnsureBatchExists is wired, the import phase will
    # auto-create placeholder batches for unmatched refs whose compound
    # resolves to a known molecule. No-op when False (default).
    auto_create_unmatched_batches: bool = False


@dataclass
class ImportRunFileResult:
    rows_total: int = 0
    plates_created: int = 0
    wells_created: int = 0
    readouts_created: int = 0
    unmatched_batches: list[str] = field(default_factory=list)
    unmatched_compound_refs: list[str] = field(default_factory=list)
    controls_from_template: int = 0
    controls_unclassified: int = 0
    skipped_rows: int = 0
    conflicts_well_metadata: list[WellConflict] = field(default_factory=list)
    conflicts_readout: list[ReadoutConflict] = field(default_factory=list)
    attachment_id: uuid.UUID | None = None
    # Non-fatal warnings. ``compute_warning`` covers normalization /
    # aggregation failures (e.g. missing controls). ``attachment_warning``
    # covers attachment persistence failures — the import itself still
    # succeeded.
    compute_warning: str | None = None
    attachment_warning: str | None = None
    # Per-compound dose-response fit warnings surfaced from the calc engine.
    fit_warnings: list[str] = field(default_factory=list)
    # Number of placeholder batches auto-created during this import.
    # Always 0 when auto_create_unmatched_batches=False on the command.
    auto_created_batches: int = 0
