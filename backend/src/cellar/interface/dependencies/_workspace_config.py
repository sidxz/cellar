"""Workspace-config + external-API-key + data-source + ontology + protocol-form deps."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.screening.manage_ontology_annotations import (
    RemoveOntologyAnnotation,
    SetOntologyAnnotation,
)
from cellar.application.screening.search_ontology import SearchOntology
from cellar.application.workspace_config.create_custom_field import CreateCustomField
from cellar.application.workspace_config.create_data_source import CreateDataSource
from cellar.application.workspace_config.create_external_api_key import CreateExternalApiKey
from cellar.application.workspace_config.create_ontology_slot import CreateOntologySlot
from cellar.application.workspace_config.create_organization import CreateOrganization
from cellar.application.workspace_config.create_protocol_form import (
    CreateProtocolForm as CreateProtocolFormUC,
)
from cellar.application.workspace_config.create_registration_form import CreateRegistrationForm
from cellar.application.workspace_config.create_salt_entry import CreateSaltEntry
from cellar.application.workspace_config.create_vocabulary import CreateVocabulary
from cellar.application.workspace_config.delete_custom_field import DeleteCustomField
from cellar.application.workspace_config.delete_data_source import DeleteDataSource
from cellar.application.workspace_config.delete_external_api_key import DeleteExternalApiKey
from cellar.application.workspace_config.delete_ontology_slot import DeleteOntologySlot
from cellar.application.workspace_config.delete_protocol_form import (
    DeleteProtocolForm as DeleteProtocolFormUC,
)
from cellar.application.workspace_config.delete_registration_form import DeleteRegistrationForm
from cellar.application.workspace_config.delete_salt_entry import DeleteSaltEntry
from cellar.application.workspace_config.delete_vocabulary import DeleteVocabulary
from cellar.application.workspace_config.get_data_source import GetDataSource
from cellar.application.workspace_config.get_organization import GetOrganization
from cellar.application.workspace_config.get_registration_form import GetRegistrationForm
from cellar.application.workspace_config.get_workspace_settings import GetWorkspaceSettings
from cellar.application.workspace_config.list_custom_fields import ListCustomFields
from cellar.application.workspace_config.list_data_sources import ListDataSources
from cellar.application.workspace_config.list_external_api_keys import ListExternalApiKeys
from cellar.application.workspace_config.list_ontology_slots import ListOntologySlots
from cellar.application.workspace_config.list_organizations import ListOrganizations
from cellar.application.workspace_config.list_protocol_forms import (
    ListProtocolForms as ListProtocolFormsUC,
)
from cellar.application.workspace_config.list_registration_forms import ListRegistrationForms
from cellar.application.workspace_config.list_salt_entries import ListSaltEntries
from cellar.application.workspace_config.list_vocabularies import ListVocabularies
from cellar.application.workspace_config.update_custom_field import UpdateCustomField
from cellar.application.workspace_config.update_data_source import UpdateDataSource
from cellar.application.workspace_config.update_external_api_key import UpdateExternalApiKey
from cellar.application.workspace_config.update_ontology_slot import UpdateOntologySlot
from cellar.application.workspace_config.update_organization import UpdateOrganization
from cellar.application.workspace_config.update_protocol_form import (
    UpdateProtocolForm as UpdateProtocolFormUC,
)
from cellar.application.workspace_config.update_registration_form import UpdateRegistrationForm
from cellar.application.workspace_config.update_salt_entry import UpdateSaltEntry
from cellar.application.workspace_config.update_vocabulary import UpdateVocabulary
from cellar.application.workspace_config.update_workspace_settings import UpdateWorkspaceSettings
from cellar.application.workspace_config.tagging.assign_tag import AssignTag
from cellar.application.workspace_config.tagging.delete_tag import DeleteTag
from cellar.application.workspace_config.tagging.get_tags_for_entity import GetTagsForEntity
from cellar.application.workspace_config.tagging.list_tag_entities import ListTagEntities
from cellar.application.workspace_config.tagging.list_tags import ListTags
from cellar.application.workspace_config.tagging.merge_tags import MergeTags
from cellar.application.workspace_config.tagging.rename_tag import RenameTag
from cellar.application.workspace_config.tagging.set_entity_tags import SetEntityTags
from cellar.application.workspace_config.tagging.unassign_tag import UnassignTag

from ._core import _get_use_case

__all__ = [
    # Workspace config
    "CreateOrganizationDep",
    "UpdateOrganizationDep",
    "GetOrganizationDep",
    "ListOrganizationsDep",
    "GetWorkspaceSettingsDep",
    "UpdateWorkspaceSettingsDep",
    "CreateVocabularyDep",
    "UpdateVocabularyDep",
    "ListVocabulariesDep",
    "DeleteVocabularyDep",
    "CreateCustomFieldDep",
    "ListCustomFieldsDep",
    "UpdateCustomFieldDep",
    "DeleteCustomFieldDep",
    "CreateSaltEntryDep",
    "ListSaltEntriesDep",
    "UpdateSaltEntryDep",
    "DeleteSaltEntryDep",
    "CreateRegistrationFormDep",
    "GetRegistrationFormDep",
    "ListRegistrationFormsDep",
    "UpdateRegistrationFormDep",
    "DeleteRegistrationFormDep",
    # External API keys
    "CreateExternalApiKeyDep",
    "ListExternalApiKeysDep",
    "UpdateExternalApiKeyDep",
    "DeleteExternalApiKeyDep",
    # Data source
    "CreateDataSourceDep",
    "GetDataSourceDep",
    "ListDataSourcesDep",
    "UpdateDataSourceDep",
    "DeleteDataSourceDep",
    # Ontology slots
    "CreateOntologySlotDep",
    "ListOntologySlotsDep",
    "UpdateOntologySlotDep",
    "DeleteOntologySlotDep",
    # Ontology search + annotations
    "SearchOntologyDep",
    "SetOntologyAnnotationDep",
    "RemoveOntologyAnnotationDep",
    # Protocol forms
    "CreateProtocolFormDep",
    "ListProtocolFormsDep",
    "UpdateProtocolFormDep",
    "DeleteProtocolFormDep",
    # Tags
    "AssignTagDep",
    "UnassignTagDep",
    "SetEntityTagsDep",
    "ListTagsDep",
    "ListTagEntitiesDep",
    "GetTagsForEntityDep",
    "RenameTagDep",
    "MergeTagsDep",
    "DeleteTagDep",
]

# --- Workspace Config dependencies ---
CreateOrganizationDep = Annotated[CreateOrganization, Depends(_get_use_case(CreateOrganization))]
UpdateOrganizationDep = Annotated[UpdateOrganization, Depends(_get_use_case(UpdateOrganization))]
GetOrganizationDep = Annotated[GetOrganization, Depends(_get_use_case(GetOrganization))]
ListOrganizationsDep = Annotated[ListOrganizations, Depends(_get_use_case(ListOrganizations))]
GetWorkspaceSettingsDep = Annotated[
    GetWorkspaceSettings, Depends(_get_use_case(GetWorkspaceSettings))
]
UpdateWorkspaceSettingsDep = Annotated[
    UpdateWorkspaceSettings, Depends(_get_use_case(UpdateWorkspaceSettings))
]
CreateVocabularyDep = Annotated[CreateVocabulary, Depends(_get_use_case(CreateVocabulary))]
UpdateVocabularyDep = Annotated[UpdateVocabulary, Depends(_get_use_case(UpdateVocabulary))]
ListVocabulariesDep = Annotated[ListVocabularies, Depends(_get_use_case(ListVocabularies))]
DeleteVocabularyDep = Annotated[DeleteVocabulary, Depends(_get_use_case(DeleteVocabulary))]
CreateCustomFieldDep = Annotated[CreateCustomField, Depends(_get_use_case(CreateCustomField))]
ListCustomFieldsDep = Annotated[ListCustomFields, Depends(_get_use_case(ListCustomFields))]
UpdateCustomFieldDep = Annotated[UpdateCustomField, Depends(_get_use_case(UpdateCustomField))]
DeleteCustomFieldDep = Annotated[DeleteCustomField, Depends(_get_use_case(DeleteCustomField))]
CreateSaltEntryDep = Annotated[CreateSaltEntry, Depends(_get_use_case(CreateSaltEntry))]
ListSaltEntriesDep = Annotated[ListSaltEntries, Depends(_get_use_case(ListSaltEntries))]
UpdateSaltEntryDep = Annotated[UpdateSaltEntry, Depends(_get_use_case(UpdateSaltEntry))]
DeleteSaltEntryDep = Annotated[DeleteSaltEntry, Depends(_get_use_case(DeleteSaltEntry))]
CreateRegistrationFormDep = Annotated[
    CreateRegistrationForm, Depends(_get_use_case(CreateRegistrationForm))
]
GetRegistrationFormDep = Annotated[
    GetRegistrationForm, Depends(_get_use_case(GetRegistrationForm))
]
ListRegistrationFormsDep = Annotated[
    ListRegistrationForms, Depends(_get_use_case(ListRegistrationForms))
]
UpdateRegistrationFormDep = Annotated[
    UpdateRegistrationForm, Depends(_get_use_case(UpdateRegistrationForm))
]
DeleteRegistrationFormDep = Annotated[
    DeleteRegistrationForm, Depends(_get_use_case(DeleteRegistrationForm))
]

# --- External API Keys dependencies ---
CreateExternalApiKeyDep = Annotated[
    CreateExternalApiKey, Depends(_get_use_case(CreateExternalApiKey))
]
ListExternalApiKeysDep = Annotated[
    ListExternalApiKeys, Depends(_get_use_case(ListExternalApiKeys))
]
UpdateExternalApiKeyDep = Annotated[
    UpdateExternalApiKey, Depends(_get_use_case(UpdateExternalApiKey))
]
DeleteExternalApiKeyDep = Annotated[
    DeleteExternalApiKey, Depends(_get_use_case(DeleteExternalApiKey))
]

# --- Data Source dependencies ---
CreateDataSourceDep = Annotated[CreateDataSource, Depends(_get_use_case(CreateDataSource))]
GetDataSourceDep = Annotated[GetDataSource, Depends(_get_use_case(GetDataSource))]
ListDataSourcesDep = Annotated[ListDataSources, Depends(_get_use_case(ListDataSources))]
UpdateDataSourceDep = Annotated[UpdateDataSource, Depends(_get_use_case(UpdateDataSource))]
DeleteDataSourceDep = Annotated[DeleteDataSource, Depends(_get_use_case(DeleteDataSource))]

# --- Ontology Slot dependencies ---
CreateOntologySlotDep = Annotated[CreateOntologySlot, Depends(_get_use_case(CreateOntologySlot))]
ListOntologySlotsDep = Annotated[ListOntologySlots, Depends(_get_use_case(ListOntologySlots))]
UpdateOntologySlotDep = Annotated[UpdateOntologySlot, Depends(_get_use_case(UpdateOntologySlot))]
DeleteOntologySlotDep = Annotated[DeleteOntologySlot, Depends(_get_use_case(DeleteOntologySlot))]

# --- Ontology Search + Annotation dependencies ---
SearchOntologyDep = Annotated[SearchOntology, Depends(_get_use_case(SearchOntology))]
SetOntologyAnnotationDep = Annotated[
    SetOntologyAnnotation, Depends(_get_use_case(SetOntologyAnnotation))
]
RemoveOntologyAnnotationDep = Annotated[
    RemoveOntologyAnnotation, Depends(_get_use_case(RemoveOntologyAnnotation))
]

# --- Protocol Form dependencies ---
CreateProtocolFormDep = Annotated[
    CreateProtocolFormUC, Depends(_get_use_case(CreateProtocolFormUC))
]
ListProtocolFormsDep = Annotated[ListProtocolFormsUC, Depends(_get_use_case(ListProtocolFormsUC))]
UpdateProtocolFormDep = Annotated[
    UpdateProtocolFormUC, Depends(_get_use_case(UpdateProtocolFormUC))
]
DeleteProtocolFormDep = Annotated[
    DeleteProtocolFormUC, Depends(_get_use_case(DeleteProtocolFormUC))
]

# --- Tag dependencies ---
AssignTagDep = Annotated[AssignTag, Depends(_get_use_case(AssignTag))]
UnassignTagDep = Annotated[UnassignTag, Depends(_get_use_case(UnassignTag))]
SetEntityTagsDep = Annotated[SetEntityTags, Depends(_get_use_case(SetEntityTags))]
ListTagsDep = Annotated[ListTags, Depends(_get_use_case(ListTags))]
ListTagEntitiesDep = Annotated[ListTagEntities, Depends(_get_use_case(ListTagEntities))]
GetTagsForEntityDep = Annotated[GetTagsForEntity, Depends(_get_use_case(GetTagsForEntity))]
RenameTagDep = Annotated[RenameTag, Depends(_get_use_case(RenameTag))]
MergeTagsDep = Annotated[MergeTags, Depends(_get_use_case(MergeTags))]
DeleteTagDep = Annotated[DeleteTag, Depends(_get_use_case(DeleteTag))]
