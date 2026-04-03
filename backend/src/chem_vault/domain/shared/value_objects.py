"""Shared value objects — immutable, equality by value.

All VOs use ``model_config = ConfigDict(frozen=True)`` and validate
invariants via Pydantic field/model validators.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from chem_vault.domain.shared.enums import (
    AmountUnit,
    AssignmentType,
    ConcentrationUnit,
    LightCondition,
    LinkedEntityType,
    Qualifier,
)

_INCHI_KEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


class _FrozenModel(BaseModel):
    """Base for all value objects."""

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Chemical structure VOs
# ---------------------------------------------------------------------------


class ChemicalStructure(_FrozenModel):
    """Structural representations of a molecule.

    All-null (undisclosed) or all-populated (disclosed). No partial state.
    Equality is by ``inchi_key``.
    """

    smiles: str | None = None
    cxsmiles: str | None = None
    inchi: str | None = None
    inchi_key: str | None = None
    molfile: str | None = None

    @model_validator(mode="after")
    def _all_or_nothing(self) -> ChemicalStructure:
        fields = [self.smiles, self.cxsmiles, self.inchi, self.inchi_key, self.molfile]
        populated = [f is not None for f in fields]
        if any(populated) and not all(populated):
            raise ValueError("ChemicalStructure must be all-null or all-populated")
        return self

    @field_validator("inchi_key")
    @classmethod
    def _validate_inchi_key(cls, v: str | None) -> str | None:
        if v is not None and not _INCHI_KEY_RE.match(v):
            raise ValueError(
                f"InChIKey must match XXXXXXXXXXXXXX-XXXXXXXXXX-X, got '{v}'"
            )
        return v

    @property
    def is_disclosed(self) -> bool:
        return self.smiles is not None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChemicalStructure):
            return NotImplemented
        return self.inchi_key == other.inchi_key

    def __hash__(self) -> int:
        return hash(self.inchi_key)


class ComputedDescriptors(_FrozenModel):
    """Deterministic molecular descriptors computed via RDKit.

    All-null or all-populated — tied to ``ChemicalStructure`` lifecycle.
    """

    molecular_formula: str | None = None
    molecular_weight: float | None = None
    exact_mass: float | None = None
    logp: float | None = None
    tpsa: float | None = None
    hbd: int | None = None
    hba: int | None = None
    rotatable_bonds: int | None = None
    aromatic_rings: int | None = None
    ring_count: int | None = None
    heavy_atom_count: int | None = None
    ro5_violations: int | None = None

    @model_validator(mode="after")
    def _all_or_nothing(self) -> ComputedDescriptors:
        fields = [
            self.molecular_formula,
            self.molecular_weight,
            self.exact_mass,
            self.logp,
            self.tpsa,
            self.hbd,
            self.hba,
            self.rotatable_bonds,
            self.aromatic_rings,
            self.ring_count,
            self.heavy_atom_count,
            self.ro5_violations,
        ]
        populated = [f is not None for f in fields]
        if any(populated) and not all(populated):
            raise ValueError("ComputedDescriptors must be all-null or all-populated")
        return self

    @field_validator("molecular_weight")
    @classmethod
    def _mw_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("molecular_weight must be positive")
        return v

    @field_validator("ro5_violations")
    @classmethod
    def _ro5_range(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 4):
            raise ValueError("ro5_violations must be in range [0, 4]")
        return v

    @field_validator(
        "hbd", "hba", "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count"
    )
    @classmethod
    def _non_negative_int(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("Count fields must be non-negative")
        return v


class PredictedProperties(_FrozenModel):
    """Properties from external prediction services. Individually nullable."""

    logd: float | None = None
    pka: float | None = None
    logs: float | None = None
    prediction_source: str | None = None
    predicted_at: datetime | None = None

    @model_validator(mode="after")
    def _source_requires_property(self) -> PredictedProperties:
        if self.prediction_source is not None:
            if all(v is None for v in (self.logd, self.pka, self.logs)):
                raise ValueError(
                    "prediction_source requires at least one predicted property"
                )
        return self


# ---------------------------------------------------------------------------
# Registration / identification VOs
# ---------------------------------------------------------------------------


class RegistrationNumber(_FrozenModel):
    """Immutable human-readable compound identifier (e.g., CV-00001)."""

    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("RegistrationNumber cannot be empty")
        return v


class BatchNumber(_FrozenModel):
    """Sequential batch identifier (e.g., CV-00001-001)."""

    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("BatchNumber cannot be empty")
        return v


class Barcode(_FrozenModel):
    """Physical barcode identifier for samples, plates, or storage locations."""

    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Barcode cannot be empty")
        return v


class FormulationNumber(_FrozenModel):
    """Immutable formulation identifier (e.g., FRM-00001)."""

    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("FormulationNumber cannot be empty")
        return v


# ---------------------------------------------------------------------------
# Measurement VOs
# ---------------------------------------------------------------------------


class Amount(_FrozenModel):
    """Quantity of material with unit."""

    value: float
    unit: AmountUnit

    @field_validator("value")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Amount value must be >= 0")
        return v


class Concentration(_FrozenModel):
    """Solution concentration with unit."""

    value: float
    unit: ConcentrationUnit

    @field_validator("value")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Concentration value must be > 0")
        return v


class QualifiedValue(_FrozenModel):
    """Numeric measurement with qualifier (e.g., IC50 > 10000 nM)."""

    value: float
    qualifier: Qualifier = Qualifier.EQUAL


# ---------------------------------------------------------------------------
# Synthesis VOs
# ---------------------------------------------------------------------------


class ReactionConditions(_FrozenModel):
    """Experimental conditions for a reaction step."""

    solvent: str | None = None
    temperature: str | None = None
    pressure: str | None = None
    catalyst: str | None = None
    atmosphere: str | None = None
    time: str | None = None
    additional_conditions: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> ReactionConditions:
        fields = [
            self.solvent,
            self.temperature,
            self.pressure,
            self.catalyst,
            self.atmosphere,
            self.time,
            self.additional_conditions,
        ]
        if all(f is None for f in fields):
            raise ValueError("ReactionConditions must have at least one field set")
        return self


class ReactionOutcome(_FrozenModel):
    """Results of executing a reaction step."""

    yield_percent: float | None = None
    crude_yield_percent: float | None = None
    purity_percent: float | None = None
    actual_scale: Amount | None = None
    purification_method: str | None = None

    @field_validator("yield_percent", "crude_yield_percent", "purity_percent")
    @classmethod
    def _percent_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 < v <= 100):
            raise ValueError("Percent values must be in (0, 100]")
        return v


class SynthesisAssignment(_FrozenModel):
    """Who is performing a synthesis — internal chemist or external CRO."""

    assignment_type: AssignmentType
    assigned_to: uuid.UUID | None = None
    assigned_org_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_assignment(self) -> SynthesisAssignment:
        if self.assignment_type == AssignmentType.INTERNAL and self.assigned_to is None:
            raise ValueError("Internal assignment requires assigned_to (user ID)")
        if self.assignment_type == AssignmentType.CRO and self.assigned_org_id is None:
            raise ValueError("CRO assignment requires assigned_org_id")
        return self


# ---------------------------------------------------------------------------
# Cross-context VOs
# ---------------------------------------------------------------------------


class LinkedEntityRef(_FrozenModel):
    """Generic cross-context reference for ELN entries."""

    entity_type: LinkedEntityType
    entity_id: uuid.UUID


class StorageCondition(_FrozenModel):
    """ICH-aligned stability study storage conditions."""

    temperature_celsius: float
    relative_humidity_percent: float | None = None
    light_condition: LightCondition | None = None

    @field_validator("relative_humidity_percent")
    @classmethod
    def _humidity_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("relative_humidity_percent must be in [0, 100]")
        return v
