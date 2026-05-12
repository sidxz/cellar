"""Integration tests for research organization persistence."""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.saved_search import (
    SavedSearch,
    SearchVisibility,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.saved_search_repository import (
    SQLAlchemySavedSearchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Helper — insert minimal molecule row for membership tests
# ---------------------------------------------------------------------------


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
    """Insert a minimal molecule row for membership tests.

    We need an organization row first (FK constraint on originating_org_id),
    so we insert one with the workspace_id as a deterministic org_id.
    """
    org_id = ws_id  # reuse workspace_id as org_id — only created once
    async with uow:
        # Ensure org exists (ignore conflict on duplicate)
        await uow.session.execute(
            sa.text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": org_id, "ws": ws_id},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecules (id, workspace_id, name, molecule_type, "
                "structure_status, registration_status, synthesis_status, "
                "lifecycle_stage, registration_number, originating_org_id, version) "
                "VALUES (:id, :ws, 'Test Mol', 'small_molecule', 'disclosed', "
                "'approved', 'virtual', 'registered', :reg, :org, 1)"
            ),
            {"id": mol_id, "ws": ws_id, "reg": f"CV-{mol_id.hex[:6]}", "org": org_id},
        )
        await uow.commit()


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class TestProjectRepository:
    async def test_save_and_find_by_id(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            project = Project.create(
                workspace_id=ws_id,
                name="Kinase Discovery",
                description="JAK2 inhibitors",
                created_by=user_id,
            )
            await repo.save(project)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            loaded = await repo.find_by_id(project.id)
            assert loaded is not None
            assert loaded.name == "Kinase Discovery"
            assert loaded.description == "JAK2 inhibitors"
            assert loaded.status.value == "active"
            assert loaded.created_by == user_id
            assert loaded.version == 1

    async def test_update_with_version_increment(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            project = Project(
                id=project_id,
                workspace_id=ws_id,
                name="Old Name",
                created_by=user_id,
            )
            await repo.save(project)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            project = await repo.find_by_id(project_id)
            assert project is not None
            project.update(name="New Name")
            await repo.save(project)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            project = await repo.find_by_id(project_id)
            assert project is not None
            assert project.name == "New Name"
            assert project.version == 2

    async def test_find_by_workspace(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            await repo.save(
                Project.create(workspace_id=ws_id, name="Alpha", created_by=user_id)
            )
            await repo.save(
                Project.create(workspace_id=ws_id, name="Beta", created_by=user_id)
            )
            # Different workspace — should not appear
            await repo.save(
                Project.create(
                    workspace_id=uuid.uuid4(), name="Other", created_by=user_id
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            projects = await repo.find_by_workspace(ws_id)
            assert len(projects) == 2
            assert projects[0].name == "Alpha"  # ordered by name
            assert projects[1].name == "Beta"

    async def test_find_by_name(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            await repo.save(
                Project.create(
                    workspace_id=ws_id, name="GPCR Library", created_by=user_id
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            found = await repo.find_by_name(ws_id, "GPCR Library")
            assert found is not None
            assert found.name == "GPCR Library"

            not_found = await repo.find_by_name(ws_id, "Nonexistent")
            assert not_found is None


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


class TestCollectionRepository:
    async def test_save_and_find_by_id(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            collection = Collection.create(
                workspace_id=ws_id,
                name="Hit List",
                description="Primary screen hits",
                created_by=user_id,
            )
            await repo.save(collection)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id(collection.id)
            assert loaded is not None
            assert loaded.name == "Hit List"
            assert loaded.description == "Primary screen hits"
            assert loaded.molecule_count == 0

    async def test_find_by_workspace_with_counts(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        # Insert a molecule for membership
        await _insert_molecule(uow, mol_id, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c1 = Collection.create(
                workspace_id=ws_id, name="With Mols", created_by=user_id
            )
            c2 = Collection.create(
                workspace_id=ws_id, name="Empty", created_by=user_id
            )
            await repo.save(c1)
            await repo.save(c2)
            await uow.commit()

        # Add molecule to first collection
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c1.id, [mol_id])
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            collections = await repo.find_by_workspace(ws_id)
            assert len(collections) == 2
            by_name = {c.name: c for c in collections}
            assert by_name["Empty"].molecule_count == 0
            assert by_name["With Mols"].molecule_count == 1

    async def test_delete_cascades_membership(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        await _insert_molecule(uow, mol_id, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Deletable", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c.id, [mol_id])
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.delete(ws_id, c.id)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            assert await repo.find_by_id(c.id) is None
            # Membership rows also gone (CASCADE)
            count = await repo.count_molecules(ws_id, c.id)
            assert count == 0


# ---------------------------------------------------------------------------
# Collection Membership
# ---------------------------------------------------------------------------


class TestCollectionMembership:
    async def test_add_and_count(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol1 = uuid.uuid4()
        mol2 = uuid.uuid4()

        await _insert_molecule(uow, mol1, ws_id)
        await _insert_molecule(uow, mol2, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Membership Test", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            added = await repo.add_molecules(ws_id, c.id, [mol1, mol2])
            assert added == 2
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            assert await repo.count_molecules(ws_id, c.id) == 2

    async def test_add_duplicate_ignored(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        await _insert_molecule(uow, mol_id, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Dedup Test", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c.id, [mol_id])
            await uow.commit()

        # Adding same molecule again — should be ignored
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            added = await repo.add_molecules(ws_id, c.id, [mol_id])
            assert added == 0
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            assert await repo.count_molecules(ws_id, c.id) == 1

    async def test_remove(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol1 = uuid.uuid4()
        mol2 = uuid.uuid4()

        await _insert_molecule(uow, mol1, ws_id)
        await _insert_molecule(uow, mol2, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Remove Test", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c.id, [mol1, mol2])
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            removed = await repo.remove_molecules(ws_id, c.id, [mol1])
            assert removed == 1
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            assert await repo.count_molecules(ws_id, c.id) == 1

    async def test_get_molecule_ids_paginated(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mols = [uuid.uuid4() for _ in range(5)]

        for m in mols:
            await _insert_molecule(uow, m, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Paginated", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c.id, mols)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            page1 = await repo.get_molecule_ids(ws_id, c.id, offset=0, limit=3)
            assert len(page1) == 3
            page2 = await repo.get_molecule_ids(ws_id, c.id, offset=3, limit=3)
            assert len(page2) == 2
            # All 5 molecules accounted for
            assert set(page1 + page2) == set(mols)

    async def test_replace_molecule_swap(self, uow: AsyncUnitOfWork) -> None:
        """Source mol in collection, target not — simple UPDATE."""
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        source = uuid.uuid4()
        target = uuid.uuid4()

        await _insert_molecule(uow, source, ws_id)
        await _insert_molecule(uow, target, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Swap Test", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c.id, [source])
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            updated = await repo.replace_molecule(ws_id, source, target)
            assert updated == 1
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            mol_ids = await repo.get_molecule_ids(ws_id, c.id)
            assert target in mol_ids
            assert source not in mol_ids

    async def test_replace_molecule_dedup(self, uow: AsyncUnitOfWork) -> None:
        """Both source and target in same collection — source row deleted, target kept."""
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        source = uuid.uuid4()
        target = uuid.uuid4()

        await _insert_molecule(uow, source, ws_id)
        await _insert_molecule(uow, target, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            c = Collection.create(
                workspace_id=ws_id, name="Dedup Merge", created_by=user_id
            )
            await repo.save(c)
            await uow.commit()

        # Add both to the same collection
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.add_molecules(ws_id, c.id, [source, target])
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            updated = await repo.replace_molecule(ws_id, source, target)
            # Source row deleted in step 1 (dedup), no rows left to update
            assert updated == 0
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            mol_ids = await repo.get_molecule_ids(ws_id, c.id)
            assert mol_ids == [target]
            assert await repo.count_molecules(ws_id, c.id) == 1


# ---------------------------------------------------------------------------
# SavedSearch
# ---------------------------------------------------------------------------


class TestSavedSearchRepository:
    async def test_save_and_find_by_id(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            search = SavedSearch.create(
                workspace_id=ws_id,
                name="JAK2 Hits",
                query={"target": "JAK2", "ic50_lt": 100},
                columns={"visible": ["name", "ic50"]},
                created_by=user_id,
            )
            await repo.save(search)
            await uow.commit()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            loaded = await repo.find_by_id(search.id)
            assert loaded is not None
            assert loaded.name == "JAK2 Hits"
            assert loaded.query == {"target": "JAK2", "ic50_lt": 100}
            assert loaded.columns == {"visible": ["name", "ic50"]}
            assert loaded.visibility == SearchVisibility.PRIVATE
            assert loaded.created_by == user_id

    async def test_find_by_workspace(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            await repo.save(
                SavedSearch.create(
                    workspace_id=ws_id,
                    name="Alpha Search",
                    query={"type": "substructure"},
                    created_by=user_id,
                )
            )
            await repo.save(
                SavedSearch.create(
                    workspace_id=ws_id,
                    name="Beta Search",
                    query={"type": "similarity"},
                    created_by=user_id,
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            searches = await repo.find_by_workspace(ws_id)
            assert len(searches) == 2
            assert searches[0].name == "Alpha Search"
            assert searches[1].name == "Beta Search"

    async def test_find_by_creator(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            await repo.save(
                SavedSearch.create(
                    workspace_id=ws_id,
                    name="User A Search",
                    query={"q": "aspirin"},
                    created_by=user_a,
                )
            )
            await repo.save(
                SavedSearch.create(
                    workspace_id=ws_id,
                    name="User B Search",
                    query={"q": "caffeine"},
                    created_by=user_b,
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            results = await repo.find_by_creator(ws_id, user_a)
            assert len(results) == 1
            assert results[0].name == "User A Search"

    async def test_delete(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            search = SavedSearch.create(
                workspace_id=ws_id,
                name="Deletable",
                query={"delete": True},
                created_by=user_id,
            )
            await repo.save(search)
            await uow.commit()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            await repo.delete(ws_id, search.id)
            await uow.commit()

        async with uow:
            repo = SQLAlchemySavedSearchRepository(uow)
            assert await repo.find_by_id(search.id) is None
