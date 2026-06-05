"""Molecule structure PNG renderer for exports.

Wraps :class:`DepictionGenerator` to produce PNG bytes (not base64) at
size presets that match ``reportConfig.imageSize``. Used by both XLSX
(``openpyxl.drawing.image.Image``) and PDF (inline base64 data URI).

Batches by SMILES — same SMILES across many rows renders once.
"""

from __future__ import annotations

import base64
from typing import Literal

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

StructureSize = Literal["small", "medium", "large"]

STRUCTURE_SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "small": (120, 80),
    "medium": (160, 120),
    "large": (240, 180),
}


def _resolve_size(size: StructureSize | tuple[int, int] | None) -> tuple[int, int]:
    if size is None:
        return STRUCTURE_SIZE_PRESETS["medium"]
    if isinstance(size, str):
        return STRUCTURE_SIZE_PRESETS.get(size, STRUCTURE_SIZE_PRESETS["medium"])
    return size


def render_structure_pngs(
    smiles_list: list[str | None],
    *,
    size: StructureSize | tuple[int, int] | None = None,
) -> dict[str, bytes]:
    """Render a batch of SMILES → ``{smiles: PNG bytes}``.

    Invalid / empty SMILES are skipped silently. Duplicates dedupe. PNG is
    drawn via ``rdMolDraw2D.MolDraw2DCairo`` which produces antialiased
    output suitable for embedding in spreadsheets and PDFs.
    """
    width, height = _resolve_size(size)
    out: dict[str, bytes] = {}
    for smiles in smiles_list:
        if not smiles or smiles in out:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        out[smiles] = drawer.GetDrawingText()
    return out


def render_structure_data_uri(
    smiles: str | None,
    *,
    size: StructureSize | tuple[int, int] | None = None,
) -> str | None:
    """Render one SMILES → data:image/png;base64,... URL or None."""
    if not smiles:
        return None
    pngs = render_structure_pngs([smiles], size=size)
    png = pngs.get(smiles)
    if png is None:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
