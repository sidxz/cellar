"""2D structure depiction via RDKit."""

from __future__ import annotations

from rdkit.Chem.Draw import rdMolDraw2D


class DepictionGenerator:
    """Generates 2D SVG depictions of molecules."""

    def generate_svg(
        self, mol: object, width: int = 400, height: int = 300
    ) -> str:
        """Render a molecule as an SVG string."""
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        drawer.DrawMolecule(mol)  # type: ignore[arg-type]
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
