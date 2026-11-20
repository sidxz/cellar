"""Tests for MixtureComponent owned entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import ComponentRole
from cellar.domain.chemical_registration.mixture_component import MixtureComponent
from cellar.domain.shared.errors import ValidationError


class TestMixtureComponent:
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
