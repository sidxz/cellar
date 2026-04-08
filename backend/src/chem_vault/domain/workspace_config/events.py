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
