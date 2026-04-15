"""Domain events for workspace configuration context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.workspace_config.enums import OrganizationType


@dataclass(frozen=True, kw_only=True)
class OrganizationCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
    org_type: OrganizationType


@dataclass(frozen=True, kw_only=True)
class OrganizationUpdated(DomainEvent):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class OrganizationDeactivated(DomainEvent):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class WorkspaceSettingsUpdated(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class VocabularyCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class VocabularyUpdated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


# --- Custom Field Definitions ---


@dataclass(frozen=True, kw_only=True)
class CustomFieldDefinitionCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
    applies_to: str


@dataclass(frozen=True, kw_only=True)
class CustomFieldDefinitionUpdated(DomainEvent):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CustomFieldDefinitionDeactivated(DomainEvent):
    workspace_id: uuid.UUID


# --- Salt Catalog ---


@dataclass(frozen=True, kw_only=True)
class SaltEntryCreated(DomainEvent):
    workspace_id: uuid.UUID
    code: str


@dataclass(frozen=True, kw_only=True)
class SaltEntryUpdated(DomainEvent):
    workspace_id: uuid.UUID


# --- Registration Forms ---


@dataclass(frozen=True, kw_only=True)
class RegistrationFormCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
    applies_to: str


@dataclass(frozen=True, kw_only=True)
class RegistrationFormUpdated(DomainEvent):
    workspace_id: uuid.UUID


# --- Protocol Forms ---


@dataclass(frozen=True, kw_only=True)
class ProtocolFormCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class ProtocolFormUpdated(DomainEvent):
    workspace_id: uuid.UUID


# --- External API Keys ---


@dataclass(frozen=True, kw_only=True)
class ExternalApiKeyCreated(DomainEvent):
    workspace_id: uuid.UUID
    key_name: str


@dataclass(frozen=True, kw_only=True)
class ExternalApiKeyUpdated(DomainEvent):
    workspace_id: uuid.UUID


# --- Ontology Slot Definitions ---


@dataclass(frozen=True, kw_only=True)
class OntologySlotDefinitionCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class OntologySlotDefinitionUpdated(DomainEvent):
    workspace_id: uuid.UUID


# --- Data Sources ---


@dataclass(frozen=True, kw_only=True)
class DataSourceCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
    source_type: str


@dataclass(frozen=True, kw_only=True)
class DataSourceUpdated(DomainEvent):
    workspace_id: uuid.UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class DataSourceDeactivated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
