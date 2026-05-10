"""Unit tests for substructure query normalization."""

from __future__ import annotations

import pytest

from chem_vault.infrastructure.rdkit.query_normalizer import (
    aromatize_substructure_query,
)


# ---------------------------------------------------------------------------
# Aromatized outputs — Kekulé and SMILES inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_query",
    [
        "c1ccccc1",  # already-aromatic SMILES
        "C1=CC=CC=C1",  # Kekulé SMILES
        "[#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1",  # Ketcher Kekulé SMARTS
    ],
)
def test_benzene_inputs_normalize_to_aromatic_smarts(raw_query: str) -> None:
    """Benzene in any common form should normalize to an aromatic-bond SMARTS
    that the cartridge can match against aromatic-perceived molecules."""
    out = aromatize_substructure_query(raw_query)
    assert ":" in out, f"Expected aromatic bonds (:) in normalized output {out!r}"
    # All six bonds should be aromatic (no remaining - or =).
    assert "-" not in out
    assert "=" not in out


def test_aliphatic_chain_preserved() -> None:
    """Non-aromatic structures keep their explicit single/double bonds."""
    out = aromatize_substructure_query("CC(=O)O")  # acetic acid
    # Acetic acid has no aromatic atoms, so no `:` should appear.
    assert ":" not in out
    # Double bond on the carbonyl is preserved.
    assert "=" in out


def test_pyridine_ring_aromatized() -> None:
    out = aromatize_substructure_query("C1=CC=NC=C1")  # Kekulé pyridine
    assert ":" in out
    # Nitrogen retained.
    assert "#7" in out or "n" in out


# ---------------------------------------------------------------------------
# SMARTS-only fallthrough
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smarts_only",
    [
        "[!#1]",  # negation
        "[#6;a]",  # property class
        "[N,O]",  # atom list
    ],
)
def test_smarts_only_inputs_pass_through_unchanged(smarts_only: str) -> None:
    """Inputs that aren't valid SMILES (use SMARTS-only primitives) must be
    returned untouched so the cartridge's qmol_from_smarts can handle them."""
    assert aromatize_substructure_query(smarts_only) == smarts_only


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_query_returns_empty() -> None:
    assert aromatize_substructure_query("") == ""


def test_unparseable_input_passes_through() -> None:
    """Garbage strings are returned unchanged; the cartridge surfaces the error."""
    bogus = "ThisIsNotAValidStructure???"
    assert aromatize_substructure_query(bogus) == bogus
