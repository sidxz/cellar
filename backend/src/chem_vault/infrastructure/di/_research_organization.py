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
from chem_vault.application.research_organization.execute_search import ExecuteSearch
from chem_vault.application.research_organization.get_collection import (
    GetCollection,
    ListCollections,
)
from chem_vault.application.research_organization.get_collections_for_molecule import (
    ListCollectionsForMolecule,
)
from chem_vault.application.research_organization.get_project import GetProject, ListProjects
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


def register_research_organization(container: Container) -> None:
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
