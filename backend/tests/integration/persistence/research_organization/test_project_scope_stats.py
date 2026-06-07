"""Integration test for the extended project scope-stats query."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
    ProjectMemberModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


async def test_scope_stats_includes_campaigns_members_activity(session_factory) -> None:
    ws = uuid.uuid4()
    project_id = uuid.uuid4()
    user1, user2 = uuid.uuid4(), uuid.uuid4()
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 6, 1, tzinfo=UTC)

    async with session_factory() as s:
        s.add(
            ProjectModel(
                id=project_id,
                workspace_id=ws,
                name="P",
                status="active",
                created_by=user1,
                updated_at=older,
            )
        )
        # project_members has a real FK to projects but no ORM relationship,
        # so the unit-of-work can't infer the insert order — flush the project
        # row first so the membership FK resolves.
        await s.flush()
        s.add(
            CampaignModel(
                id=uuid.uuid4(),
                workspace_id=ws,
                project_id=project_id,
                name="C1",
                status="draft",
                created_by=user1,
                updated_at=newer,
            )
        )
        s.add(
            CampaignModel(
                id=uuid.uuid4(),
                workspace_id=ws,
                project_id=project_id,
                name="C2",
                status="closed",
                created_by=user1,
                updated_at=older,
            )
        )
        s.add(ProjectMemberModel(project_id=project_id, user_id=user1, role="manager"))
        s.add(ProjectMemberModel(project_id=project_id, user_id=user2, role="viewer"))
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProjectRepository(uow)
        stats = await repo.get_scope_stats(ws, [project_id])

    s1 = stats[project_id]
    assert s1.campaign_count == 2
    # greatest(project.updated_at=older, max(campaign.updated_at)=newer) == newer
    assert s1.last_activity_at == newer
    assert s1.member_count == 2
    assert set(s1.member_ids) == {user1, user2}


async def test_scope_stats_no_campaigns_uses_project_updated_at(session_factory) -> None:
    ws = uuid.uuid4()
    project_id = uuid.uuid4()
    proj_updated = datetime(2026, 3, 3, tzinfo=UTC)

    async with session_factory() as s:
        s.add(
            ProjectModel(
                id=project_id,
                workspace_id=ws,
                name="Quiet",
                status="active",
                created_by=uuid.uuid4(),
                updated_at=proj_updated,
            )
        )
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProjectRepository(uow)
        stats = await repo.get_scope_stats(ws, [project_id])

    s1 = stats[project_id]
    assert s1.campaign_count == 0
    assert s1.last_activity_at == proj_updated
    assert s1.member_count == 0
    assert s1.member_ids == ()


async def test_scope_stats_member_ids_capped_at_five_oldest(session_factory) -> None:
    """member_count is the full membership; member_ids is the 5 oldest, in order.

    ProjectMemberModel.created_at carries a server_default but no Python-side
    default, so explicit values are honoured on insert (no post-flush update
    needed). Seven members with distinct, monotonically increasing created_at
    values pin both the count (7) and the deterministic oldest-5 avatar slice.
    """
    ws = uuid.uuid4()
    project_id = uuid.uuid4()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Build (user_id, created_at) pairs with strictly increasing timestamps so
    # the oldest-5 ordering is unambiguous regardless of the user_id tiebreaker.
    members = [(uuid.uuid4(), base.replace(day=1 + i)) for i in range(7)]
    expected_oldest_five = tuple(uid for uid, _ in members[:5])

    async with session_factory() as s:
        s.add(
            ProjectModel(
                id=project_id,
                workspace_id=ws,
                name="Crowded",
                status="active",
                created_by=members[0][0],
                updated_at=base,
            )
        )
        await s.flush()
        for uid, created in members:
            s.add(
                ProjectMemberModel(
                    project_id=project_id,
                    user_id=uid,
                    role="viewer",
                    created_at=created,
                )
            )
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProjectRepository(uow)
        stats = await repo.get_scope_stats(ws, [project_id])

    s1 = stats[project_id]
    assert s1.member_count == 7
    assert len(s1.member_ids) == 5
    assert s1.member_ids == expected_oldest_five
