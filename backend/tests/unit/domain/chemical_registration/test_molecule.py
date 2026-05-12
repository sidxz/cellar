"""Tests for Molecule aggregate root."""

import uuid
from datetime import date

import pytest

from cellar.domain.chemical_registration.enums import (
    ComponentRole,
    IdentifierType,
    LifecycleStage,
    MoleculeType,
    RegistrationStatus,
    Stereochemistry,
    StructureStatus,
    SynthesisStatus,
)
from cellar.domain.chemical_registration.events import (
    MoleculeDisclosed,
    MoleculeLifecycleChanged,
    MoleculeMerged,
    MoleculeRegistered,
    MoleculeTagsUpdated,
)
from cellar.domain.chemical_registration.mixture_component import MixtureComponent
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    PredictedProperties,
    RegistrationNumber,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def reg_number() -> RegistrationNumber:
    return RegistrationNumber(value="CV-00001")


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


def _make_disclosed(
    ws_id: uuid.UUID,
    org_id: uuid.UUID,
    structure: ChemicalStructure,
    descriptors: ComputedDescriptors,
    reg_number: RegistrationNumber | None = None,
    **kwargs,
) -> Molecule:
    return Molecule.register_disclosed(
        workspace_id=ws_id,
        registration_number=reg_number or RegistrationNumber(value="CV-00001"),
        name="Aspirin",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        structure=structure,
        descriptors=descriptors,
        originating_org_id=org_id,
        **kwargs,
    )


def _make_undisclosed(
    ws_id: uuid.UUID, org_id: uuid.UUID, **kwargs
) -> Molecule:
    return Molecule.register_undisclosed(
        workspace_id=ws_id,
        registration_number=RegistrationNumber(value="CV-00002"),
        name="Partner Compound X",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=org_id,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Factory: register_disclosed
# ---------------------------------------------------------------------------


class TestRegisterDisclosed:
    def test_sets_all_fields(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
        reg_number: RegistrationNumber,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors, reg_number)

        assert mol.workspace_id == ws_id
        assert mol.registration_number == reg_number
        assert mol.name == "Aspirin"
        assert mol.molecule_type == MoleculeType.SMALL_MOLECULE
        assert mol.structure == aspirin_structure
        assert mol.descriptors == aspirin_descriptors
        assert mol.molecular_formula == "C9H8O4"
        assert mol.structure_status == StructureStatus.DISCLOSED
        assert mol.registration_status == RegistrationStatus.APPROVED
        assert mol.synthesis_status == SynthesisStatus.SYNTHESIZED
        assert mol.lifecycle_stage == LifecycleStage.REGISTERED
        assert mol.originating_org_id == org_id
        assert mol.version == 1
        assert mol.merged_into_id is None
        assert mol.identifiers == []
        assert mol.mixture_components == []

    def test_emits_registered_event(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        events = mol.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MoleculeRegistered)
        assert events[0].aggregate_id == mol.id
        assert events[0].registration_number == "CV-00001"
        assert events[0].workspace_id == ws_id

    def test_name_is_stripped(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = Molecule.register_disclosed(
            workspace_id=ws_id,
            registration_number=RegistrationNumber(value="CV-00001"),
            name="  Aspirin  ",
            molecule_type=MoleculeType.SMALL_MOLECULE,
            structure=aspirin_structure,
            descriptors=aspirin_descriptors,
            originating_org_id=org_id,
        )
        assert mol.name == "Aspirin"

    def test_empty_name_raises(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Molecule.register_disclosed(
                workspace_id=ws_id,
                registration_number=RegistrationNumber(value="CV-00001"),
                name="",
                molecule_type=MoleculeType.SMALL_MOLECULE,
                structure=aspirin_structure,
                descriptors=aspirin_descriptors,
                originating_org_id=org_id,
            )

    def test_molecular_formula_auto_set_from_descriptors(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        assert mol.molecular_formula == aspirin_descriptors.molecular_formula

    def test_optional_fields(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(
            ws_id,
            org_id,
            aspirin_structure,
            aspirin_descriptors,
            stereochemistry=Stereochemistry.ACHIRAL,
            tags=["tool compound"],
            invention_date=date(2024, 1, 15),
            custom_fields={"project": "oncology"},
        )
        assert mol.stereochemistry == Stereochemistry.ACHIRAL
        assert mol.tags == ["tool compound"]
        assert mol.invention_date == date(2024, 1, 15)
        assert mol.custom_fields == {"project": "oncology"}


# ---------------------------------------------------------------------------
# Factory: register_undisclosed
# ---------------------------------------------------------------------------


class TestRegisterUndisclosed:
    def test_sets_fields(self, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        assert mol.structure_status == StructureStatus.UNDISCLOSED
        assert mol.structure is None
        assert mol.descriptors is None
        assert mol.molecular_formula is None
        assert mol.synthesis_status == SynthesisStatus.VIRTUAL

    def test_emits_registered_event(self, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        events = mol.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MoleculeRegistered)

    def test_undisclosed_with_structure_raises(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        with pytest.raises(ValidationError, match="Undisclosed molecule must not have a structure"):
            Molecule(
                workspace_id=ws_id,
                registration_number=RegistrationNumber(value="CV-00001"),
                name="Bad",
                molecule_type=MoleculeType.SMALL_MOLECULE,
                structure=aspirin_structure,
                descriptors=aspirin_descriptors,
                structure_status=StructureStatus.UNDISCLOSED,
                originating_org_id=org_id,
            )


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_disclosed_without_structure_raises(
        self, ws_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="Disclosed molecule must have a structure"):
            Molecule(
                workspace_id=ws_id,
                registration_number=RegistrationNumber(value="CV-00001"),
                name="Bad",
                molecule_type=MoleculeType.SMALL_MOLECULE,
                structure=None,
                descriptors=None,
                structure_status=StructureStatus.DISCLOSED,
                originating_org_id=org_id,
            )

    def test_disclosed_without_descriptors_raises(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
    ) -> None:
        with pytest.raises(ValidationError, match="Disclosed molecule must have computed descriptors"):
            Molecule(
                workspace_id=ws_id,
                registration_number=RegistrationNumber(value="CV-00001"),
                name="Bad",
                molecule_type=MoleculeType.SMALL_MOLECULE,
                structure=aspirin_structure,
                descriptors=None,
                structure_status=StructureStatus.DISCLOSED,
                originating_org_id=org_id,
            )

    def test_molecular_formula_mismatch_raises(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        with pytest.raises(ValidationError, match="does not match"):
            Molecule(
                workspace_id=ws_id,
                registration_number=RegistrationNumber(value="CV-00001"),
                name="Bad",
                molecule_type=MoleculeType.SMALL_MOLECULE,
                structure=aspirin_structure,
                descriptors=aspirin_descriptors,
                molecular_formula="WRONG",
                structure_status=StructureStatus.DISCLOSED,
                originating_org_id=org_id,
            )

    def test_tombstone_immutability(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.mark_as_tombstone(
            merged_into_id=uuid.uuid4(),
            merge_event_id=uuid.uuid4(),
            reason="Duplicate",
        )
        with pytest.raises(ValidationError, match="tombstone"):
            mol.update_tags(added=["new_tag"])

    def test_tombstone_cannot_be_merged_again(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.mark_as_tombstone(
            merged_into_id=uuid.uuid4(),
            merge_event_id=uuid.uuid4(),
            reason="Dup",
        )
        with pytest.raises(ValidationError, match="tombstone"):
            mol.mark_as_tombstone(
                merged_into_id=uuid.uuid4(),
                merge_event_id=uuid.uuid4(),
                reason="Again",
            )

    def test_cannot_merge_into_self(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        with pytest.raises(ValidationError, match="cannot be merged into itself"):
            mol.mark_as_tombstone(
                merged_into_id=mol.id,
                merge_event_id=uuid.uuid4(),
                reason="Self merge",
            )

    def test_mixture_without_enough_components(
        self, ws_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        mol = Molecule.register_undisclosed(
            workspace_id=ws_id,
            registration_number=RegistrationNumber(value="CV-00003"),
            name="Salt Form",
            molecule_type=MoleculeType.MIXTURE,
            originating_org_id=org_id,
        )
        mol.add_mixture_component(
            MixtureComponent.create(
                mixture_molecule_id=mol.id,
                component_molecule_id=uuid.uuid4(),
                stoichiometric_ratio=1.0,
                role=ComponentRole.ACTIVE,
            )
        )
        with pytest.raises(ValidationError, match="at least 2 components"):
            mol.validate_mixture_composition()

    def test_mixture_with_enough_components_passes(
        self, ws_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        mol = Molecule.register_undisclosed(
            workspace_id=ws_id,
            registration_number=RegistrationNumber(value="CV-00003"),
            name="Salt Form",
            molecule_type=MoleculeType.MIXTURE,
            originating_org_id=org_id,
        )
        mol.add_mixture_component(
            MixtureComponent.create(
                mixture_molecule_id=mol.id,
                component_molecule_id=uuid.uuid4(),
                stoichiometric_ratio=1.0,
                role=ComponentRole.ACTIVE,
            )
        )
        mol.add_mixture_component(
            MixtureComponent.create(
                mixture_molecule_id=mol.id,
                component_molecule_id=uuid.uuid4(),
                stoichiometric_ratio=1.0,
                role=ComponentRole.COUNTERION,
            )
        )
        mol.validate_mixture_composition()  # should not raise

    def test_non_mixture_cannot_add_component(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        with pytest.raises(ValidationError, match="Only mixture"):
            mol.add_mixture_component(
                MixtureComponent.create(
                    mixture_molecule_id=mol.id,
                    component_molecule_id=uuid.uuid4(),
                    stoichiometric_ratio=1.0,
                    role=ComponentRole.ACTIVE,
                )
            )


# ---------------------------------------------------------------------------
# Disclosure
# ---------------------------------------------------------------------------


class TestDisclose:
    def test_disclose_undisclosed_molecule(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.clear_events()
        mol.disclose(
            structure=aspirin_structure,
            descriptors=aspirin_descriptors,
            disclosed_by=user_id,
        )
        assert mol.structure_status == StructureStatus.DISCLOSED
        assert mol.structure == aspirin_structure
        assert mol.descriptors == aspirin_descriptors
        assert mol.molecular_formula == "C9H8O4"
        assert mol.disclosed_by == user_id
        assert mol.disclosed_at is not None

    def test_disclose_emits_event(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.clear_events()
        mol.disclose(
            structure=aspirin_structure,
            descriptors=aspirin_descriptors,
            disclosed_by=user_id,
        )
        events = mol.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MoleculeDisclosed)
        assert events[0].inchi_key == aspirin_structure.inchi_key

    def test_cannot_disclose_already_disclosed(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        with pytest.raises(ValidationError, match="Only undisclosed"):
            mol.disclose(
                structure=aspirin_structure,
                descriptors=aspirin_descriptors,
                disclosed_by=user_id,
            )

    def test_cannot_disclose_tombstone(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.mark_as_tombstone(
            merged_into_id=uuid.uuid4(),
            merge_event_id=uuid.uuid4(),
            reason="Dup",
        )
        with pytest.raises(ValidationError, match="tombstone"):
            mol.disclose(
                structure=aspirin_structure,
                descriptors=aspirin_descriptors,
                disclosed_by=user_id,
            )

    def test_disclose_records_stereochemistry(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.clear_events()
        mol.disclose(
            structure=aspirin_structure,
            descriptors=aspirin_descriptors,
            disclosed_by=user_id,
            stereochemistry=Stereochemistry.ACHIRAL,
        )
        assert mol.stereochemistry == Stereochemistry.ACHIRAL


# ---------------------------------------------------------------------------
# Registration status transitions
# ---------------------------------------------------------------------------


class TestRegistrationStatus:
    def test_approve_from_pending(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(
            ws_id, org_id, aspirin_structure, aspirin_descriptors,
            registration_status=RegistrationStatus.PENDING_REVIEW,
        )
        mol.approve()
        assert mol.registration_status == RegistrationStatus.APPROVED

    def test_reject_from_pending(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(
            ws_id, org_id, aspirin_structure, aspirin_descriptors,
            registration_status=RegistrationStatus.PENDING_REVIEW,
        )
        mol.reject()
        assert mol.registration_status == RegistrationStatus.REJECTED

    def test_resubmit_from_rejected(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(
            ws_id, org_id, aspirin_structure, aspirin_descriptors,
            registration_status=RegistrationStatus.PENDING_REVIEW,
        )
        mol.reject()
        mol.resubmit()
        assert mol.registration_status == RegistrationStatus.PENDING_REVIEW

    def test_cannot_approve_already_approved(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        assert mol.registration_status == RegistrationStatus.APPROVED
        with pytest.raises(ValidationError, match="Cannot transition"):
            mol.approve()

    def test_cannot_reject_approved(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        with pytest.raises(ValidationError, match="Cannot transition"):
            mol.reject()


# ---------------------------------------------------------------------------
# Synthesis status transitions
# ---------------------------------------------------------------------------


class TestSynthesisStatus:
    def test_virtual_to_designed(self, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.advance_synthesis(SynthesisStatus.DESIGNED)
        assert mol.synthesis_status == SynthesisStatus.DESIGNED

    def test_virtual_to_synthesized(self, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.advance_synthesis(SynthesisStatus.SYNTHESIZED)
        assert mol.synthesis_status == SynthesisStatus.SYNTHESIZED

    def test_virtual_to_purchased(self, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.advance_synthesis(SynthesisStatus.PURCHASED)
        assert mol.synthesis_status == SynthesisStatus.PURCHASED

    def test_designed_to_synthesized(self, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
        mol = _make_undisclosed(ws_id, org_id)
        mol.advance_synthesis(SynthesisStatus.DESIGNED)
        mol.advance_synthesis(SynthesisStatus.SYNTHESIZED)
        assert mol.synthesis_status == SynthesisStatus.SYNTHESIZED

    def test_cannot_go_backwards(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        assert mol.synthesis_status == SynthesisStatus.SYNTHESIZED
        with pytest.raises(ValidationError, match="Cannot transition"):
            mol.advance_synthesis(SynthesisStatus.VIRTUAL)


# ---------------------------------------------------------------------------
# Lifecycle stage transitions
# ---------------------------------------------------------------------------


class TestLifecycleStage:
    def test_registered_to_active(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.clear_events()
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        assert mol.lifecycle_stage == LifecycleStage.ACTIVE
        events = mol.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MoleculeLifecycleChanged)
        assert events[0].old_stage == "registered"
        assert events[0].new_stage == "active"

    def test_active_to_hit(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        mol.advance_lifecycle(LifecycleStage.HIT, changed_by=user_id)
        assert mol.lifecycle_stage == LifecycleStage.HIT

    def test_full_progression(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        mol.advance_lifecycle(LifecycleStage.HIT, changed_by=user_id)
        mol.advance_lifecycle(LifecycleStage.LEAD, changed_by=user_id)
        mol.advance_lifecycle(LifecycleStage.PRECLINICAL_CANDIDATE, changed_by=user_id)
        mol.advance_lifecycle(LifecycleStage.DEVELOPMENT_CANDIDATE, changed_by=user_id)
        assert mol.lifecycle_stage == LifecycleStage.DEVELOPMENT_CANDIDATE

    def test_deprioritize_requires_reason(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        with pytest.raises(ValidationError, match="Reason is required"):
            mol.advance_lifecycle(LifecycleStage.DEPRIORITIZED, changed_by=user_id)

    def test_deprioritize_with_reason(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        mol.advance_lifecycle(
            LifecycleStage.DEPRIORITIZED, changed_by=user_id, reason="Toxicity"
        )
        assert mol.lifecycle_stage == LifecycleStage.DEPRIORITIZED

    def test_reactivate_from_deprioritized(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        mol.advance_lifecycle(
            LifecycleStage.DEPRIORITIZED, changed_by=user_id, reason="Toxicity"
        )
        mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)
        assert mol.lifecycle_stage == LifecycleStage.ACTIVE

    def test_archived_is_terminal(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.advance_lifecycle(
            LifecycleStage.ARCHIVED, changed_by=user_id, reason="Retired"
        )
        with pytest.raises(ValidationError, match="Cannot transition"):
            mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)

    def test_invalid_transition_raises(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        with pytest.raises(ValidationError, match="Cannot transition"):
            mol.advance_lifecycle(LifecycleStage.LEAD, changed_by=user_id)


# ---------------------------------------------------------------------------
# Tombstone / merge
# ---------------------------------------------------------------------------


class TestTombstone:
    def test_mark_as_tombstone(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        target_id = uuid.uuid4()
        merge_event_id = uuid.uuid4()
        mol.clear_events()
        mol.mark_as_tombstone(
            merged_into_id=target_id,
            merge_event_id=merge_event_id,
            reason="Duplicate InChIKey",
        )
        assert mol.is_tombstone
        assert mol.merged_into_id == target_id
        events = mol.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MoleculeMerged)
        assert events[0].source_molecule_id == mol.id
        assert events[0].target_molecule_id == target_id
        assert events[0].merge_event_id == merge_event_id

    def test_tombstone_blocks_all_mutations(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.mark_as_tombstone(
            merged_into_id=uuid.uuid4(),
            merge_event_id=uuid.uuid4(),
            reason="Dup",
        )

        with pytest.raises(ValidationError, match="tombstone"):
            mol.approve()

        with pytest.raises(ValidationError, match="tombstone"):
            mol.advance_synthesis(SynthesisStatus.PURCHASED)

        with pytest.raises(ValidationError, match="tombstone"):
            mol.advance_lifecycle(LifecycleStage.ACTIVE, changed_by=user_id)

        with pytest.raises(ValidationError, match="tombstone"):
            mol.update_predicted_properties(
                PredictedProperties(logd=1.0, prediction_source="test")
            )

        with pytest.raises(ValidationError, match="tombstone"):
            mol.update_custom_fields({"key": "value"})

        with pytest.raises(ValidationError, match="tombstone"):
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier="CAS-123",
                    identifier_type=IdentifierType.CAS_NUMBER,
                    source="test",
                    registered_by=user_id,
                )
            )


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TestTags:
    def test_update_tags_add(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.clear_events()
        mol.update_tags(added=["probe", "backup"])
        assert "probe" in mol.tags
        assert "backup" in mol.tags

    def test_update_tags_remove(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(
            ws_id, org_id, aspirin_structure, aspirin_descriptors, tags=["probe", "old"]
        )
        mol.update_tags(removed=["old"])
        assert "old" not in mol.tags
        assert "probe" in mol.tags

    def test_update_tags_emits_event(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.clear_events()
        mol.update_tags(added=["new"], removed=["old"])
        events = mol.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MoleculeTagsUpdated)
        assert events[0].added_tags == ("new",)
        assert events[0].removed_tags == ("old",)

    def test_no_duplicate_tags(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(
            ws_id, org_id, aspirin_structure, aspirin_descriptors, tags=["probe"]
        )
        mol.update_tags(added=["probe"])
        assert mol.tags.count("probe") == 1


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


class TestIdentifiers:
    def test_add_identifier(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        ident = MoleculeIdentifier.create(
            molecule_id=mol.id,
            identifier="CAS-50-78-2",
            identifier_type=IdentifierType.CAS_NUMBER,
            source="User registration",
            registered_by=user_id,
        )
        mol.add_identifier(ident)
        assert len(mol.identifiers) == 1
        assert mol.identifiers[0].identifier == "CAS-50-78-2"


# ---------------------------------------------------------------------------
# Predicted properties
# ---------------------------------------------------------------------------


class TestPredictedProperties:
    def test_update_predicted_properties(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        props = PredictedProperties(logd=1.5, prediction_source="ChemAxon 24.3")
        mol.update_predicted_properties(props)
        assert mol.predicted_properties == props


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


class TestCustomFields:
    def test_update_custom_fields(
        self,
        ws_id: uuid.UUID,
        org_id: uuid.UUID,
        aspirin_structure: ChemicalStructure,
        aspirin_descriptors: ComputedDescriptors,
    ) -> None:
        mol = _make_disclosed(ws_id, org_id, aspirin_structure, aspirin_descriptors)
        mol.update_custom_fields({"project": "oncology", "priority": "high"})
        assert mol.custom_fields == {"project": "oncology", "priority": "high"}
