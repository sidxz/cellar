"""The parse activity hands the parser's warnings to the run (process_chunk reports them)."""

from __future__ import annotations

from pathlib import Path

from temporalio.testing import ActivityEnvironment

from cellar.infrastructure.temporal.activities.file_parsing import (
    FileParsingActivities,
    ParseFileInput,
)


async def test_a_value_not_stored_reaches_the_chunk_item(tmp_path: Path) -> None:
    f = tmp_path / "rows.csv"
    f.write_text(f"name,smiles,custom_id\nA,CCO,{'x' * 300}\n")

    out = await ActivityEnvironment().run(
        FileParsingActivities().parse_file,
        ParseFileInput(storage_path=str(f), file_format="csv", filename="rows.csv"),
    )

    (item,) = out.chunks[0]
    assert len(item["warnings"]) == 1 and "longer than 255" in item["warnings"][0]
