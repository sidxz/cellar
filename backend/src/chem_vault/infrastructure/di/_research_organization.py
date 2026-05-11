"""Research organization bindings: projects, members, molecule-project,
collections, saved searches, execute search.
"""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.research_organization.archive_project import ArchiveProject
from chem_vault.application.research_organization.collection_membership import (
    AddMoleculesToCollection,
    ListCollectionMolecules,
    RemoveMoleculesFromCollection,
)
from chem_vault.application.research_organization.compose_collections import ComposeCollections
from chem_vault.application.research_organization.create_collection import CreateCollection
from chem_vault.application.research_organization.create_project import CreateProject
from chem_vault.application.research_organization.create_saved_search import CreateSavedSearch
from chem_vault.application.research_organization.delete_collection import DeleteCollection
from chem_vault.application.research_organization.delete_saved_search import DeleteSavedSearch
from chem_vault.application.chemical_registration.molecule_reader import MoleculeReader
from chem_vault.application.research_organization.count_search import CountSearch
from chem_vault.application.research_organization.execute_search import ExecuteSearch
from chem_vault.application.research_organization.get_collection import (
    GetCollection,
    ListCollections,
)
from chem_vault.application.research_organization.get_collections_for_molecule import (
    ListCollectionsForMolecule,
)
from chem_vault.application.research_organization.get_project import GetProject, ListProjects
from chem_vault.application.research_organization.get_project_scope_stats import (
    GetProjectScopeStats,
)
from chem_vault.application.research_organization.get_saved_search import (
    GetSavedSearch,
    ListSavedSearches,
)
from chem_vault.application.research_organization.manage_molecule_projects import (
    AddMoleculeToProject,
    ListMoleculeProjects,
    RemoveMoleculeFromProject,
)
from chem_vault.application.research_organization.manage_project_members import (
    AddProjectMember,
    ListProjectMembers,
    RemoveProjectMember,
    UpdateProjectMemberRole,
)
from chem_vault.application.research_organization.update_collection import UpdateCollection
from chem_vault.application.research_organization.update_project import UpdateProject
from chem_vault.application.research_organization.update_saved_search import UpdateSavedSearch
from chem_vault.application.screening.molecule_activity_service import MoleculeActivityService
from chem_vault.application.shared.molecule_resolver import MoleculeResolver
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.project_member_repository import (
    SQLAlchemyProjectMemberRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.saved_search_repository import (
    SQLAlchemySavedSearchRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.application.admin.admin_delete_registry import register_admin_delete
from chem_vault.application.research_organization.add_campaign_channel import AddCampaignChannel
from chem_vault.application.research_organization.add_result_row import AddResultRow
from chem_vault.application.research_organization.add_results_from_campaign import AddResultsFromCampaign as AddResultsFromCampaignUC
from chem_vault.application.research_organization.add_results_from_collection import AddResultsFromCollection as AddResultsFromCollectionUC
from chem_vault.application.research_organization.add_results_from_run import AddResultsFromRun as AddResultsFromRunUC
from chem_vault.application.research_organization.channel_resolution import ChannelResolver
from chem_vault.application.research_organization.close_campaign import CloseCampaign
from chem_vault.application.research_organization.create_campaign import CreateCampaign as CreateCampaignUC
from chem_vault.application.research_organization.get_published_campaign import GetPublishedCampaign
from chem_vault.application.research_organization.override_result_cell import OverrideResultCell
from chem_vault.application.research_organization.recompute_channel import RecomputeChannel
from chem_vault.application.research_organization.refresh_campaign_from_sources import RefreshFromSources
from chem_vault.application.research_organization.remove_campaign_channel import RemoveCampaignChannel
from chem_vault.application.research_organization.remove_result_row import RemoveResultRow

from chem_vault.application.research_organization.set_result_decision import SetResultDecision
from chem_vault.application.research_organization.supersede_campaign import SupersedeCampaign as SupersedeCampaignUC
from chem_vault.application.research_organization.update_campaign_channel import UpdateCampaignChannel
from chem_vault.application.research_organization.update_campaign_metadata import UpdateCampaignMetadata
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.research_organization.repository import CampaignRepository
from chem_vault.domain.screening_assay.repository import ProtocolRepository, RunRepository
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
    SQLAlchemyChannelResolutionQuery,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)


def register_research_organization(container: Container) -> None:
    # Force cascade rules to register at DI bootstrap.
    import chem_vault.infrastructure.cascade.rules_research_organization  # noqa: F401

    # --- Projects ---
    def _project_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProjectRepository(uow), c[EventDispatcher])
        return _f

    def _project_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyProjectRepository(uow))
        return _f

    def _create_project(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateProject(
            uow,
            SQLAlchemyProjectRepository(uow),
            c[EventDispatcher],
            member_repo=SQLAlchemyProjectMemberRepository(uow),
        )

    container.define(CreateProject, _create_project)
    container.define(UpdateProject, _project_cmd(UpdateProject))
    container.define(ArchiveProject, _project_cmd(ArchiveProject))
    container.define(GetProject, _project_query(GetProject))
    container.define(ListProjects, _project_query(ListProjects))
    container.define(GetProjectScopeStats, _project_query(GetProjectScopeStats))

    # --- Project members ---
    def _member_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyProjectRepository(uow),
                SQLAlchemyProjectMemberRepository(uow),
                c[EventDispatcher],
            )
        return _f

    def _member_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyProjectRepository(uow),
                SQLAlchemyProjectMemberRepository(uow),
            )
        return _f

    container.define(AddProjectMember, _member_cmd(AddProjectMember))
    container.define(RemoveProjectMember, _member_cmd(RemoveProjectMember))
    container.define(UpdateProjectMemberRole, _member_cmd(UpdateProjectMemberRole))
    container.define(ListProjectMembers, _member_query(ListProjectMembers))

    # --- Molecule-project association ---
    def _mol_project_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyProjectRepository(uow),
                SQLAlchemyMoleculeRepository(uow),
                SQLAlchemyProjectMemberRepository(uow),
                c[EventDispatcher],
            )
        return _f

    container.define(AddMoleculeToProject, _mol_project_cmd(AddMoleculeToProject))
    container.define(RemoveMoleculeFromProject, _mol_project_cmd(RemoveMoleculeFromProject))

    def _list_mol_projects(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListMoleculeProjects(uow, SQLAlchemyMoleculeRepository(uow))

    container.define(ListMoleculeProjects, _list_mol_projects)

    # --- Collections ---
    def _collection_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyCollectionRepository(uow), c[EventDispatcher])
        return _f

    def _collection_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyCollectionRepository(uow))
        return _f

    def _delete_collection(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteCollection(uow, SQLAlchemyCollectionRepository(uow), c[EventDispatcher])

    container.define(CreateCollection, _collection_cmd(CreateCollection))
    container.define(ComposeCollections, _collection_cmd(ComposeCollections))
    container.define(UpdateCollection, _collection_cmd(UpdateCollection))
    container.define(DeleteCollection, _delete_collection)
    container.define(GetCollection, _collection_query(GetCollection))
    container.define(ListCollections, _collection_query(ListCollections))
    container.define(ListCollectionMolecules, _collection_query(ListCollectionMolecules))
    container.define(ListCollectionsForMolecule, _collection_query(ListCollectionsForMolecule))

    def _add_molecules(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        resolver = MoleculeResolver(SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol])
        return AddMoleculesToCollection(
            uow, SQLAlchemyCollectionRepository(uow), resolver, c[EventDispatcher],
        )

    def _remove_molecules(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveMoleculesFromCollection(
            uow, SQLAlchemyCollectionRepository(uow), c[EventDispatcher],
        )

    container.define(AddMoleculesToCollection, _add_molecules)
    container.define(RemoveMoleculesFromCollection, _remove_molecules)

    # --- Saved Searches ---
    def _ss_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySavedSearchRepository(uow), c[EventDispatcher])
        return _f

    def _ss_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySavedSearchRepository(uow))
        return _f

    def _delete_saved_search(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteSavedSearch(uow, SQLAlchemySavedSearchRepository(uow), c[EventDispatcher])

    container.define(CreateSavedSearch, _ss_cmd(CreateSavedSearch))
    container.define(UpdateSavedSearch, _ss_cmd(UpdateSavedSearch))
    container.define(DeleteSavedSearch, _delete_saved_search)
    container.define(GetSavedSearch, _ss_query(GetSavedSearch))
    container.define(ListSavedSearches, _ss_query(ListSavedSearches))

    # --- Execute Search ---
    def _execute_search(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ExecuteSearch(
            uow,
            c[MoleculeReader],
            SQLAlchemySavedSearchRepository(uow),
            activity_service=MoleculeActivityService(
                uow=uow,
                readout_repo=SQLAlchemyReadoutDataRepository(uow),
                curve_repo=SQLAlchemyDoseResponseCurveRepository(uow),
                protocol_repo=SQLAlchemyProtocolRepository(uow),
            ),
        )

    container.define(ExecuteSearch, _execute_search)

    # --- Count Search (live "Search N compounds" preview) ---
    def _count_search(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CountSearch(
            uow,
            c[MoleculeReader],
            SQLAlchemySavedSearchRepository(uow),
        )

    container.define(CountSearch, _count_search)

    # --- Campaigns ---
    def _channel_resolution_query(c: Container) -> SQLAlchemyChannelResolutionQuery:
        return SQLAlchemyChannelResolutionQuery(c[async_sessionmaker])

    def _channel_resolver(c: Container) -> ChannelResolver:
        return ChannelResolver(query=c[SQLAlchemyChannelResolutionQuery])

    container.define(SQLAlchemyChannelResolutionQuery, _channel_resolution_query)
    container.define(ChannelResolver, _channel_resolver)

    def _campaign_repo(c: Container) -> SQLAlchemyCampaignRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemyCampaignRepository(uow)

    container.define(SQLAlchemyCampaignRepository, _campaign_repo)

    def _campaign_repo_protocol(c: Container) -> CampaignRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemyCampaignRepository(uow)  # type: ignore[return-value]

    container.define(CampaignRepository, _campaign_repo_protocol)

    def _create_campaign(c: Container) -> CreateCampaignUC:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateCampaignUC(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _add_results_from_collection(c: Container) -> AddResultsFromCollectionUC:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddResultsFromCollectionUC(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            collection_repo=SQLAlchemyCollectionRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _add_results_from_campaign(c: Container) -> AddResultsFromCampaignUC:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddResultsFromCampaignUC(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _add_results_from_run(c: Container) -> AddResultsFromRunUC:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddResultsFromRunUC(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            run_repo=SQLAlchemyRunRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _add_channel(c: Container) -> AddCampaignChannel:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddCampaignChannel(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _update_channel(c: Container) -> UpdateCampaignChannel:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdateCampaignChannel(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _remove_channel(c: Container) -> RemoveCampaignChannel:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveCampaignChannel(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _set_decision(c: Container) -> SetResultDecision:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SetResultDecision(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _override_cell(c: Container) -> OverrideResultCell:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return OverrideResultCell(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _add_result_row(c: Container) -> AddResultRow:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddResultRow(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _remove_result_row(c: Container) -> RemoveResultRow:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RemoveResultRow(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _recompute_channel(c: Container) -> RecomputeChannel:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RecomputeChannel(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _update_campaign_metadata(c: Container) -> UpdateCampaignMetadata:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return UpdateCampaignMetadata(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _refresh(c: Container) -> RefreshFromSources:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RefreshFromSources(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _close_campaign(c: Container) -> CloseCampaign:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CloseCampaign(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            collection_repo=SQLAlchemyCollectionRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            resolver=c[ChannelResolver],
            dispatcher=c[EventDispatcher],
        )

    def _supersede(c: Container) -> SupersedeCampaignUC:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SupersedeCampaignUC(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _get_published(c: Container) -> GetPublishedCampaign:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetPublishedCampaign(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            project_repo=SQLAlchemyProjectRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            collection_repo=SQLAlchemyCollectionRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            batch_repo=SQLAlchemyBatchRepository(uow),
        )

    container.define(CreateCampaignUC, _create_campaign)
    container.define(AddResultsFromCollectionUC, _add_results_from_collection)
    container.define(AddResultsFromCampaignUC, _add_results_from_campaign)
    container.define(AddResultsFromRunUC, _add_results_from_run)
    container.define(AddCampaignChannel, _add_channel)
    container.define(UpdateCampaignChannel, _update_channel)
    container.define(RemoveCampaignChannel, _remove_channel)
    container.define(SetResultDecision, _set_decision)
    container.define(OverrideResultCell, _override_cell)
    container.define(AddResultRow, _add_result_row)
    container.define(RemoveResultRow, _remove_result_row)
    container.define(RecomputeChannel, _recompute_channel)
    container.define(UpdateCampaignMetadata, _update_campaign_metadata)
    container.define(RefreshFromSources, _refresh)
    container.define(CloseCampaign, _close_campaign)
    container.define(SupersedeCampaignUC, _supersede)
    container.define(GetPublishedCampaign, _get_published)

    # --- Admin Hard-Delete Registry (Tier 1) ---
    register_admin_delete(
        entity_type="project",
        table="projects",
        label_field="name",
    )
    register_admin_delete(
        entity_type="collection",
        table="collections",
        label_field="name",
    )
    register_admin_delete(
        entity_type="saved_search",
        table="saved_searches",
        label_field="name",
    )


def build_research_org_admin_repos(uow) -> dict:
    """Build the repo map for research-organization Tier-1 admin deletes."""
    from chem_vault.application.admin._adapter import RepoAdapter

    return {
        "project": RepoAdapter(SQLAlchemyProjectRepository(uow), find="find_by_id_in_workspace"),
        "collection": RepoAdapter(SQLAlchemyCollectionRepository(uow), find="find_by_id_in_workspace"),
        "saved_search": RepoAdapter(SQLAlchemySavedSearchRepository(uow), find="find_by_id_in_workspace"),
    }
