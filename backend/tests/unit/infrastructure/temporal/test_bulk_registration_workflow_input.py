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
