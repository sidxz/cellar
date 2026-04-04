"""MixtureComponent — owned entity linking component molecules to a mixture."""

from __future__ import annotations

import uuid

from chem_vault.domain.chemical_registration.enums import ComponentRole
from chem_vault.domain.shared.errors import ValidationError


class MixtureComponent:
    """A component within a mixture molecule.

    Fully owned by the parent Molecule aggregate (which must have molecule_type = mixture).
    The component_molecule_id references a separate Molecule aggregate by ID.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        mixture_molecule_id: uuid.UUID,
        component_molecule_id: uuid.UUID,
        stoichiometric_ratio: float,
        role: ComponentRole,
    ) -> None:
        if stoichiometric_ratio <= 0:
            raise ValidationError("Stoichiometric ratio must be positive")
        if mixture_molecule_id == component_molecule_id:
            raise ValidationError("A mixture cannot contain itself as a component")
        self.id = id or uuid.uuid4()
        self.mixture_molecule_id = mixture_molecule_id
        self.component_molecule_id = component_molecule_id
        self.stoichiometric_ratio = stoichiometric_ratio
        self.role = role

    @classmethod
    def create(
        cls,
        *,
        mixture_molecule_id: uuid.UUID,
        component_molecule_id: uuid.UUID,
        stoichiometric_ratio: float,
        role: ComponentRole,
    ) -> MixtureComponent:
        return cls(
            mixture_molecule_id=mixture_molecule_id,
            component_molecule_id=component_molecule_id,
            stoichiometric_ratio=stoichiometric_ratio,
            role=role,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MixtureComponent):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return (
            f"MixtureComponent(id={self.id}, "
            f"component={self.component_molecule_id}, ratio={self.stoichiometric_ratio})"
        )
