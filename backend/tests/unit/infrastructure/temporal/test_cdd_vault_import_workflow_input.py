"""What the vault import workflow hands on: to its export, to its next run, to the sync record."""

from __future__ import annotations

from cellar.infrastructure.temporal.activities.dtos import ChunkItemResult
from cellar.infrastructure.temporal.workflows.cdd_vault_import import (
    CddVaultImportProgress,
    CddVaultImportWorkflowInput,
    _continue_input,
    _export_input,
    _sync_pairs,
)

NAMES = ["SACC-0001", "SACC-0002"]


def _input(**overrides) -> CddVaultImportWorkflowInput:
    values = {
        "workspace_id": "ws",
        "cdd_vault_id": "4443",
        "import_mode": "filtered",
        "submitted_by": "u",
        "originating_org_id": "org",
        "secret_ref": "ws:cdd_vault",
        "filter_criteria": {"names": NAMES},
        "entity_mappings": [{"entity_type": "molecule"}],
        "create_batch_on_duplicate": True,
    }
    return CddVaultImportWorkflowInput(**{**values, **overrides})


def test_export_input_carries_the_names_of_a_filtered_import() -> None:
    export = _export_input(_input(), modified_after=None)

    assert export.names == NAMES
    assert export.vault_id == "4443"
    assert export.secret_ref == "ws:cdd_vault"


def test_export_input_of_an_unfiltered_import_has_no_names() -> None:
    export = _export_input(
        _input(import_mode="sync", filter_criteria=None), modified_after="2026-04-14T00:00:00"
    )

    assert export.names is None
    assert export.modified_after == "2026-04-14T00:00:00"


def test_continue_input_keeps_the_filter_and_options_and_takes_progress() -> None:
    first = _input(max_molecules=900)
    progress = CddVaultImportProgress(
        import_id="imp",
        total_count=20000,
        registered_count=9000,
        duplicate_count=3000,
        error_count=4,
        skipped_count=496,
    )

    nxt = _continue_input(
        first,
        import_id="imp",
        storage_path="/data/cdd-exports/77",
        offset=12500,
        chunk_index=50,
        progress=progress,
    )

    assert nxt.filter_criteria == {"names": NAMES}
    assert nxt.import_mode == "filtered"
    assert nxt.max_molecules == 900
    assert nxt.entity_mappings == [{"entity_type": "molecule"}]
    assert nxt.create_batch_on_duplicate is True
    assert nxt.import_id == "imp"
    assert nxt.storage_path == "/data/cdd-exports/77"
    assert nxt.resume_offset == 12500
    assert nxt.resume_chunk_index == 50
    assert nxt.total_count == 20000
    assert nxt.cumulative_registered == 9000
    assert nxt.cumulative_duplicate == 3000
    assert nxt.cumulative_error == 4
    assert nxt.cumulative_skipped == 496


RESULTS = [
    ChunkItemResult(
        row_index=0,
        success=True,
        molecule_id="m-1",
        cdd_molecule_id=11,
        cdd_modified_at="2026-11-01T00:00:00Z",
    ),
    ChunkItemResult(row_index=1, success=False, cdd_molecule_id=12, error="bad structure"),
]


def test_a_whole_vault_import_records_what_it_registered_for_the_next_sync() -> None:
    assert _sync_pairs("full_vault", RESULTS) == [
        {"cdd_molecule_id": 11, "molecule_id": "m-1", "cdd_modified_at": "2026-11-01T00:00:00Z"}
    ]


def test_a_filtered_import_leaves_the_sync_watermark_alone() -> None:
    assert _sync_pairs("filtered", RESULTS) == []
