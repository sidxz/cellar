"""Tests for StructureProcessor scaffold integration."""

from __future__ import annotations

import pytest
from returns.result import Success

from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator
from cellar.infrastructure.rdkit.structure_processor import StructureProcessor


@pytest.fixture()
def processor() -> StructureProcessor:
    """StructureProcessor with scaffold calculator wired."""
    return StructureProcessor(scaffold_calculator=MurckoScaffoldCalculator())


def test_processed_structure_includes_scaffold(processor: StructureProcessor) -> None:
    result = processor.process("CC(C)Cc1ccc(cc1)C(C)C(=O)O")  # ibuprofen
    assert isinstance(result, Success)
    assert result.unwrap().bemis_murcko_smiles == "c1ccccc1"


def test_acyclic_smiles_yields_empty_scaffold(processor: StructureProcessor) -> None:
    result = processor.process("CCCCC")
    assert isinstance(result, Success)
    assert result.unwrap().bemis_murcko_smiles == ""
