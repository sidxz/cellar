"""The one rule for what a registration will do — shared by RegisterMolecule and the preview.

The trap these tests guard: POST /molecules promotes ``name`` to an identifier, so a
classifier that only reads external_ids would say "registered" for a row that in fact
deduplicates or conflicts on its name.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from cellar.application.chemical_registration.registration_classifier import (
    classify_disclosed,
    classify_undisclosed,
    collect_identifiers,
)
from cellar.domain.chemical_registration.enums import MoleculeType, RegistrationAction
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
INCHI_KEY = "UHOVQNZJYSORNB-UHFFFAOYSA-N"

_STRUCTURE = ChemicalStructure(
    smiles="c1ccccc1",
    cxsmiles="c1ccccc1",
    inchi="InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
    inchi_key=INCHI_KEY,
    molfile="fake",
)
_DESCRIPTORS = ComputedDescriptors(
    molecular_formula="C6H6",
    molecular_weight=78.11,
    exact_mass=78.047,
    logp=1.56,
    tpsa=0.0,
    hbd=0,
    hba=0,
    rotatable_bonds=0,
    aromatic_rings=1,
    ring_count=1,
    heavy_atom_count=6,
    ro5_violations=0,
)


def _disclosed(name: str = "Known-001") -> Molecule:
    return Molecule.register_disclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CC-000001"),
        name=name,
        molecule_type=MoleculeType.SMALL_MOLECULE,
        structure=_STRUCTURE,
        descriptors=_DESCRIPTORS,
        originating_org_id=ORG_ID,
    )


def _undisclosed(name: str = "Partner-001") -> Molecule:
    return Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CC-000002"),
        name=name,
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )


def _repo(
    *,
    by_inchi: Molecule | None = None,
    undisclosed: Molecule | None = None,
    owners: dict[str, uuid.UUID] | None = None,
    by_id: Molecule | None = None,
) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_inchi_key = AsyncMock(return_value=by_inchi)
    repo.find_undisclosed_by_identifiers = AsyncMock(return_value=undisclosed)
    repo.find_identifiers_in_workspace = AsyncMock(return_value=owners or {})
    repo.find_by_id_in_workspace = AsyncMock(return_value=by_id)
    return repo


class TestCollectIdentifiers:
    def test_name_is_folded_in_when_promoted(self) -> None:
        assert collect_identifiers("CPD-1", ["EXT-9"], promote_name=True) == {"CPD-1", "EXT-9"}

    def test_name_is_left_out_when_not_promoted(self) -> None:
        assert collect_identifiers("Compound-7", ["EXT-9"], promote_name=False) == {"EXT-9"}

    def test_empty_name_is_never_an_identifier(self) -> None:
        assert collect_identifiers("", [], promote_name=True) == set()


class TestClassifyDisclosed:
    async def test_nothing_known_registers(self) -> None:
        forecast = await classify_disclosed(
            _repo(), WS_ID, INCHI_KEY, {"New-1"}, detect_undisclosed=True
        )
        assert forecast.action == RegistrationAction.REGISTERED
        assert forecast.matched_molecule is None

    async def test_name_only_owned_by_another_structure_is_a_conflict(self) -> None:
        """The trap: name + smiles, no external_ids, name already taken elsewhere."""
        other = _disclosed("Taken")
        forecast = await classify_disclosed(
            _repo(owners={"Taken": other.id}),
            WS_ID,
            "DIFFERENT-INCHI-KEY",
            {"Taken"},
            detect_undisclosed=True,
        )
        assert forecast.action == RegistrationAction.CONFLICT
        assert "Taken" in (forecast.conflict_reason or "")

    async def test_same_structure_deduplicates_even_when_name_is_on_that_molecule(self) -> None:
        existing = _disclosed("Known-001")
        forecast = await classify_disclosed(
            _repo(by_inchi=existing, owners={"Known-001": existing.id}),
            WS_ID,
            INCHI_KEY,
            {"Known-001"},
            detect_undisclosed=True,
        )
        assert forecast.action == RegistrationAction.DEDUPLICATED
        assert forecast.matched_molecule is existing

    async def test_same_structure_but_name_owned_elsewhere_is_a_conflict(self) -> None:
        existing = _disclosed("Known-001")
        forecast = await classify_disclosed(
            _repo(by_inchi=existing, owners={"Other-Alias": uuid.uuid4()}),
            WS_ID,
            INCHI_KEY,
            {"Other-Alias"},
            detect_undisclosed=True,
        )
        assert forecast.action == RegistrationAction.CONFLICT

    async def test_name_only_matching_an_undisclosed_molecule_discloses(self) -> None:
        partner = _undisclosed("Partner-001")
        forecast = await classify_disclosed(
            _repo(undisclosed=partner, owners={"Partner-001": partner.id}),
            WS_ID,
            INCHI_KEY,
            {"Partner-001"},
            detect_undisclosed=True,
        )
        assert forecast.action == RegistrationAction.DISCLOSED
        assert forecast.matched_molecule is partner

    async def test_undisclosed_detection_can_be_switched_off(self) -> None:
        partner = _undisclosed("Partner-001")
        repo = _repo(undisclosed=partner, owners={"Partner-001": partner.id})
        forecast = await classify_disclosed(
            repo, WS_ID, INCHI_KEY, {"Partner-001"}, detect_undisclosed=False
        )
        # Without detection the identifier is simply taken by someone else.
        assert forecast.action == RegistrationAction.CONFLICT
        repo.find_undisclosed_by_identifiers.assert_not_awaited()


class TestClassifyUndisclosed:
    async def test_nothing_known_registers(self) -> None:
        forecast = await classify_undisclosed(_repo(), WS_ID, {"New-1"})
        assert forecast.action == RegistrationAction.REGISTERED

    async def test_identifiers_split_across_molecules_is_a_conflict(self) -> None:
        forecast = await classify_undisclosed(
            _repo(owners={"A": uuid.uuid4(), "B": uuid.uuid4()}), WS_ID, {"A", "B"}
        )
        assert forecast.action == RegistrationAction.CONFLICT
        assert "different molecules" in (forecast.conflict_reason or "")

    async def test_name_only_claimed_by_a_disclosed_molecule_is_a_conflict(self) -> None:
        known = _disclosed("Known-001")
        forecast = await classify_undisclosed(
            _repo(owners={"Known-001": known.id}, by_id=known), WS_ID, {"Known-001"}
        )
        assert forecast.action == RegistrationAction.CONFLICT
        assert "CC-000001" in (forecast.conflict_reason or "")

    async def test_name_only_matching_an_undisclosed_molecule_deduplicates(self) -> None:
        partner = _undisclosed("Partner-001")
        forecast = await classify_undisclosed(
            _repo(owners={"Partner-001": partner.id}, by_id=partner), WS_ID, {"Partner-001"}
        )
        assert forecast.action == RegistrationAction.DEDUPLICATED
        assert forecast.matched_molecule is partner
