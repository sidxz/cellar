from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.sdf_renderer import SdfRenderer
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows: list[list[ExportRow]]) -> AsyncIterator[list[ExportRow]]:
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_sdf_writes_mol_blocks_and_data_tags(tmp_path: Path):
    cols = [
        ColumnSpec(key="registration_number", header="Reg #", kind="text"),
        ColumnSpec(key="name", header="Name", kind="text"),
        ColumnSpec(key="smiles", header="SMILES", kind="smiles"),
        ColumnSpec(key="molecular_weight", header="MW", kind="number"),
        ColumnSpec(key="drc:rd1:ec:50.0::value", header="Mtb::EC50", kind="number", unit="µM"),
        ColumnSpec(key="drc:rd1:ec:50.0::qualifier", header="Mtb::EC50::q", kind="qualifier"),
    ]
    rows = [[
        ExportRow(cells={
            "registration_number": "CV-1", "name": "ethanol", "smiles": "CCO",
            "molecular_weight": 46.07,
            "drc:rd1:ec:50.0::value": 1.23, "drc:rd1:ec:50.0::qualifier": "=",
        }, raw={"smiles": "CCO"}),
        ExportRow(cells={
            "registration_number": "CV-2", "name": "no_struct", "smiles": None,
            "molecular_weight": 380.1,
            "drc:rd1:ec:50.0::value": None, "drc:rd1:ec:50.0::qualifier": "ND",
        }, raw={"smiles": None}),
    ]]
    out = tmp_path / "out.sdf"
    await SdfRenderer().render(
        columns=cols,
        batches=_batches(rows),
        out_path=out,
        options=RenderOptions(),
        row_count_hint=2,
    )
    text = out.read_text()
    # RDKit SDWriter emits ">  <Header>  (N) " — assert with the angle-bracket prefix only.
    assert "<Reg #>" in text
    assert "CV-1" in text
    assert "<Mtb::EC50>" in text
    assert "1.23" in text
    assert text.count("$$$$") == 1   # 2nd row has no SMILES → skipped
