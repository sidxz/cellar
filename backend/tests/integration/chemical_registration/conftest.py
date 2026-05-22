"""Shared fixtures for chemical_registration integration tests."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth


# ---------------------------------------------------------------------------
# Event dispatcher stub
# ---------------------------------------------------------------------------


class _FakeDispatcher:
    def __init__(self) -> None:
        self.dispatched: list = []

    async def dispatch_all(self, events) -> None:
        self.dispatched.extend(events)


@pytest.fixture
def fake_event_dispatcher() -> _FakeDispatcher:
    return _FakeDispatcher()


@pytest.fixture
def editor_auth() -> FakeAuth:
    return FakeAuth(role="editor")


# ---------------------------------------------------------------------------
# seeded_workspace_and_molecule
#
# Inserts:
#   - one organization row (needed as FK target)
#   - one molecule (undisclosed)
#   - one molecule_identifier ("SACC-0001") on that molecule
#
# Returns (workspace_id, molecule_id, identifier_id, actor_id)
# ---------------------------------------------------------------------------


async def _ensure_org(session, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": org_id, "ws": ws_id},
    )


@pytest.fixture
async def seeded_workspace_and_molecule(
    session_factory,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed a workspace, molecule, and one molecule identifier.

    Returns (workspace_id, molecule_id, identifier_id, actor_id).
    """
    workspace_id = uuid.uuid4()
    actor = uuid.uuid4()
    mol_id = uuid.uuid4()
    ident_id = uuid.uuid4()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _ensure_org(uow.session, workspace_id, workspace_id)
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecules "
                "(id, workspace_id, name, molecule_type, structure_status, "
                "registration_status, synthesis_status, lifecycle_stage, "
                "registration_number, originating_org_id, version) "
                "VALUES (:id, :ws, 'Test Mol', 'small_molecule', 'undisclosed', "
                "'approved', 'virtual', 'registered', 'CC-000001', :org, 1)"
            ),
            {"id": mol_id, "ws": workspace_id, "org": workspace_id},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecule_identifiers "
                "(id, molecule_id, workspace_id, identifier, identifier_type, "
                "source, registered_by) "
                "VALUES (:id, :mol, :ws, 'SACC-0001', 'custom', 'Registration', :actor)"
            ),
            {"id": ident_id, "mol": mol_id, "ws": workspace_id, "actor": actor},
        )
        await uow.commit()

    return workspace_id, mol_id, ident_id, actor
