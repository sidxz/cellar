"""Tests for Molecule.bemis_murcko_smiles field."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.chemical_registration.enums import MoleculeType, StructureStatus
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def aspirin_structure() -> ChemicalStructure:
    return ChemicalStructure(
        smiles="CC(=O)Oc1ccccc1C(=O)O",
        cxsmiles="CC(=O)Oc1ccccc1C(=O)O",
        inchi="InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
        inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        molfile="fake_molfile_data",
    )


@pytest.fixture
def aspirin_descriptors() -> ComputedDescriptors:
    return ComputedDescriptors(
        molecular_formula="C9H8O4",
        molecular_weight=180.16,
        exact_mass=180.042,
        logp=1.31,
        tpsa=63.60,
        hbd=1,
        hba=4,
        rotatable_bonds=3,
        aromatic_rings=1,
        ring_count=1,
        heavy_atom_count=13,
        ro5_violations=0,
    )


def _make_minimal_molecule(
    ws_id: uuid.UUID,
    org_id: uuid.UUID,
    structure: ChemicalStructure,
    descriptors: ComputedDescriptors,
    **kwargs,
) -> Molecule:
    """Build the smallest valid disclosed Molecule, forwarding extra kwargs."""
    return Molecule(
        workspace_id=ws_id,
        registration_number=RegistrationNumber(value="CV-00001"),
        name="Aspirin",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        structure=structure,
        descriptors=descriptors,
        molecular_formula=descriptors.molecular_formula,
        structure_status=StructureStatus.DISCLOSED,
        originating_org_id=org_id,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_molecule_default_bemis_murcko_is_none(
    ws_id: uuid.UUID,
    org_id: uuid.UUID,
    aspirin_structure: ChemicalStructure,
    aspirin_descriptors: ComputedDescriptors,
) -> None:
    mol = _make_minimal_molecule(ws_id, org_id, aspirin_structure, aspirin_descriptors)
    assert mol.bemis_murcko_smiles is None


def test_molecule_accepts_scaffold_smiles(
    ws_id: uuid.UUID,
    org_id: uuid.UUID,
    aspirin_structure: ChemicalStructure,
    aspirin_descriptors: ComputedDescriptors,
) -> None:
    mol = _make_minimal_molecule(
        ws_id,
        org_id,
        aspirin_structure,
        aspirin_descriptors,
        bemis_murcko_smiles="c1ccccc1",
    )
    assert mol.bemis_murcko_smiles == "c1ccccc1"


def test_molecule_accepts_empty_string_for_acyclic(
    ws_id: uuid.UUID,
    org_id: uuid.UUID,
    aspirin_structure: ChemicalStructure,
    aspirin_descriptors: ComputedDescriptors,
) -> None:
    mol = _make_minimal_molecule(
        ws_id,
        org_id,
        aspirin_structure,
        aspirin_descriptors,
        bemis_murcko_smiles="",
    )
    assert mol.bemis_murcko_smiles == ""
