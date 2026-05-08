"""Workspace config bindings: orgs, settings, vocabularies, custom fields, salts,
registration forms, external API keys, data sources, ontology slots, protocol forms.
"""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.workspace_config.create_custom_field import CreateCustomField
from chem_vault.application.workspace_config.create_data_source import CreateDataSource
from chem_vault.application.workspace_config.create_external_api_key import CreateExternalApiKey
from chem_vault.application.workspace_config.create_ontology_slot import CreateOntologySlot
from chem_vault.application.workspace_config.create_organization import CreateOrganization
from chem_vault.application.workspace_config.create_protocol_form import CreateProtocolForm
from chem_vault.application.workspace_config.create_registration_form import CreateRegistrationForm
from chem_vault.application.workspace_config.create_salt_entry import CreateSaltEntry
from chem_vault.application.workspace_config.create_vocabulary import CreateVocabulary
from chem_vault.application.workspace_config.delete_custom_field import DeleteCustomField
from chem_vault.application.workspace_config.delete_data_source import DeleteDataSource
from chem_vault.application.workspace_config.delete_external_api_key import DeleteExternalApiKey
from chem_vault.application.workspace_config.delete_ontology_slot import DeleteOntologySlot
from chem_vault.application.workspace_config.delete_protocol_form import DeleteProtocolForm
from chem_vault.application.workspace_config.delete_registration_form import DeleteRegistrationForm
from chem_vault.application.workspace_config.delete_salt_entry import DeleteSaltEntry
from chem_vault.application.workspace_config.delete_vocabulary import DeleteVocabulary
from chem_vault.application.workspace_config.get_data_source import GetDataSource
from chem_vault.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from chem_vault.application.workspace_config.get_external_api_key_secret import (
    GetExternalApiKeySecret,
)
from chem_vault.application.workspace_config.get_organization import GetOrganization
from chem_vault.application.workspace_config.get_registration_form import GetRegistrationForm
from chem_vault.application.workspace_config.get_workspace_settings import GetWorkspaceSettings
from chem_vault.application.workspace_config.list_custom_fields import ListCustomFields
from chem_vault.application.workspace_config.list_data_sources import ListDataSources
from chem_vault.application.workspace_config.list_external_api_keys import ListExternalApiKeys
from chem_vault.application.workspace_config.list_ontology_slots import ListOntologySlots
from chem_vault.application.workspace_config.list_organizations import ListOrganizations
from chem_vault.application.workspace_config.list_protocol_forms import ListProtocolForms
from chem_vault.application.workspace_config.list_registration_forms import ListRegistrationForms
from chem_vault.application.workspace_config.list_salt_entries import ListSaltEntries
from chem_vault.application.workspace_config.list_vocabularies import ListVocabularies
from chem_vault.application.workspace_config.update_custom_field import UpdateCustomField
from chem_vault.application.workspace_config.update_data_source import UpdateDataSource
from chem_vault.application.workspace_config.update_external_api_key import UpdateExternalApiKey
from chem_vault.application.workspace_config.update_ontology_slot import UpdateOntologySlot
from chem_vault.application.workspace_config.update_organization import UpdateOrganization
from chem_vault.application.workspace_config.update_protocol_form import UpdateProtocolForm
from chem_vault.application.workspace_config.update_registration_form import UpdateRegistrationForm
from chem_vault.application.workspace_config.update_salt_entry import UpdateSaltEntry
from chem_vault.application.workspace_config.update_vocabulary import UpdateVocabulary
from chem_vault.application.workspace_config.update_workspace_settings import (
    UpdateWorkspaceSettings,
)
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (
    SQLAlchemyControlledVocabularyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.custom_field_definition_repository import (
    SQLAlchemyCustomFieldDefinitionRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.data_source_repository import (
    SQLAlchemyDataSourceRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.external_api_key_repository import (
    SQLAlchemyExternalApiKeyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.ontology_slot_definition_repository import (
    SQLAlchemyOntologySlotDefinitionRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.organization_repository import (
    SQLAlchemyOrganizationRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.protocol_form_repository import (
    SQLAlchemyProtocolFormRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.registration_form_repository import (
    SQLAlchemyRegistrationFormRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.application.admin.admin_delete_registry import register_admin_delete
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository


def register_workspace_config(container: Container) -> None:
    # --- Organizations ---
    def _org_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOrganizationRepository(uow), c[EventDispatcher])
        return _f

    def _org_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOrganizationRepository(uow))
        return _f

    container.define(CreateOrganization, _org_cmd(CreateOrganization))
    container.define(UpdateOrganization, _org_cmd(UpdateOrganization))
    container.define(GetOrganization, _org_query(GetOrganization))
    container.define(ListOrganizations, _org_query(ListOrganizations))

    # --- Workspace Settings ---
    def _settings_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyWorkspaceSettingsRepository(uow), c[EventDispatcher])
        return _f

    def _settings_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyWorkspaceSettingsRepository(uow))
        return _f

    container.define(GetWorkspaceSettings, _settings_query(GetWorkspaceSettings))
    container.define(UpdateWorkspaceSettings, _settings_cmd(UpdateWorkspaceSettings))

    # --- Controlled Vocabularies ---
    def _vocab_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyControlledVocabularyRepository(uow), c[EventDispatcher])
        return _f

    def _vocab_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyControlledVocabularyRepository(uow))
        return _f

    container.define(CreateVocabulary, _vocab_cmd(CreateVocabulary))
    container.define(UpdateVocabulary, _vocab_cmd(UpdateVocabulary))
    container.define(ListVocabularies, _vocab_query(ListVocabularies))

    def _delete_vocabulary(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteVocabulary(
            uow,
            SQLAlchemyControlledVocabularyRepository(uow),
            SQLAlchemyWorkspaceSettingsRepository(uow),
            c[EventDispatcher],
        )

    container.define(DeleteVocabulary, _delete_vocabulary)

    # --- Custom Field Definitions ---
    # NOTE: CustomFieldValidator is NOT registered as a singleton. It must share
    # the caller's UoW, so it is constructed inline in use-case factories in
    # chemical_registration and inventory files.
    def _cfd_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow), dispatcher=c[EventDispatcher])
        return _f

    def _cfd_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return _f

    def _delete_custom_field(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteCustomField(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow), dispatcher=c[EventDispatcher])

    container.define(CreateCustomField, _cfd_cmd(CreateCustomField))
    container.define(UpdateCustomField, _cfd_cmd(UpdateCustomField))
    container.define(ListCustomFields, _cfd_query(ListCustomFields))
    container.define(DeleteCustomField, _delete_custom_field)

    # --- Salt Catalog ---
    def _salt_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySaltEntryRepository(uow), c[EventDispatcher])
        return _f

    def _salt_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySaltEntryRepository(uow))
        return _f

    def _delete_salt_entry(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteSaltEntry(uow, SQLAlchemySaltEntryRepository(uow), c[EventDispatcher])

    container.define(CreateSaltEntry, _salt_cmd(CreateSaltEntry))
    container.define(UpdateSaltEntry, _salt_cmd(UpdateSaltEntry))
    container.define(ListSaltEntries, _salt_query(ListSaltEntries))
    container.define(DeleteSaltEntry, _delete_salt_entry)

    # --- Registration Forms ---
    def _regform_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegistrationFormRepository(uow), c[EventDispatcher])
        return _f

    def _regform_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyRegistrationFormRepository(uow))
        return _f

    def _delete_registration_form(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteRegistrationForm(uow, SQLAlchemyRegistrationFormRepository(uow), c[EventDispatcher])

    container.define(CreateRegistrationForm, _regform_cmd(CreateRegistrationForm))
    container.define(UpdateRegistrationForm, _regform_cmd(UpdateRegistrationForm))
    container.define(GetRegistrationForm, _regform_query(GetRegistrationForm))
    container.define(ListRegistrationForms, _regform_query(ListRegistrationForms))
    container.define(DeleteRegistrationForm, _delete_registration_form)

    # --- External API Keys ---
    def _apikey_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyExternalApiKeyRepository(uow), c[EventDispatcher], c[SecretProvider])
        return _f

    def _apikey_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyExternalApiKeyRepository(uow))
        return _f

    container.define(CreateExternalApiKey, _apikey_cmd(CreateExternalApiKey))
    container.define(UpdateExternalApiKey, _apikey_cmd(UpdateExternalApiKey))
    container.define(DeleteExternalApiKey, _apikey_cmd(DeleteExternalApiKey))
    container.define(ListExternalApiKeys, _apikey_query(ListExternalApiKeys))
    container.define(GetExternalApiKeySecret, lambda c: GetExternalApiKeySecret(c[SecretProvider]))

    # --- Data Sources ---
    def _ds_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyDataSourceRepository(uow), c[EventDispatcher])
        return _f

    def _ds_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyDataSourceRepository(uow))
        return _f

    container.define(CreateDataSource, _ds_cmd(CreateDataSource))
    container.define(UpdateDataSource, _ds_cmd(UpdateDataSource))
    container.define(DeleteDataSource, _ds_cmd(DeleteDataSource))
    container.define(ListDataSources, _ds_query(ListDataSources))
    container.define(GetDataSource, _ds_query(GetDataSource))

    def _get_ds_for_import(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetDataSourceForImport(
            uow,
            SQLAlchemyDataSourceRepository(uow),
            SQLAlchemyExternalApiKeyRepository(uow),
            c[SecretProvider],
        )

    container.define(GetDataSourceForImport, _get_ds_for_import)

    # --- Ontology Slot Definitions ---
    def _slot_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOntologySlotDefinitionRepository(uow), c[EventDispatcher])
        return _f

    def _slot_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyOntologySlotDefinitionRepository(uow))
        return _f

    container.define(CreateOntologySlot, _slot_cmd(CreateOntologySlot))
    container.define(UpdateOntologySlot, _slot_cmd(UpdateOntologySlot))
    container.define(DeleteOntologySlot, _slot_cmd(DeleteOntologySlot))
    container.define(ListOntologySlots, _slot_query(ListOntologySlots))

    # --- Protocol Forms ---
    def _pf_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolFormRepository(uow), c[EventDispatcher])
        return _f

    def _pf_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProtocolFormRepository(uow))
        return _f

    container.define(CreateProtocolForm, _pf_cmd(CreateProtocolForm))
    container.define(UpdateProtocolForm, _pf_cmd(UpdateProtocolForm))
    container.define(DeleteProtocolForm, _pf_cmd(DeleteProtocolForm))
    container.define(ListProtocolForms, _pf_query(ListProtocolForms))

    # --- Admin Hard-Delete Registry (Tier 1) ---
    class _VocabularyAdapter:
        """Adapts ControlledVocabularyRepository to the admin-delete protocol."""
        def __init__(self, repo):
            self._r = repo

        async def find_by_id(self, workspace_id, id):
            return await self._r.find_by_id_in_workspace(workspace_id, id)

        async def delete(self, workspace_id, id):
            await self._r.delete(workspace_id, id)

    def _resolve_vocab(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return _VocabularyAdapter(SQLAlchemyControlledVocabularyRepository(uow))

    register_admin_delete(
        entity_type="vocabulary",
        table="controlled_vocabularies",
        label_field="name",
        repo_resolver=_resolve_vocab,
    )
