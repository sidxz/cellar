"""Shared kernel — base classes, value objects, errors, and enums."""

from cellar.domain.shared.entity import AggregateRoot, Entity
from cellar.domain.shared.enums import (
    AmountUnit,
    AssignmentType,
    ConcentrationUnit,
    LightCondition,
    LinkedEntityType,
    Qualifier,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConcurrencyConflictError,
    ConflictError,
    DataLockedError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.repository import Repository
from cellar.domain.shared.value_objects import (
    Amount,
    Barcode,
    BatchNumber,
    ChemicalStructure,
    ComputedDescriptors,
    Concentration,
    FormulationNumber,
    LinkedEntityRef,
    PredictedProperties,
    QualifiedValue,
    ReactionConditions,
    ReactionOutcome,
    RegistrationNumber,
    StorageCondition,
    SynthesisAssignment,
)

__all__ = [
    # Entity
    "Entity",
    "AggregateRoot",
    # Events
    "DomainEvent",
    # Errors
    "DomainError",
    "NotFoundError",
    "ConflictError",
    "ConcurrencyConflictError",
    "ValidationError",
    "AuthorizationError",
    "DataLockedError",
    # Repository
    "Repository",
    # Enums
    "AmountUnit",
    "AssignmentType",
    "ConcentrationUnit",
    "LightCondition",
    "LinkedEntityType",
    "Qualifier",
    # Value Objects
    "Amount",
    "Barcode",
    "BatchNumber",
    "ChemicalStructure",
    "Concentration",
    "ComputedDescriptors",
    "FormulationNumber",
    "LinkedEntityRef",
    "PredictedProperties",
    "QualifiedValue",
    "ReactionConditions",
    "ReactionOutcome",
    "RegistrationNumber",
    "StorageCondition",
    "SynthesisAssignment",
]
