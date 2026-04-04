"""Molecule aggregate root — the central entity of chemical registration."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from chem_vault.domain.chemical_registration.enums import (
    LifecycleStage,
    MoleculeType,
    RegistrationStatus,
    Stereochemistry,
    StructureStatus,
    SynthesisStatus,
)
from chem_vault.domain.chemical_registration.events import (
    MoleculeDisclosed,
    MoleculeLifecycleChanged,
    MoleculeMerged,
    MoleculeRegistered,
    MoleculeTagsUpdated,
)
from chem_vault.domain.chemical_registration.mixture_component import MixtureComponent
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    PredictedProperties,
    RegistrationNumber,
)

# ---------------------------------------------------------------------------
# State-machine transition tables
# ---------------------------------------------------------------------------

_REGISTRATION_TRANSITIONS: dict[RegistrationStatus, set[RegistrationStatus]] = {
    RegistrationStatus.PENDING_REVIEW: {RegistrationStatus.APPROVED, RegistrationStatus.REJECTED},
    RegistrationStatus.APPROVED: set(),
    RegistrationStatus.REJECTED: {RegistrationStatus.PENDING_REVIEW},
}

_SYNTHESIS_TRANSITIONS: dict[SynthesisStatus, set[SynthesisStatus]] = {
    SynthesisStatus.VIRTUAL: {SynthesisStatus.DESIGNED, SynthesisStatus.SYNTHESIZED, SynthesisStatus.PURCHASED},
    SynthesisStatus.DESIGNED: {SynthesisStatus.SYNTHESIZED, SynthesisStatus.PURCHASED},
    SynthesisStatus.SYNTHESIZED: set(),
    SynthesisStatus.PURCHASED: set(),
}

_LIFECYCLE_TRANSITIONS: dict[LifecycleStage, set[LifecycleStage]] = {
    LifecycleStage.REGISTERED: {LifecycleStage.ACTIVE, LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED},
    LifecycleStage.ACTIVE: {
        LifecycleStage.HIT, LifecycleStage.LEAD,
        LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED,
    },
    LifecycleStage.HIT: {
        LifecycleStage.LEAD, LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED,
    },
    LifecycleStage.LEAD: {
        LifecycleStage.PRECLINICAL_CANDIDATE, LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED,
    },
    LifecycleStage.PRECLINICAL_CANDIDATE: {
        LifecycleStage.DEVELOPMENT_CANDIDATE, LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED,
    },
    LifecycleStage.DEVELOPMENT_CANDIDATE: {LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED},
    LifecycleStage.DEPRIORITIZED: {LifecycleStage.ACTIVE},
    LifecycleStage.ARCHIVED: set(),
}


class Molecule(AggregateRoot):
    """A unique chemical structure (or undisclosed placeholder) within a workspace.

    Aggregate root with owned entities: MoleculeIdentifier[], MixtureComponent[].
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        registration_number: RegistrationNumber,
        name: str,
        molecule_type: MoleculeType,
        structure: ChemicalStructure | None = None,
        descriptors: ComputedDescriptors | None = None,
        predicted_properties: PredictedProperties | None = None,
        molecular_formula: str | None = None,
        structure_image_key: str | None = None,
        sequence: str | None = None,
        stereochemistry: Stereochemistry | None = None,
        structure_status: StructureStatus = StructureStatus.DISCLOSED,
        registration_status: RegistrationStatus = RegistrationStatus.APPROVED,
        synthesis_status: SynthesisStatus = SynthesisStatus.SYNTHESIZED,
        lifecycle_stage: LifecycleStage = LifecycleStage.REGISTERED,
        tags: list[str] | None = None,
        invention_date: date | None = None,
        disclosed_at: datetime | None = None,
        disclosed_by: uuid.UUID | None = None,
        merged_into_id: uuid.UUID | None = None,
        custom_fields: dict[str, Any] | None = None,
        originating_org_id: uuid.UUID,
        identifiers: list[MoleculeIdentifier] | None = None,
        mixture_components: list[MixtureComponent] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Molecule name must not be empty")

        self.workspace_id = workspace_id
        self.registration_number = registration_number
        self.name = name.strip()
        self.molecule_type = molecule_type
        self.structure = structure
        self.descriptors = descriptors
        self.predicted_properties = predicted_properties
        self.molecular_formula = molecular_formula
        self.structure_image_key = structure_image_key
        self.sequence = sequence
        self.stereochemistry = stereochemistry
        self.structure_status = structure_status
        self.registration_status = registration_status
        self.synthesis_status = synthesis_status
        self.lifecycle_stage = lifecycle_stage
        self.tags: list[str] = list(tags) if tags else []
        self.invention_date = invention_date
        self.disclosed_at = disclosed_at
        self.disclosed_by = disclosed_by
        self.merged_into_id = merged_into_id
        self.custom_fields = dict(custom_fields) if custom_fields else None
        self.originating_org_id = originating_org_id
        self.identifiers: list[MoleculeIdentifier] = list(identifiers) if identifiers else []
        self.mixture_components: list[MixtureComponent] = list(mixture_components) if mixture_components else []

        self._validate_structure_consistency()
        self._validate_molecular_formula_sync()

    # ------------------------------------------------------------------
    # Invariant validators
    # ------------------------------------------------------------------

    def _validate_structure_consistency(self) -> None:
        """Invariant 1 & 2: structure + descriptors follow structure_status."""
        if self.structure_status == StructureStatus.DISCLOSED:
            if self.structure is None:
                raise ValidationError("Disclosed molecule must have a structure")
            if self.descriptors is None:
                raise ValidationError("Disclosed molecule must have computed descriptors")
        else:
            if self.structure is not None:
                raise ValidationError("Undisclosed molecule must not have a structure")
            if self.descriptors is not None:
                raise ValidationError("Undisclosed molecule must not have computed descriptors")

    def _validate_molecular_formula_sync(self) -> None:
        """Sync invariant: molecular_formula must match descriptors when both set."""
        if self.descriptors is not None and self.molecular_formula is not None:
            if self.molecular_formula != self.descriptors.molecular_formula:
                raise ValidationError(
                    f"molecular_formula '{self.molecular_formula}' does not match "
                    f"descriptors.molecular_formula '{self.descriptors.molecular_formula}'"
                )

    def _guard_tombstone(self) -> None:
        """Invariant 4: tombstones are immutable."""
        if self.merged_into_id is not None:
            raise ValidationError("Cannot mutate a tombstone molecule")

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def register_disclosed(
        cls,
        *,
        workspace_id: uuid.UUID,
        registration_number: RegistrationNumber,
        name: str,
        molecule_type: MoleculeType,
        structure: ChemicalStructure,
        descriptors: ComputedDescriptors,
        originating_org_id: uuid.UUID,
        molecular_formula: str | None = None,
        stereochemistry: Stereochemistry | None = None,
        sequence: str | None = None,
        registration_status: RegistrationStatus = RegistrationStatus.APPROVED,
        synthesis_status: SynthesisStatus = SynthesisStatus.SYNTHESIZED,
        tags: list[str] | None = None,
        invention_date: date | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Molecule:
        mol = cls(
            workspace_id=workspace_id,
            registration_number=registration_number,
            name=name,
            molecule_type=molecule_type,
            structure=structure,
            descriptors=descriptors,
            originating_org_id=originating_org_id,
            molecular_formula=molecular_formula or descriptors.molecular_formula,
            stereochemistry=stereochemistry,
            sequence=sequence,
            structure_status=StructureStatus.DISCLOSED,
            registration_status=registration_status,
            synthesis_status=synthesis_status,
            tags=tags,
            invention_date=invention_date,
            custom_fields=custom_fields,
        )
        mol.register_event(
            MoleculeRegistered(
                aggregate_id=mol.id,
                aggregate_type="Molecule",
                registration_number=registration_number.value,
                molecule_type=molecule_type.value,
                workspace_id=workspace_id,
                originating_org_id=originating_org_id,
            )
        )
        return mol

    @classmethod
    def register_undisclosed(
        cls,
        *,
        workspace_id: uuid.UUID,
        registration_number: RegistrationNumber,
        name: str,
        molecule_type: MoleculeType,
        originating_org_id: uuid.UUID,
        sequence: str | None = None,
        registration_status: RegistrationStatus = RegistrationStatus.APPROVED,
        synthesis_status: SynthesisStatus = SynthesisStatus.VIRTUAL,
        tags: list[str] | None = None,
        invention_date: date | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> Molecule:
        mol = cls(
            workspace_id=workspace_id,
            registration_number=registration_number,
            name=name,
            molecule_type=molecule_type,
            originating_org_id=originating_org_id,
            structure=None,
            descriptors=None,
            molecular_formula=None,
            sequence=sequence,
            structure_status=StructureStatus.UNDISCLOSED,
            registration_status=registration_status,
            synthesis_status=synthesis_status,
            tags=tags,
            invention_date=invention_date,
            custom_fields=custom_fields,
        )
        mol.register_event(
            MoleculeRegistered(
                aggregate_id=mol.id,
                aggregate_type="Molecule",
                registration_number=registration_number.value,
                molecule_type=molecule_type.value,
                workspace_id=workspace_id,
                originating_org_id=originating_org_id,
            )
        )
        return mol

    # ------------------------------------------------------------------
    # State transitions — structure_status
    # ------------------------------------------------------------------

    def disclose(
        self,
        *,
        structure: ChemicalStructure,
        descriptors: ComputedDescriptors,
        disclosed_by: uuid.UUID,
        molecular_formula: str | None = None,
    ) -> None:
        """Transition undisclosed -> disclosed."""
        self._guard_tombstone()
        if self.structure_status != StructureStatus.UNDISCLOSED:
            raise ValidationError("Only undisclosed molecules can be disclosed")

        self.structure = structure
        self.descriptors = descriptors
        self.molecular_formula = molecular_formula or descriptors.molecular_formula
        self.structure_status = StructureStatus.DISCLOSED
        self.disclosed_at = datetime.now(UTC)
        self.disclosed_by = disclosed_by
        self.updated_at = datetime.now(UTC)

        self._validate_structure_consistency()
        self._validate_molecular_formula_sync()

        self.register_event(
            MoleculeDisclosed(
                aggregate_id=self.id,
                aggregate_type="Molecule",
                inchi_key=structure.inchi_key,  # type: ignore[arg-type]
            )
        )

    # ------------------------------------------------------------------
    # State transitions — registration_status
    # ------------------------------------------------------------------

    def approve(self) -> None:
        self._guard_tombstone()
        self._transition_registration(RegistrationStatus.APPROVED)

    def reject(self) -> None:
        self._guard_tombstone()
        self._transition_registration(RegistrationStatus.REJECTED)

    def resubmit(self) -> None:
        self._guard_tombstone()
        self._transition_registration(RegistrationStatus.PENDING_REVIEW)

    def _transition_registration(self, target: RegistrationStatus) -> None:
        allowed = _REGISTRATION_TRANSITIONS.get(self.registration_status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition registration_status from "
                f"'{self.registration_status}' to '{target}'"
            )
        self.registration_status = target
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # State transitions — synthesis_status
    # ------------------------------------------------------------------

    def advance_synthesis(self, target: SynthesisStatus) -> None:
        self._guard_tombstone()
        allowed = _SYNTHESIS_TRANSITIONS.get(self.synthesis_status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition synthesis_status from "
                f"'{self.synthesis_status}' to '{target}'"
            )
        self.synthesis_status = target
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # State transitions — lifecycle_stage
    # ------------------------------------------------------------------

    def advance_lifecycle(
        self,
        target: LifecycleStage,
        *,
        changed_by: uuid.UUID,
        reason: str | None = None,
    ) -> None:
        self._guard_tombstone()
        allowed = _LIFECYCLE_TRANSITIONS.get(self.lifecycle_stage, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition lifecycle_stage from "
                f"'{self.lifecycle_stage}' to '{target}'"
            )
        if target in (LifecycleStage.DEPRIORITIZED, LifecycleStage.ARCHIVED) and not reason:
            raise ValidationError(
                f"Reason is required when transitioning to '{target}'"
            )
        old_stage = self.lifecycle_stage
        self.lifecycle_stage = target
        self.updated_at = datetime.now(UTC)
        self.register_event(
            MoleculeLifecycleChanged(
                aggregate_id=self.id,
                aggregate_type="Molecule",
                old_stage=old_stage.value,
                new_stage=target.value,
                changed_by=changed_by,
                reason=reason,
            )
        )

    # ------------------------------------------------------------------
    # Tombstone / merge
    # ------------------------------------------------------------------

    def mark_as_tombstone(
        self,
        *,
        merged_into_id: uuid.UUID,
        merge_event_id: uuid.UUID,
        reason: str,
    ) -> None:
        self._guard_tombstone()
        if merged_into_id == self.id:
            raise ValidationError("A molecule cannot be merged into itself")
        self.merged_into_id = merged_into_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            MoleculeMerged(
                aggregate_id=self.id,
                aggregate_type="Molecule",
                source_molecule_id=self.id,
                target_molecule_id=merged_into_id,
                merge_event_id=merge_event_id,
                reason=reason,
            )
        )

    @property
    def is_tombstone(self) -> bool:
        return self.merged_into_id is not None

    # ------------------------------------------------------------------
    # Mutations — tags
    # ------------------------------------------------------------------

    def update_tags(
        self, *, added: list[str] | None = None, removed: list[str] | None = None
    ) -> None:
        self._guard_tombstone()
        added = added or []
        removed = removed or []
        for tag in removed:
            if tag in self.tags:
                self.tags.remove(tag)
        for tag in added:
            if tag not in self.tags:
                self.tags.append(tag)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            MoleculeTagsUpdated(
                aggregate_id=self.id,
                aggregate_type="Molecule",
                added_tags=tuple(added),
                removed_tags=tuple(removed),
            )
        )

    # ------------------------------------------------------------------
    # Mutations — predicted properties
    # ------------------------------------------------------------------

    def update_predicted_properties(self, props: PredictedProperties) -> None:
        self._guard_tombstone()
        self.predicted_properties = props
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Mutations — custom fields
    # ------------------------------------------------------------------

    def update_custom_fields(self, fields: dict[str, Any]) -> None:
        self._guard_tombstone()
        self.custom_fields = dict(fields)
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Mutations — identifiers
    # ------------------------------------------------------------------

    def add_identifier(self, identifier: MoleculeIdentifier) -> None:
        self._guard_tombstone()
        self.identifiers.append(identifier)
        self.updated_at = datetime.now(UTC)

    def remove_identifier(self, identifier_id: uuid.UUID) -> None:
        """Remove an identifier by ID."""
        self._guard_tombstone()
        original_count = len(self.identifiers)
        self.identifiers = [i for i in self.identifiers if i.id != identifier_id]
        if len(self.identifiers) == original_count:
            raise ValidationError(f"Identifier {identifier_id} not found on this molecule")
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Mutations — mixture components
    # ------------------------------------------------------------------

    def add_mixture_component(self, component: MixtureComponent) -> None:
        self._guard_tombstone()
        if self.molecule_type != MoleculeType.MIXTURE:
            raise ValidationError("Only mixture molecules can have components")
        self.mixture_components.append(component)
        self.updated_at = datetime.now(UTC)

    def validate_mixture_composition(self) -> None:
        """Invariant 5: mixtures must have >= 2 components with positive ratios.

        Called at points of use (e.g. before save), not in __init__,
        because components are added incrementally.
        """
        if self.molecule_type == MoleculeType.MIXTURE and len(self.mixture_components) < 2:
            raise ValidationError(
                "Mixture molecules must have at least 2 components"
            )
