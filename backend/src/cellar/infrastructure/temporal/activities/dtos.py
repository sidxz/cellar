"""Temporal activity DTOs — all JSON-serializable (str UUIDs, plain dicts).

These cross the workflow ↔ activity boundary and are stored in
Temporal's event history, so they must be small and serializable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Registration activity
# ---------------------------------------------------------------------------


@dataclass
class ChunkItem:
    """A single molecule record within a processing chunk."""

    row_index: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = field(default_factory=list)
    # Batch fields
    amount_value: float | None = None
    amount_unit: str = "mg"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    purity: float | None = None
    batch_source: str = "synthesized"
    appearance: str | None = None
    vendor_catalog_number: str | None = None  # CDD molecule_batch_identifier
    cdd_molecule_id: int | None = None
    cdd_batch_id: int | None = None  # CDD batch numeric ID (for plate well resolution)
    cdd_modified_at: str | None = None  # ISO timestamp from CDD


@dataclass
class ChunkInput:
    """Input for the process_chunk activity."""

    workspace_id: str
    originating_org_id: str
    submitted_by: str
    items: list[ChunkItem] = field(default_factory=list)
    chunk_index: int = 0
    create_batch_on_duplicate: bool | None = None


@dataclass
class ChunkItemResult:
    """Result for a single molecule within a chunk."""

    row_index: int
    success: bool
    is_new: bool = False
    action: str = (
        "registered"  # registered | deduplicated | disclosed | merge_candidate | conflict
    )
    molecule_id: str | None = None
    batch_id: str | None = None
    batch_number: str | None = None
    salt_matched: bool = False
    needs_merge_confirmation: bool = False
    matched_molecule_id: str | None = None
    disclosure_id: str | None = None
    conflict_reason: str | None = None
    error: str | None = None
    cdd_molecule_id: int | None = None
    cdd_modified_at: str | None = None
    batch_skipped: bool = False


@dataclass
class ChunkOutput:
    """Output of the process_chunk activity."""

    registered: int = 0
    duplicate: int = 0
    error: int = 0
    disclosed: int = 0
    merge_candidate: int = 0
    conflict: int = 0
    # Molecule-level counts (batch-rows grouped by row_index).
    # A molecule is "registered" if any row was is_new, "duplicate" if all
    # rows were existing, "error" if all rows failed.
    mol_registered: int = 0
    mol_duplicate: int = 0
    mol_error: int = 0
    results: list[ChunkItemResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# BulkRegistration tracking
# ---------------------------------------------------------------------------


@dataclass
class CreateBulkRegInput:
    """Input for creating a BulkRegistration aggregate."""

    workspace_id: str
    source_file: str
    file_format: str
    submitted_by: str
    total_count: int
    workflow_id: str | None = None


@dataclass
class PersistChunkItemsInput:
    """Input for persisting per-row outcomes of a processed chunk.

    Carries the chunk's full ChunkItemResult set across the activity boundary
    so the activity can record items + roll up counters in one transaction.
    """

    workspace_id: str
    bulk_reg_id: str
    items: list[dict] = field(default_factory=list)  # serialized ChunkItemResult dicts


@dataclass
class UpdateBulkRegProgressInput:
    """Input for updating BulkRegistration progress counters."""

    workspace_id: str
    bulk_reg_id: str
    registered: int = 0
    duplicate: int = 0
    error: int = 0


@dataclass
class CompleteBulkRegInput:
    """Input for completing a BulkRegistration."""

    workspace_id: str
    bulk_reg_id: str


# ---------------------------------------------------------------------------
# CDD import tracking
# ---------------------------------------------------------------------------


@dataclass
class CreateCddImportInput:
    """Input for creating a CddMoleculeImport aggregate."""

    workspace_id: str
    cdd_vault_id: str
    import_mode: str
    originating_org_id: str
    submitted_by: str
    workflow_id: str | None = None
    filter_criteria: dict | None = None


@dataclass
class CompleteDiscoveryInput:
    """Input for completing discovery phase (DISCOVERING -> PROCESSING)."""

    workspace_id: str
    import_id: str
    total_count: int


@dataclass
class UpdateCddImportProgressInput:
    """Input for updating CDD import progress counters."""

    workspace_id: str
    import_id: str
    registered: int = 0
    duplicate: int = 0
    error: int = 0
    skipped: int = 0
    last_processed_offset: int = 0


@dataclass
class CompleteCddImportInput:
    """Input for completing a CDD import."""

    workspace_id: str
    import_id: str


@dataclass
class FailCddImportInput:
    """Input for failing a CDD import."""

    workspace_id: str
    import_id: str
    reason: str


@dataclass
class CddSyncWatermarkInput:
    """Input for fetching the sync high-water-mark timestamp."""

    workspace_id: str
    vault_id: str


@dataclass
class CddSyncWatermarkOutput:
    """Output of the sync watermark lookup."""

    modified_after: str | None = None  # ISO 8601 or None if first sync
    synced_count: int = 0


@dataclass
class RecordSyncMappingsInput:
    workspace_id: str
    cdd_vault_id: str
    mappings: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CDD fetch
# ---------------------------------------------------------------------------


@dataclass
class CddStartExportInput:
    """Input for starting a CDD async molecule export."""

    workspace_id: str
    secret_ref: str
    vault_id: str
    max_molecules: int | None = None
    molecule_ids: list[int] | None = None
    modified_after: str | None = None  # ISO 8601 timestamp for sync mode


@dataclass
class CddStartExportOutput:
    """Output of starting a CDD export."""

    export_id: int
    total_count: int


@dataclass
class CddPollExportInput:
    """Input for polling a CDD export."""

    workspace_id: str
    secret_ref: str
    vault_id: str
    export_id: int


@dataclass
class CddPollExportOutput:
    """Output of polling a CDD export."""

    finished: bool
    count: int = 0
    storage_path: str | None = None  # path to JSON file on disk (not inline)


# ---------------------------------------------------------------------------
# CDD export chunk loading
# ---------------------------------------------------------------------------


@dataclass
class LoadExportChunkInput:
    """Input for loading a chunk from a saved CDD export."""

    storage_path: str
    offset: int
    limit: int
    max_molecules: int | None = None
    entity_mappings: list[dict] | None = None  # serialized EntityMapping dicts


@dataclass
class LoadExportChunkOutput:
    """Output of loading an export chunk — mapped to ChunkItems."""

    items: list[dict]  # serialized ChunkItem dicts
    skipped: int = 0
    has_more: bool = False
    molecule_count: int = 0  # distinct molecules (before batch expansion)


# ---------------------------------------------------------------------------
# CDD plate import tracking
# ---------------------------------------------------------------------------


@dataclass
class CreateCddPlateImportInput:
    """Input for creating a CddPlateImport aggregate."""

    workspace_id: str
    cdd_vault_id: str
    submitted_by: str
    workflow_id: str | None = None


@dataclass
class UpdateCddPlateImportProgressInput:
    """Input for updating CDD plate import progress counters."""

    workspace_id: str
    import_id: str
    plates_registered: int = 0
    plates_duplicate: int = 0
    plates_error: int = 0
    wells_mapped: int = 0
    wells_unresolved: int = 0
    last_processed_offset: int = 0


@dataclass
class CompleteCddPlateImportInput:
    """Input for completing a CDD plate import."""

    workspace_id: str
    import_id: str


@dataclass
class FailCddPlateImportInput:
    """Input for failing a CDD plate import."""

    workspace_id: str
    import_id: str
    reason: str


@dataclass
class RecordPlateSyncMappingsInput:
    workspace_id: str
    cdd_vault_id: str
    mappings: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CDD plate fetch
# ---------------------------------------------------------------------------


@dataclass
class CddStartPlateExportInput:
    """Input for starting a CDD async plate export."""

    workspace_id: str
    secret_ref: str
    vault_id: str


@dataclass
class LoadPlateChunkInput:
    """Input for loading a chunk from a saved CDD plate export."""

    storage_path: str
    offset: int
    limit: int
    entity_mappings: list[dict] | None = None  # serialized EntityMapping dicts


@dataclass
class PlateChunkItem:
    """A single plate record within a processing chunk."""

    cdd_plate_id: int
    name: str
    format: str  # "96", "384", etc.
    wells: list[dict] = field(default_factory=list)  # [{position, cdd_batch_id}, ...]


@dataclass
class LoadPlateChunkOutput:
    """Output of loading a plate export chunk."""

    items: list[dict] = field(default_factory=list)  # serialized PlateChunkItem dicts
    has_more: bool = False


@dataclass
class PlateChunkInput:
    """Input for the process_plate_chunk activity."""

    workspace_id: str
    cdd_vault_id: str
    submitted_by: str
    items: list[PlateChunkItem] = field(default_factory=list)
    chunk_index: int = 0


@dataclass
class PlateChunkOutput:
    """Output of the process_plate_chunk activity."""

    plates_registered: int = 0
    plates_duplicate: int = 0
    plates_error: int = 0
    wells_mapped: int = 0
    wells_unresolved: int = 0
    sync_pairs: list[dict] = field(
        default_factory=list
    )  # [{cdd_plate_id, plate_id, cdd_statistics}]
