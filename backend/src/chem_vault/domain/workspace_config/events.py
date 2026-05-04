"""Domain events for workspace configuration context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.workspace_config.enums import OrganizationType


@dataclass(frozen=True, kw_only=True)
class OrganizationCreated(DomainEvent):
    name: str
    org_type: OrganizationType


@dataclass(frozen=True, kw_only=True)
class OrganizationUpdated(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class OrganizationDeactivated(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class OrganizationActivated(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class WorkspaceSettingsUpdated(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class VocabularyCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class VocabularyUpdated(DomainEvent):
    name: str


# --- Custom Field Definitions ---


@dataclass(frozen=True, kw_only=True)
class CustomFieldDefinitionCreated(DomainEvent):
    name: str
    applies_to: str


@dataclass(frozen=True, kw_only=True)
class CustomFieldDefinitionUpdated(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class CustomFieldDefinitionDeactivated(DomainEvent):
    pass


# --- Salt Catalog ---


@dataclass(frozen=True, kw_only=True)
class SaltEntryCreated(DomainEvent):
    code: str


@dataclass(frozen=True, kw_only=True)
class SaltEntryUpdated(DomainEvent):
    pass


# --- Registration Forms ---


@dataclass(frozen=True, kw_only=True)
class RegistrationFormCreated(DomainEvent):
    name: str
    applies_to: str


@dataclass(frozen=True, kw_only=True)
class RegistrationFormUpdated(DomainEvent):
    pass


# --- Protocol Forms ---


@dataclass(frozen=True, kw_only=True)
class ProtocolFormCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class ProtocolFormUpdated(DomainEvent):
    pass


# --- External API Keys ---


@dataclass(frozen=True, kw_only=True)
class ExternalApiKeyCreated(DomainEvent):
    key_name: str


@dataclass(frozen=True, kw_only=True)
class ExternalApiKeyUpdated(DomainEvent):
    pass


# --- Ontology Slot Definitions ---


@dataclass(frozen=True, kw_only=True)
class OntologySlotDefinitionCreated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class OntologySlotDefinitionUpdated(DomainEvent):
    pass


# --- Data Sources ---


@dataclass(frozen=True, kw_only=True)
class DataSourceCreated(DomainEvent):
    name: str
    source_type: str


@dataclass(frozen=True, kw_only=True)
class DataSourceUpdated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class DataSourceDeactivated(DomainEvent):
    name: str
