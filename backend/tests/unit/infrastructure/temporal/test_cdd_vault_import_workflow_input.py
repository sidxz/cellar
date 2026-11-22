"""What the vault import workflow hands on: to its export, to its next run, to the sync record."""

from __future__ import annotations

from cellar.infrastructure.temporal.activities.dtos import ChunkItemResult
from cellar.infrastructure.temporal.workflows.cdd_vault_import import (
    RUN_SETTINGS_KEYS,
    CddVaultImportProgress,
    CddVaultImportWorkflowInput,
    _continue_input,
    _export_input,
    _run_settings,
    _sync_pairs,
)

NAMES = ["SACC-0001", "SACC-0002"]


def _input(**overrides) -> CddVaultImportWorkflowInput:
    values = {
        "workspace_id": "ws",
        "cdd_vault_id": "4443",
        "import_mode": "filtered",
        "submitted_by": "u",
        "secret_ref": "ws:cdd_vault",
        "filter_criteria": {"names": NAMES},
        "entity_mappings": [{"entity_type": "molecule"}],
        "registration_mapping": [{"header": "name", "target": "name"}],
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
    assert nxt.registration_mapping == [{"header": "name", "target": "name"}]
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


def test_run_settings_are_what_a_resumed_run_needs() -> None:
    first = _input(max_molecules=900)

    settings = _run_settings(first)

    assert settings == {
        "registration_mapping": [{"header": "name", "target": "name"}],
        "entity_mappings": [{"entity_type": "molecule"}],
        "create_batch_on_duplicate": True,
        "max_molecules": 900,
        "secret_ref": "ws:cdd_vault",
    }
    assert set(settings) == set(RUN_SETTINGS_KEYS)
    restarted = CddVaultImportWorkflowInput(**{**_input().__dict__, **settings})
    assert _run_settings(restarted) == settings


def test_old_cdd_workflow_payload_still_decodes() -> None:
    """A run started before this release has none of the new keys; it must still decode."""
    from temporalio.converter import DataConverter

    old = {
        "workspace_id": "ws", "cdd_vault_id": "4443", "import_mode": "full_vault",
        "submitted_by": "u", "originating_org_id": "org", "secret_ref": "ws:cdd_vault",
        "entity_mappings": [],
    }
    converter = DataConverter.default.payload_converter
    (payload,) = converter.to_payloads([old])
    (decoded,) = converter.from_payloads([payload], [CddVaultImportWorkflowInput])
    assert decoded.submitted_by_org_id is None and decoded.disclosed_by_org_id is None


def test_continue_input_carries_submitter_org_and_discloser_pick() -> None:
    first = _input(submitted_by_org_id="duar", disclosed_by="jane", disclosed_by_org_id="partner")
    nxt = _continue_input(
        first, import_id="imp", storage_path=None, offset=0, chunk_index=0,
        progress=CddVaultImportProgress(),
    )
    assert (nxt.submitted_by_org_id, nxt.disclosed_by, nxt.disclosed_by_org_id) == (
        "duar", "jane", "partner",
    )

