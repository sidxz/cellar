"""MixtureComponent — owned entity linking component molecules to a mixture."""

from __future__ import annotations

import uuid
from datetime import datetime

from chem_vault.domain.chemical_registration.enums import ComponentRole
from chem_vault.domain.shared.entity import Entity
from chem_vault.domain.shared.errors import ValidationError


class MixtureComponent(Entity):
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
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        if stoichiometric_ratio <= 0:
            raise ValidationError("Stoichiometric ratio must be positive")
        if mixture_molecule_id == component_molecule_id:
            raise ValidationError("A mixture cannot contain itself as a component")
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
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
