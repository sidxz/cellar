"""2D structure depiction via RDKit."""

from __future__ import annotations

import base64
import io

from rdkit import Chem
from rdkit.Chem import Draw
from rdkit.Chem.Draw import rdMolDraw2D


class DepictionGenerator:
    """Generates 2D depictions of molecules (SVG and PNG)."""

    def generate_svg(self, mol: object, width: int = 400, height: int = 300) -> str:
        """Render a molecule as an SVG string."""
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        drawer.DrawMolecule(mol)  # type: ignore[arg-type]
        drawer.FinishDrawing()
        return drawer.GetDrawingText()

    def generate_pngs_for_smiles(
        self, smiles_list: list[str], *, width: int = 150, height: int = 100
    ) -> dict[str, str]:
        """Render a batch of SMILES strings as base64-encoded PNGs.

        Invalid or empty SMILES are skipped silently. Duplicates are
        deduplicated. Returned dict maps each successfully rendered SMILES
        to its base64 PNG payload.
        """
        images: dict[str, str] = {}
        for smiles in smiles_list:
            if not smiles or smiles in images:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            img = Draw.MolToImage(mol, size=(width, height))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            images[smiles] = base64.b64encode(buf.getvalue()).decode()
        return images
