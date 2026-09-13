"""Unit tests for the RDKit MCS calculator."""

from __future__ import annotations

from rdkit import Chem

from cellar.infrastructure.rdkit.mcs_calculator import RdkitMcsCalculator

# A congeneric series: quinoline-4-carboxylic acid with varied substituents.
SERIES = [
    "Cc1ccc2ncc(C(=O)O)c(N)c2c1",
    "Clc1ccc2ncc(C(=O)O)c(NC)c2c1",
    "COc1ccc2ncc(C(=O)O)c(N)c2c1",
]


def test_finds_the_shared_core_of_a_congeneric_series():
    result = RdkitMcsCalculator().compute(SERIES, timeout_seconds=10)

    assert result.num_atoms == 14
    assert result.num_bonds == 15
    assert result.timed_out is False
    assert result.molecule_count == 3
    assert result.smarts.startswith("[#")

    # The core is the quinoline plus the two substituents the series shares —
    # a Bemis-Murcko scaffold would have dropped the amine and the acid.
    assert result.core_smiles == "Nc1c(C(=O)O)cnc2ccccc12"


def test_core_smiles_is_a_real_smiles_the_rest_of_the_system_can_read():
    # This is the whole point of core_smiles: /molecules/depict and R-group
    # decomposition take SMILES, and RDKit's SMARTS does not round-trip
    # through MolFromSmiles.
    result = RdkitMcsCalculator().compute(SERIES, timeout_seconds=10)

    assert result.core_smiles is not None
    assert Chem.MolFromSmiles(result.core_smiles) is not None
    assert Chem.MolFromSmiles(result.smarts) is None


def test_unrelated_molecules_share_nothing():
    result = RdkitMcsCalculator().compute(
        ["CC(=O)Oc1ccccc1C(=O)O", "C1CCOC1", "CCCCCCCC"], timeout_seconds=10
    )

    assert result.num_atoms == 0
    assert result.is_empty is True
    assert result.core_smiles is None
    assert result.molecule_count == 3


def test_rings_match_rings_only():
    # An aliphatic chain of the same length as a ring must not be reported as
    # a shared ring: `ringMatchesRingOnly` + `completeRingsOnly` are what make
    # the answer usable as a core.
    result = RdkitMcsCalculator().compute(["c1ccccc1C", "CCCCCCC"], timeout_seconds=10)

    assert result.num_atoms <= 1


def test_unparseable_smiles_are_skipped_not_fatal():
    result = RdkitMcsCalculator().compute(
        [SERIES[0], "not-a-molecule", SERIES[1]], timeout_seconds=10
    )

    # The answer covers the two that parsed, and says so.
    assert result.molecule_count == 2
    assert result.num_atoms > 0


def test_a_single_molecule_is_its_own_core():
    result = RdkitMcsCalculator().compute(["c1ccccc1"], timeout_seconds=10)

    assert result.molecule_count == 1
    assert result.core_smiles == "c1ccccc1"
    assert result.timed_out is False


def test_no_molecules_at_all():
    result = RdkitMcsCalculator().compute([], timeout_seconds=10)

    assert result.molecule_count == 0
    assert result.is_empty is True
    assert result.core_smiles is None
