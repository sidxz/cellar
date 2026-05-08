"""Integration tests for project data scoping."""

from __future__ import annotations

import uuid

import pytest

from chem_vault.domain.research_organization.project import Project
from chem_vault.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.project_member_repository import (
    SQLAlchemyProjectMemberRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.integration
class TestProjectMemberRepository:
    """Tests for the project_members table operations."""

    async def _create_project(
        self, uow: AsyncUnitOfWork, ws_id: uuid.UUID, name: str, user_id: uuid.UUID
    ) -> Project:
        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            p = Project.create(workspace_id=ws_id, name=name, created_by=user_id)
            await repo.save(p)
            await uow.commit()
        return p

    async def test_add_and_find_members(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        project = await self._create_project(uow, ws_id, "Alpha", user_a)

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.add_member(ws_id, project.id, user_a, ProjectRole.MANAGER)
            await repo.add_member(ws_id, project.id, user_b, ProjectRole.VIEWER)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            members = await repo.find_members(ws_id, project.id)
            assert len(members) == 2
            roles = {m.user_id: m.role for m in members}
            assert roles[user_a] == ProjectRole.MANAGER
            assert roles[user_b] == ProjectRole.VIEWER

    async def test_remove_member(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        project = await self._create_project(uow, ws_id, "Beta", user_a)

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.add_member(ws_id, project.id, user_a, ProjectRole.MANAGER)
            await repo.add_member(ws_id, project.id, user_b, ProjectRole.EDITOR)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.remove_member(ws_id, project.id, user_b)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            members = await repo.find_members(ws_id, project.id)
            assert len(members) == 1
            assert members[0].user_id == user_a

    async def test_update_role(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        project = await self._create_project(uow, ws_id, "Gamma", user_a)

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.add_member(ws_id, project.id, user_a, ProjectRole.VIEWER)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.update_role(ws_id, project.id, user_a, ProjectRole.MANAGER)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            role = await repo.get_role(ws_id, project.id, user_a)
            assert role == ProjectRole.MANAGER

    async def test_find_accessible_project_ids(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        p1 = await self._create_project(uow, ws_id, "P1", user_a)
        p2 = await self._create_project(uow, ws_id, "P2", user_a)
        p3 = await self._create_project(uow, ws_id, "P3", user_a)

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.add_member(ws_id, p1.id, user_b, ProjectRole.VIEWER)
            await repo.add_member(ws_id, p2.id, user_b, ProjectRole.EDITOR)
            # user_b is NOT in p3
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            ids = await repo.find_accessible_project_ids(ws_id, user_b)
            assert set(ids) == {p1.id, p2.id}

    async def test_add_member_idempotent(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        project = await self._create_project(uow, ws_id, "Delta", user_a)

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            await repo.add_member(ws_id, project.id, user_a, ProjectRole.MANAGER)
            await repo.add_member(ws_id, project.id, user_a, ProjectRole.MANAGER)  # duplicate
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            members = await repo.find_members(ws_id, project.id)
            assert len(members) == 1

    async def test_get_role_returns_none_for_nonmember(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id = uuid.uuid4()
        user_a = uuid.uuid4()
        project = await self._create_project(uow, ws_id, "Epsilon", user_a)

        async with uow:
            repo = SQLAlchemyProjectMemberRepository(uow)
            role = await repo.get_role(ws_id, project.id, uuid.uuid4())
            assert role is None


# ---------------------------------------------------------------------------
# Molecule-project association tests (added in Task 6)
# ---------------------------------------------------------------------------

import sqlalchemy as sa  # noqa: E402

from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E402
    SQLAlchemyMoleculeRepository,
)


async def _insert_molecule_raw(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID, reg_num: str
) -> None:
    """Insert a minimal molecule row directly via SQL (avoids full domain constructor)."""
    org_id = ws_id  # reuse workspace_id as org_id deterministically
    async with uow:
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
                "VALUES (:id, :ws, :name, 'small_molecule', 'undisclosed', "
                "'approved', 'virtual', 'registered', :reg, :org, 1)"
            ),
            {"id": mol_id, "ws": ws_id, "name": f"Mol-{reg_num}", "reg": reg_num, "org": org_id},
        )
        await uow.commit()


@pytest.mark.integration
class TestMoleculeProjectAssociation:
    """Tests for molecule_projects join table operations on MoleculeRepository."""

    async def _setup(
        self, uow: AsyncUnitOfWork
    ) -> tuple[uuid.UUID, Project, Project, uuid.UUID, uuid.UUID, uuid.UUID]:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create two projects
        async with uow:
            proj_repo = SQLAlchemyProjectRepository(uow)
            p1 = Project.create(workspace_id=ws_id, name="Kinase", created_by=user_id)
            p2 = Project.create(workspace_id=ws_id, name="GPCR", created_by=user_id)
            await proj_repo.save(p1)
            await proj_repo.save(p2)
            await uow.commit()

        # Create three molecules via raw SQL: m1 in Kinase, m2 in GPCR, m3 unscoped
        m1_id = uuid.uuid4()
        m2_id = uuid.uuid4()
        m3_id = uuid.uuid4()

        await _insert_molecule_raw(uow, m1_id, ws_id, f"CV-{m1_id.hex[:5]}")
        await _insert_molecule_raw(uow, m2_id, ws_id, f"CV-{m2_id.hex[:5]}")
        await _insert_molecule_raw(uow, m3_id, ws_id, f"CV-{m3_id.hex[:5]}")

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            await mol_repo.add_to_project(ws_id, m1_id, p1.id)
            await mol_repo.add_to_project(ws_id, m2_id, p2.id)
            await uow.commit()

        return ws_id, p1, p2, m1_id, m2_id, m3_id

    async def test_add_and_find_project_ids(self, uow: AsyncUnitOfWork) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            ids = await mol_repo.find_project_ids(ws_id, m1_id)
            assert ids == [p1.id]

            ids = await mol_repo.find_project_ids(ws_id, m3_id)
            assert ids == []

    async def test_add_to_project_idempotent(self, uow: AsyncUnitOfWork) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            await mol_repo.add_to_project(ws_id, m1_id, p1.id)  # duplicate
            await uow.commit()

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            ids = await mol_repo.find_project_ids(ws_id, m1_id)
            assert ids == [p1.id]

    async def test_remove_from_project(self, uow: AsyncUnitOfWork) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            await mol_repo.remove_from_project(ws_id, m1_id, p1.id)
            await uow.commit()

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            ids = await mol_repo.find_project_ids(ws_id, m1_id)
            assert ids == []

    async def test_find_active_with_project_filter(self, uow: AsyncUnitOfWork) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        # User with access to p1 only: should see m1 (in p1) + m3 (unscoped)
        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            mols = await mol_repo.find_active(ws_id, project_ids=[p1.id])
            mol_ids = {m.id for m in mols}
            assert m1_id in mol_ids
            assert m3_id in mol_ids
            assert m2_id not in mol_ids

    async def test_find_active_no_project_filter_returns_all(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        # Admin (project_ids=None): should see all
        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            mols = await mol_repo.find_active(ws_id, project_ids=None)
            mol_ids = {m.id for m in mols}
            assert {m1_id, m2_id, m3_id} <= mol_ids

    async def test_find_active_empty_project_ids_returns_unscoped_only(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        # User with no projects: should see only m3 (unscoped)
        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            mols = await mol_repo.find_active(ws_id, project_ids=[])
            mol_ids = {m.id for m in mols}
            assert mol_ids == {m3_id}
