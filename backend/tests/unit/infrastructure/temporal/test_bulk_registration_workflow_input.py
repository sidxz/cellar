"""continue_as_new must carry every non-progress field of the input; a field
listed by hand there is silently dropped the day someone adds a new option."""

from __future__ import annotations

from cellar.infrastructure.temporal.workflows.bulk_registration import (
    BulkRegistrationProgress,
    BulkRegistrationWorkflowInput,
    _continue_input,
)


def test_continue_input_keeps_options_and_takes_progress() -> None:
    first = BulkRegistrationWorkflowInput(
        workspace_id="ws",
        originating_org_id="org",
        submitted_by="u",
        source_file="f.csv",
        file_format="csv",
        storage_path="/tmp/f.csv",
        filename="f.csv",
        create_batch_on_duplicate=True,
        project_ids=["p-1", "p-2"],
    )
    progress = BulkRegistrationProgress(total_count=10, registered_count=4, chunks_processed=2)

    nxt = _continue_input(
        first, bulk_reg_id="br", progress=progress, remaining_chunks=[[{"row_index": 9}]]
    )

    assert nxt.project_ids == ["p-1", "p-2"]
    assert nxt.create_batch_on_duplicate is True
    assert nxt.resume_bulk_reg_id == "br"
    assert nxt.resume_chunk_index == 2
    assert nxt.resume_registered == 4
    assert nxt.resume_chunks == [[{"row_index": 9}]]


def test_continue_as_new_carries_submitter_org() -> None:
    first = BulkRegistrationWorkflowInput(
        workspace_id="ws", originating_org_id="org", submitted_by="u", source_file="f.csv",
        file_format="csv", storage_path="/tmp/f.csv", filename="f.csv",
        submitted_by_org_id="duar-org", disclosed_by="jane", disclosed_by_org_id="partner",
    )
    nxt = _continue_input(
        first, bulk_reg_id="br", progress=BulkRegistrationProgress(), remaining_chunks=[]
    )
    assert (nxt.submitted_by_org_id, nxt.disclosed_by, nxt.disclosed_by_org_id) == (
        "duar-org", "jane", "partner",
    )


def test_old_bulk_workflow_payload_still_decodes() -> None:
    """A run started before this release has none of the new keys; it must still decode."""
    from temporalio.converter import DataConverter

    old = {
        "workspace_id": "ws", "originating_org_id": "org", "submitted_by": "u",
        "source_file": "f.csv", "file_format": "csv", "storage_path": "/tmp/f.csv",
        "filename": "f.csv",
    }
    converter = DataConverter.default.payload_converter
    (payload,) = converter.to_payloads([old])
    (decoded,) = converter.from_payloads([payload], [BulkRegistrationWorkflowInput])
    assert decoded.submitted_by_org_id is None and decoded.disclosed_by is None

