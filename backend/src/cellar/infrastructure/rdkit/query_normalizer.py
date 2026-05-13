"""Substructure-query normalization.

Why this exists:
The PostgreSQL RDKit cartridge stores molecules with aromaticity perceived —
benzene becomes ``c1ccccc1`` (aromatic bonds) regardless of whether the
input SMILES was Kekulé. The cartridge's substructure operator (``@>``)
matches SMARTS bonds *literally*: an explicit ``-`` or ``=`` does NOT
match an aromatic bond.

Ketcher (the structure editor used in the UI) exports a drawn benzene as
the Kekulé SMARTS ``[#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1``. Sent straight to
the cartridge, this matches **zero** of the 500+ benzene-containing
molecules in a typical vault — i.e. the most common medicinal-chemistry
substructure query is silently broken.

The fix: try parsing the user's input as SMILES (which runs full
aromaticity perception), and re-export it as SMARTS. If the input is a
SMARTS-only construct (recursive SMARTS, atom lists, query primitives
like ``[!#1]`` or ``[#6;a]``), SMILES parsing fails — fall back to the
original text and let the cartridge handle it.
"""

from __future__ import annotations

from rdkit import Chem


def aromatize_substructure_query(query: str) -> str:
    """Return an aromaticity-aware SMARTS form of ``query`` when possible.

    Parses ``query`` as a SMILES first (which performs aromaticity
    perception during sanitization), then writes it back out as SMARTS.
    Aromatic rings come out with ``:`` bonds; explicit single/double
    bonds in non-aromatic regions are preserved.

    If the input cannot be parsed as SMILES (e.g. it uses SMARTS-only
    query primitives), the original string is returned unchanged so the
    cartridge's ``qmol_from_smarts`` path can handle it.
    """
    if not query:
        return query
    mol = Chem.MolFromSmiles(query)
    if mol is None:
        return query
    return Chem.MolToSmarts(mol)
