"""Tests for MixtureComponent owned entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import ComponentRole
from cellar.domain.chemical_registration.mixture_component import MixtureComponent
from cellar.domain.shared.errors import ValidationError


class TestMixtureComponent:
    def test_create(self) -> None:
        mixture_id = uuid.uuid4()
        component_id = uuid.uuid4()
        comp = MixtureComponent.create(
            mixture_molecule_id=mixture_id,
            component_molecule_id=component_id,
            stoichiometric_ratio=2.0,
            role=ComponentRole.ACTIVE,
        )
        assert comp.mixture_molecule_id == mixture_id
        assert comp.component_molecule_id == component_id
        assert comp.stoichiometric_ratio == 2.0
        assert comp.role == ComponentRole.ACTIVE
        assert comp.id is not None

    def test_zero_ratio_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            MixtureComponent.create(
                mixture_molecule_id=uuid.uuid4(),
                component_molecule_id=uuid.uuid4(),
                stoichiometric_ratio=0.0,
                role=ComponentRole.ACTIVE,
            )

    def test_negative_ratio_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            MixtureComponent.create(
                mixture_molecule_id=uuid.uuid4(),
                component_molecule_id=uuid.uuid4(),
                stoichiometric_ratio=-1.0,
                role=ComponentRole.ACTIVE,
            )

    def test_self_reference_raises(self) -> None:
        mol_id = uuid.uuid4()
        with pytest.raises(ValidationError, match="cannot contain itself"):
            MixtureComponent.create(
                mixture_molecule_id=mol_id,
                component_molecule_id=mol_id,
                stoichiometric_ratio=1.0,
                role=ComponentRole.ACTIVE,
            )

    def test_equality_by_id(self) -> None:
        shared_id = uuid.uuid4()
        a = MixtureComponent(
            id=shared_id,
            mixture_molecule_id=uuid.uuid4(),
            component_molecule_id=uuid.uuid4(),
            stoichiometric_ratio=1.0,
            role=ComponentRole.ACTIVE,
        )
        b = MixtureComponent(
            id=shared_id,
            mixture_molecule_id=uuid.uuid4(),
            component_molecule_id=uuid.uuid4(),
            stoichiometric_ratio=2.0,
            role=ComponentRole.COUNTERION,
        )
        assert a == b
