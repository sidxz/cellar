from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


class SdfRenderer:
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        writer = Chem.SDWriter(str(out_path))
        try:
            async for batch in batches:
                for row in batch:
                    smiles = row.cells.get("smiles") or row.raw.get("smiles")
                    if not smiles:
                        continue
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        continue
                    AllChem.Compute2DCoords(mol)
                    for col in columns:
                        if col.key == "smiles" or col.kind == "image_curve":
                            continue
                        v = row.cells.get(col.key)
                        if v is None or v == "":
                            continue
                        mol.SetProp(col.header, _serialize(v))
                    writer.write(mol)
        finally:
            writer.close()


def _serialize(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
