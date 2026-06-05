"""Research-organization (projects, collections, saved searches) + campaign deps."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.research_organization.add_campaign_channel import AddCampaignChannel
from cellar.application.research_organization.add_result_row import AddResultRow
from cellar.application.research_organization.add_results_from_campaign import (
    AddResultsFromCampaign as AddResultsFromCampaignUC,
)
from cellar.application.research_organization.add_results_from_collection import (
    AddResultsFromCollection as AddResultsFromCollectionUC,
)
from cellar.application.research_organization.add_results_from_runs import (
    AddResultsFromRuns as AddResultsFromRunsUC,
)
from cellar.application.research_organization.archive_project import ArchiveProject
from cellar.application.research_organization.bulk_add_to_collection import BulkAddToCollection
from cellar.application.research_organization.bulk_set_result_decisions import (
    BulkSetResultDecisions,
)
from cellar.application.research_organization.close_campaign import CloseCampaign
from cellar.application.research_organization.collection_import_templates import (
    CreateCollectionImportTemplate,
    DeleteCollectionImportTemplate,
    ListCollectionImportTemplates,
    UpdateCollectionImportTemplate,
)
from cellar.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    ListCollectionMolecules,
    RemoveMoleculesFromCollection,
)
from cellar.application.research_organization.compose_collections import ComposeCollections
from cellar.application.research_organization.count_search import CountSearch
from cellar.application.research_organization.create_campaign import (
    CreateCampaign as CreateCampaignUC,
)
from cellar.application.research_organization.create_collection import CreateCollection
from cellar.application.research_organization.create_project import CreateProject
from cellar.application.research_organization.create_saved_search import CreateSavedSearch
from cellar.application.research_organization.delete_collection import DeleteCollection
from cellar.application.research_organization.delete_saved_search import DeleteSavedSearch
from cellar.application.research_organization.execute_search import ExecuteSearch
from cellar.application.research_organization.get_campaign import GetCampaign
from cellar.application.research_organization.get_collection import (
    GetCollection,
    ListCollections,
)
from cellar.application.research_organization.get_collections_for_molecule import (
    ListCollectionsForMolecule,
)
from cellar.application.research_organization.get_project import GetProject, ListProjects
from cellar.application.research_organization.get_project_scope_stats import (
    GetProjectScopeStats,
)
from cellar.application.research_organization.get_published_campaign import GetPublishedCampaign
from cellar.application.research_organization.get_saved_search import (
    GetSavedSearch,
    ListSavedSearches,
)
from cellar.application.research_organization.list_campaigns import ListCampaigns
from cellar.application.research_organization.manage_molecule_projects import (
    AddMoleculeToProject,
    ListMoleculeProjects,
    RemoveMoleculeFromProject,
)
from cellar.application.research_organization.manage_project_members import (
    AddProjectMember,
    ListProjectMembers,
    RemoveProjectMember,
    UpdateProjectMemberRole,
)
from cellar.application.research_organization.mirror_protocol_channels import (
    MirrorProtocolChannels,
)
from cellar.application.research_organization.override_result_cell import OverrideResultCell
from cellar.application.research_organization.preview_run_import import PreviewRunImport
from cellar.application.research_organization.recompute_channel import RecomputeChannel
from cellar.application.research_organization.refresh_campaign_from_sources import (
    RefreshFromSources,
)
from cellar.application.research_organization.remove_campaign_channel import RemoveCampaignChannel
from cellar.application.research_organization.remove_result_row import RemoveResultRow
from cellar.application.research_organization.set_result_decision import SetResultDecision
from cellar.application.research_organization.supersede_campaign import (
    SupersedeCampaign as SupersedeCampaignUC,
)
from cellar.application.research_organization.update_campaign_channel import UpdateCampaignChannel
from cellar.application.research_organization.update_campaign_metadata import (
    UpdateCampaignMetadata,
)
from cellar.application.research_organization.update_collection import UpdateCollection
from cellar.application.research_organization.update_project import UpdateProject
from cellar.application.research_organization.update_saved_search import UpdateSavedSearch
from cellar.application.screening.get_dose_response_curves_batch import (
    GetDoseResponseCurvesBatch,
)
from cellar.domain.research_organization.repository import (
    CampaignRepository,
    CollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

from ._core import _get_use_case, get_container

__all__ = [
    "AddCampaignChannelDep",
    "AddMoleculeToProjectDep",
    "AddMoleculesToCollectionDep",
    # Project members + molecule-project links
    "AddProjectMemberDep",
    "AddResultRowDep",
    "AddResultsFromCampaignDep",
    "AddResultsFromCollectionDep",
    "AddResultsFromRunsDep",
    "ArchiveProjectDep",
    "BulkAddToCollectionDep",
    "BulkSetResultDecisionsDep",
    "CampaignRepositoryDep",
    "CloseCampaignDep",
    "CollectionRepoUoWDep",
    # Collections
    "ComposeCollectionsDep",
    "CountSearchDep",
    "CreateCampaignDep",
    "CreateCollectionDep",
    "CreateCollectionImportTemplateDep",
    # Research org — projects
    "CreateProjectDep",
    # Saved searches
    "CreateSavedSearchDep",
    "DeleteCollectionDep",
    "DeleteCollectionImportTemplateDep",
    "DeleteSavedSearchDep",
    "ExecuteSearchDep",
    "GetCampaignDep",
    "GetCollectionDep",
    "GetDoseResponseCurvesBatchDep",
    "GetProjectDep",
    "GetProjectScopeStatsDep",
    "GetPublishedCampaignDep",
    "GetSavedSearchDep",
    "ListCampaignsDep",
    "ListCollectionImportTemplatesDep",
    "ListCollectionMoleculesDep",
    "ListCollectionsDep",
    "ListCollectionsForMoleculeDep",
    "ListMoleculeProjectsDep",
    "ListProjectMembersDep",
    "ListProjectsDep",
    "ListSavedSearchesDep",
    "MirrorProtocolChannelsDep",
    "OverrideResultCellDep",
    "PreviewRunImportDep",
    "RecomputeChannelDep",
    "RefreshFromSourcesDep",
    "RemoveCampaignChannelDep",
    "RemoveMoleculeFromProjectDep",
    "RemoveMoleculesFromCollectionDep",
    "RemoveProjectMemberDep",
    "RemoveResultRowDep",
    "SetResultDecisionDep",
    "SupersedeCampaignDep",
    "UpdateCampaignChannelDep",
    "UpdateCampaignMetadataDep",
    "UpdateCollectionDep",
    "UpdateCollectionImportTemplateDep",
    "UpdateProjectDep",
    "UpdateProjectMemberRoleDep",
    "UpdateSavedSearchDep",
    # Campaigns
    "get_campaign_repo",
    # Collection repository (for the unregistered-rows handoff endpoint)
    "get_collection_repo_uow",
]

# --- Research Organization dependencies ---
CreateProjectDep = Annotated[CreateProject, Depends(_get_use_case(CreateProject))]
UpdateProjectDep = Annotated[UpdateProject, Depends(_get_use_case(UpdateProject))]
ArchiveProjectDep = Annotated[ArchiveProject, Depends(_get_use_case(ArchiveProject))]
GetProjectDep = Annotated[GetProject, Depends(_get_use_case(GetProject))]
ListProjectsDep = Annotated[ListProjects, Depends(_get_use_case(ListProjects))]
GetProjectScopeStatsDep = Annotated[
    GetProjectScopeStats, Depends(_get_use_case(GetProjectScopeStats))
]
ComposeCollectionsDep = Annotated[ComposeCollections, Depends(_get_use_case(ComposeCollections))]
CreateCollectionDep = Annotated[CreateCollection, Depends(_get_use_case(CreateCollection))]
UpdateCollectionDep = Annotated[UpdateCollection, Depends(_get_use_case(UpdateCollection))]
DeleteCollectionDep = Annotated[DeleteCollection, Depends(_get_use_case(DeleteCollection))]
GetCollectionDep = Annotated[GetCollection, Depends(_get_use_case(GetCollection))]
ListCollectionsDep = Annotated[ListCollections, Depends(_get_use_case(ListCollections))]
AddMoleculesToCollectionDep = Annotated[
    AddMoleculesToCollection, Depends(_get_use_case(AddMoleculesToCollection))
]
RemoveMoleculesFromCollectionDep = Annotated[
    RemoveMoleculesFromCollection, Depends(_get_use_case(RemoveMoleculesFromCollection))
]
ListCollectionMoleculesDep = Annotated[
    ListCollectionMolecules, Depends(_get_use_case(ListCollectionMolecules))
]
ListCollectionsForMoleculeDep = Annotated[
    ListCollectionsForMolecule, Depends(_get_use_case(ListCollectionsForMolecule))
]
BulkAddToCollectionDep = Annotated[
    BulkAddToCollection, Depends(_get_use_case(BulkAddToCollection))
]
CreateCollectionImportTemplateDep = Annotated[
    CreateCollectionImportTemplate, Depends(_get_use_case(CreateCollectionImportTemplate))
]
UpdateCollectionImportTemplateDep = Annotated[
    UpdateCollectionImportTemplate, Depends(_get_use_case(UpdateCollectionImportTemplate))
]
DeleteCollectionImportTemplateDep = Annotated[
    DeleteCollectionImportTemplate, Depends(_get_use_case(DeleteCollectionImportTemplate))
]
ListCollectionImportTemplatesDep = Annotated[
    ListCollectionImportTemplates, Depends(_get_use_case(ListCollectionImportTemplates))
]
CreateSavedSearchDep = Annotated[CreateSavedSearch, Depends(_get_use_case(CreateSavedSearch))]
UpdateSavedSearchDep = Annotated[UpdateSavedSearch, Depends(_get_use_case(UpdateSavedSearch))]
DeleteSavedSearchDep = Annotated[DeleteSavedSearch, Depends(_get_use_case(DeleteSavedSearch))]
GetSavedSearchDep = Annotated[GetSavedSearch, Depends(_get_use_case(GetSavedSearch))]
ListSavedSearchesDep = Annotated[ListSavedSearches, Depends(_get_use_case(ListSavedSearches))]
ExecuteSearchDep = Annotated[ExecuteSearch, Depends(_get_use_case(ExecuteSearch))]
CountSearchDep = Annotated[CountSearch, Depends(_get_use_case(CountSearch))]
AddProjectMemberDep = Annotated[AddProjectMember, Depends(_get_use_case(AddProjectMember))]
RemoveProjectMemberDep = Annotated[
    RemoveProjectMember, Depends(_get_use_case(RemoveProjectMember))
]
UpdateProjectMemberRoleDep = Annotated[
    UpdateProjectMemberRole, Depends(_get_use_case(UpdateProjectMemberRole))
]
ListProjectMembersDep = Annotated[ListProjectMembers, Depends(_get_use_case(ListProjectMembers))]
AddMoleculeToProjectDep = Annotated[
    AddMoleculeToProject, Depends(_get_use_case(AddMoleculeToProject))
]
RemoveMoleculeFromProjectDep = Annotated[
    RemoveMoleculeFromProject, Depends(_get_use_case(RemoveMoleculeFromProject))
]
ListMoleculeProjectsDep = Annotated[
    ListMoleculeProjects, Depends(_get_use_case(ListMoleculeProjects))
]


# --- Collection repository (route-managed UoW) ---
def get_collection_repo_uow(
    container: Annotated[Container, Depends(get_container)],
) -> tuple[CollectionRepository, AsyncUnitOfWork]:
    """Fresh ``(CollectionRepository, AsyncUnitOfWork)`` pair.

    The route handler is responsible for entering the UoW context::

        repo, uow = collection_repo_uow
        async with uow:
            collection = await repo.find_by_id_in_workspace(...)
    """
    uow = AsyncUnitOfWork(container[async_sessionmaker])
    return SQLAlchemyCollectionRepository(uow), uow


CollectionRepoUoWDep = Annotated[
    tuple[CollectionRepository, AsyncUnitOfWork], Depends(get_collection_repo_uow)
]


# --- Campaign dependencies ---
def get_campaign_repo(
    container: Annotated[Container, Depends(get_container)],
) -> CampaignRepository:
    """Campaign repository — used directly by list/get routes."""
    return container[CampaignRepository]


CampaignRepositoryDep = Annotated[CampaignRepository, Depends(get_campaign_repo)]

CreateCampaignDep = Annotated[CreateCampaignUC, Depends(_get_use_case(CreateCampaignUC))]
AddResultsFromCollectionDep = Annotated[
    AddResultsFromCollectionUC, Depends(_get_use_case(AddResultsFromCollectionUC))
]
AddResultsFromCampaignDep = Annotated[
    AddResultsFromCampaignUC, Depends(_get_use_case(AddResultsFromCampaignUC))
]
AddResultsFromRunsDep = Annotated[
    AddResultsFromRunsUC, Depends(_get_use_case(AddResultsFromRunsUC))
]
PreviewRunImportDep = Annotated[PreviewRunImport, Depends(_get_use_case(PreviewRunImport))]
AddCampaignChannelDep = Annotated[AddCampaignChannel, Depends(_get_use_case(AddCampaignChannel))]
UpdateCampaignChannelDep = Annotated[
    UpdateCampaignChannel, Depends(_get_use_case(UpdateCampaignChannel))
]
MirrorProtocolChannelsDep = Annotated[
    MirrorProtocolChannels, Depends(_get_use_case(MirrorProtocolChannels))
]
RemoveCampaignChannelDep = Annotated[
    RemoveCampaignChannel, Depends(_get_use_case(RemoveCampaignChannel))
]
SetResultDecisionDep = Annotated[SetResultDecision, Depends(_get_use_case(SetResultDecision))]
BulkSetResultDecisionsDep = Annotated[
    BulkSetResultDecisions, Depends(_get_use_case(BulkSetResultDecisions))
]
OverrideResultCellDep = Annotated[OverrideResultCell, Depends(_get_use_case(OverrideResultCell))]
AddResultRowDep = Annotated[AddResultRow, Depends(_get_use_case(AddResultRow))]
RemoveResultRowDep = Annotated[RemoveResultRow, Depends(_get_use_case(RemoveResultRow))]
RefreshFromSourcesDep = Annotated[RefreshFromSources, Depends(_get_use_case(RefreshFromSources))]
CloseCampaignDep = Annotated[CloseCampaign, Depends(_get_use_case(CloseCampaign))]
SupersedeCampaignDep = Annotated[SupersedeCampaignUC, Depends(_get_use_case(SupersedeCampaignUC))]
GetPublishedCampaignDep = Annotated[
    GetPublishedCampaign, Depends(_get_use_case(GetPublishedCampaign))
]
ListCampaignsDep = Annotated[ListCampaigns, Depends(_get_use_case(ListCampaigns))]
GetCampaignDep = Annotated[GetCampaign, Depends(_get_use_case(GetCampaign))]
GetDoseResponseCurvesBatchDep = Annotated[
    GetDoseResponseCurvesBatch, Depends(_get_use_case(GetDoseResponseCurvesBatch))
]
RecomputeChannelDep = Annotated[RecomputeChannel, Depends(_get_use_case(RecomputeChannel))]
UpdateCampaignMetadataDep = Annotated[
    UpdateCampaignMetadata, Depends(_get_use_case(UpdateCampaignMetadata))
]
