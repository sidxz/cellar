"""Workspace config bindings: orgs, settings, vocabularies, custom fields, salts,
registration forms, external API keys, data sources, ontology slots, protocol forms.
"""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.workspace_config.create_custom_field import CreateCustomField
from cellar.application.workspace_config.create_data_source import CreateDataSource
from cellar.application.workspace_config.create_external_api_key import CreateExternalApiKey
from cellar.application.workspace_config.create_ontology_slot import CreateOntologySlot
from cellar.application.workspace_config.create_organization import CreateOrganization
from cellar.application.workspace_config.create_protocol_form import CreateProtocolForm
from cellar.application.workspace_config.create_registration_form import CreateRegistrationForm
from cellar.application.workspace_config.create_salt_entry import CreateSaltEntry
from cellar.application.workspace_config.create_vocabulary import CreateVocabulary
from cellar.application.workspace_config.delete_custom_field import DeleteCustomField
from cellar.application.workspace_config.delete_data_source import DeleteDataSource
from cellar.application.workspace_config.delete_external_api_key import DeleteExternalApiKey
from cellar.application.workspace_config.delete_ontology_slot import DeleteOntologySlot
from cellar.application.workspace_config.delete_protocol_form import DeleteProtocolForm
from cellar.application.workspace_config.delete_registration_form import DeleteRegistrationForm
from cellar.application.workspace_config.delete_salt_entry import DeleteSaltEntry
from cellar.application.workspace_config.delete_vocabulary import DeleteVocabulary
from cellar.application.workspace_config.get_data_source import GetDataSource
from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from cellar.application.workspace_config.get_external_api_key_secret import (
    GetExternalApiKeySecret,
)
from cellar.application.workspace_config.get_organization import GetOrganization
from cellar.application.workspace_config.get_registration_form import GetRegistrationForm
from cellar.application.workspace_config.get_workspace_settings import GetWorkspaceSettings
from cellar.application.workspace_config.list_custom_fields import ListCustomFields
from cellar.application.workspace_config.list_data_sources import ListDataSources
from cellar.application.workspace_config.list_external_api_keys import ListExternalApiKeys
from cellar.application.workspace_config.list_ontology_slots import ListOntologySlots
from cellar.application.workspace_config.list_organizations import ListOrganizations
from cellar.application.workspace_config.list_protocol_forms import ListProtocolForms
from cellar.application.workspace_config.list_registration_forms import ListRegistrationForms
from cellar.application.workspace_config.list_salt_entries import ListSaltEntries
from cellar.application.workspace_config.list_vocabularies import ListVocabularies
from cellar.application.workspace_config.update_custom_field import UpdateCustomField
from cellar.application.workspace_config.update_data_source import UpdateDataSource
from cellar.application.workspace_config.update_external_api_key import UpdateExternalApiKey
from cellar.application.workspace_config.update_ontology_slot import UpdateOntologySlot
from cellar.application.workspace_config.update_organization import UpdateOrganization
from cellar.application.workspace_config.update_protocol_form import UpdateProtocolForm
from cellar.application.workspace_config.update_registration_form import UpdateRegistrationForm
from cellar.application.workspace_config.update_salt_entry import UpdateSaltEntry
from cellar.application.workspace_config.update_vocabulary import UpdateVocabulary
from cellar.application.workspace_config.update_workspace_settings import (
    UpdateWorkspaceSettings,
)
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (
    SQLAlchemyControlledVocabularyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.custom_field_definition_repository import (
    SQLAlchemyCustomFieldDefinitionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.data_source_repository import (
    SQLAlchemyDataSourceRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.external_api_key_repository import (
    SQLAlchemyExternalApiKeyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.ontology_slot_definition_repository import (
    SQLAlchemyOntologySlotDefinitionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.organization_repository import (
    SQLAlchemyOrganizationRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_form_repository import (
    SQLAlchemyProtocolFormRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.registration_form_repository import (
    SQLAlchemyRegistrationFormRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.application.admin.admin_delete_registry import register_admin_delete
from cellar.application.workspace_config.tagging.assign_tag import AssignTag
from cellar.application.workspace_config.tagging.delete_tag import DeleteTag
from cellar.application.workspace_config.tagging.get_tags_for_entity import GetTagsForEntity
from cellar.application.workspace_config.tagging.list_tag_entities import ListTagEntities
from cellar.application.workspace_config.tagging.list_tags import ListTags
from cellar.application.workspace_config.tagging.merge_tags import MergeTags
from cellar.application.workspace_config.tagging.rename_tag import RenameTag
from cellar.application.workspace_config.tagging.set_entity_tags import SetEntityTags
from cellar.application.workspace_config.tagging.unassign_tag import UnassignTag
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_browse_repository import (
    SQLAlchemyTagBrowseRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    SQLAlchemyTagLinkRepositoryProvider,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)


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
            return uc_cls(
                uow=uow,
                repo=SQLAlchemyCustomFieldDefinitionRepository(uow),
                dispatcher=c[EventDispatcher],
            )

        return _f

    def _cfd_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow=uow, repo=SQLAlchemyCustomFieldDefinitionRepository(uow))

        return _f

    def _delete_custom_field(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteCustomField(
            uow=uow,
            repo=SQLAlchemyCustomFieldDefinitionRepository(uow),
            dispatcher=c[EventDispatcher],
        )

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
        return DeleteRegistrationForm(
            uow, SQLAlchemyRegistrationFormRepository(uow), c[EventDispatcher]
        )

    container.define(CreateRegistrationForm, _regform_cmd(CreateRegistrationForm))
    container.define(UpdateRegistrationForm, _regform_cmd(UpdateRegistrationForm))
    container.define(GetRegistrationForm, _regform_query(GetRegistrationForm))
    container.define(ListRegistrationForms, _regform_query(ListRegistrationForms))
    container.define(DeleteRegistrationForm, _delete_registration_form)

    # --- External API Keys ---
    def _apikey_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow, SQLAlchemyExternalApiKeyRepository(uow), c[EventDispatcher], c[SecretProvider]
            )

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

    # --- Tags ---
    def _tag_assign(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyTagRepository(uow),
                SQLAlchemyTagLinkRepositoryProvider(uow),
                c[EventDispatcher],
            )

        return _f

    container.define(AssignTag, _tag_assign(AssignTag))
    container.define(UnassignTag, _tag_assign(UnassignTag))
    container.define(SetEntityTags, _tag_assign(SetEntityTags))

    def _list_tags(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListTags(uow, SQLAlchemyTagRepository(uow))

    container.define(ListTags, _list_tags)

    def _list_tag_entities(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListTagEntities(uow, SQLAlchemyTagBrowseRepository(uow))

    container.define(ListTagEntities, _list_tag_entities)

    def _get_tags_for_entity(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetTagsForEntity(uow, SQLAlchemyTagLinkRepositoryProvider(uow))

    container.define(GetTagsForEntity, _get_tags_for_entity)

    def _rename_or_delete(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyTagRepository(uow), c[EventDispatcher])

        return _f

    container.define(RenameTag, _rename_or_delete(RenameTag))
    container.define(DeleteTag, _rename_or_delete(DeleteTag))

    def _merge_tags(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MergeTags(
            uow,
            SQLAlchemyTagRepository(uow),
            SQLAlchemyTagLinkRepositoryProvider(uow),
            c[EventDispatcher],
        )

    container.define(MergeTags, _merge_tags)

    # --- Admin Hard-Delete Registry (Tier 1) ---
    register_admin_delete(
        entity_type="vocabulary",
        table="controlled_vocabularies",
        label_field="name",
    )
    register_admin_delete(
        entity_type="registration_form",
        table="registration_forms",
        label_field="name",
    )
    register_admin_delete(
        entity_type="protocol_form",
        table="protocol_forms",
        label_field="name",
    )
    register_admin_delete(
        entity_type="salt_entry",
        table="salt_catalog",
        label_field="code",
    )
    register_admin_delete(
        entity_type="ontology_slot",
        table="ontology_slot_definitions",
        label_field="name",
    )
    register_admin_delete(
        entity_type="custom_field",
        table="custom_field_definitions",
        label_field="label",
    )
    register_admin_delete(
        entity_type="data_source",
        table="data_sources",
        label_field="name",
    )
    register_admin_delete(
        entity_type="api_key",
        table="external_api_keys",
        label_field="label",
    )


def build_workspace_config_admin_repos(uow) -> dict:
    """Build the repo map for workspace-config Tier-1 admin deletes.

    Called at AdminHardDelete invocation time (inside the active UoW) so that
    each repo shares the caller's transaction session.
    """
    from cellar.application.admin._adapter import RepoAdapter

    class _VocabularyAdapter:
        """Adapts ControlledVocabularyRepository to the admin-delete protocol."""

        def __init__(self, repo):
            self._r = repo

        async def find_by_id(self, workspace_id, id):
            return await self._r.find_by_id_in_workspace(workspace_id, id)

        async def delete(self, workspace_id, id):
            await self._r.delete(workspace_id, id)

    return {
        "vocabulary": _VocabularyAdapter(SQLAlchemyControlledVocabularyRepository(uow)),
        "registration_form": RepoAdapter(
            SQLAlchemyRegistrationFormRepository(uow), find="find_by_id_in_workspace"
        ),
        "protocol_form": RepoAdapter(
            SQLAlchemyProtocolFormRepository(uow), find="find_by_id_in_workspace"
        ),
        "salt_entry": RepoAdapter(
            SQLAlchemySaltEntryRepository(uow), find="find_by_id_in_workspace"
        ),
        "ontology_slot": RepoAdapter(
            SQLAlchemyOntologySlotDefinitionRepository(uow), find="find_by_id_in_workspace"
        ),
        "custom_field": RepoAdapter(
            SQLAlchemyCustomFieldDefinitionRepository(uow), find="find_by_id_in_workspace"
        ),
        "data_source": RepoAdapter(
            SQLAlchemyDataSourceRepository(uow), find="find_by_id_in_workspace"
        ),
        "api_key": RepoAdapter(
            SQLAlchemyExternalApiKeyRepository(uow), find="find_by_id_in_workspace"
        ),
    }
