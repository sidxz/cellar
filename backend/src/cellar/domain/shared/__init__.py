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
    "AggregateRoot",
    # Value Objects
    "Amount",
    # Enums
    "AmountUnit",
    "AssignmentType",
    "AuthorizationError",
    "Barcode",
    "BatchNumber",
    "ChemicalStructure",
    "ComputedDescriptors",
    "Concentration",
    "ConcentrationUnit",
    "ConcurrencyConflictError",
    "ConflictError",
    "DataLockedError",
    # Errors
    "DomainError",
    # Events
    "DomainEvent",
    # Entity
    "Entity",
    "FormulationNumber",
    "LightCondition",
    "LinkedEntityRef",
    "LinkedEntityType",
    "NotFoundError",
    "PredictedProperties",
    "QualifiedValue",
    "Qualifier",
    "ReactionConditions",
    "ReactionOutcome",
    "RegistrationNumber",
    # Repository
    "Repository",
    "StorageCondition",
    "SynthesisAssignment",
    "ValidationError",
]
