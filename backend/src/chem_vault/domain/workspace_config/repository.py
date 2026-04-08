"""Repository protocols for workspace configuration entities."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from chem_vault.domain.workspace_config.enums import FieldTarget
from chem_vault.domain.workspace_config.organization import Organization
from chem_vault.domain.workspace_config.registration_form import RegistrationForm
from chem_vault.domain.workspace_config.salt_entry import SaltEntry
from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings


@runtime_checkable
class OrganizationRepository(Protocol):
    """Repository for Organization aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> Organization | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Organization | None: ...

    async def save(self, aggregate: Organization) -> None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, include_inactive: bool = False
    ) -> list[Organization]: ...

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> Organization | None: ...


@runtime_checkable
class WorkspaceSettingsRepository(Protocol):
    """Repository for WorkspaceSettings aggregates.

    Uses workspace_id as the identity key (id == workspace_id).
    """

    async def find_by_id(self, id: uuid.UUID) -> WorkspaceSettings | None: ...

    async def save(self, aggregate: WorkspaceSettings) -> None: ...


@runtime_checkable
class ControlledVocabularyRepository(Protocol):
    """Repository for ControlledVocabulary aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> ControlledVocabulary | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> ControlledVocabulary | None: ...

    async def save(self, aggregate: ControlledVocabulary) -> None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[ControlledVocabulary]: ...

    async def find_by_name(
        self, workspace_id: uuid.UUID, name: str
    ) -> ControlledVocabulary | None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class CustomFieldDefinitionRepository(Protocol):
    """Repository for CustomFieldDefinition aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> CustomFieldDefinition | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> CustomFieldDefinition | None: ...

    async def save(self, aggregate: CustomFieldDefinition) -> None: ...

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        applies_to: FieldTarget | None = None,
        active_only: bool = True,
    ) -> list[CustomFieldDefinition]: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class SaltEntryRepository(Protocol):
    """Repository for SaltEntry aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> SaltEntry | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> SaltEntry | None: ...

    async def save(self, aggregate: SaltEntry) -> None: ...

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, active_only: bool = True
    ) -> list[SaltEntry]: ...

    async def find_by_code(
        self, workspace_id: uuid.UUID, code: str
    ) -> SaltEntry | None: ...

    async def find_by_smiles(
        self, workspace_id: uuid.UUID, smiles: str
    ) -> SaltEntry | None: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@runtime_checkable
class RegistrationFormRepository(Protocol):
    """Repository for RegistrationForm aggregates."""

    async def find_by_id(self, id: uuid.UUID) -> RegistrationForm | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> RegistrationForm | None: ...

    async def save(self, aggregate: RegistrationForm) -> None: ...

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        applies_to: FieldTarget | None = None,
    ) -> list[RegistrationForm]: ...

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
