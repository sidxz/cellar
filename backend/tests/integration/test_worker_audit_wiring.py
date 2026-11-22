"""The Temporal worker wires the same audit catch-all as the API.

Regression for the backlog item "worker dispatches domain events to nobody":
a dispatcher built the way ``worker.py`` builds it must write an audit row,
attributed to the actor the activity set from its ``submitted_by`` input.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.shared.actor_context import set_current_actor
from cellar.domain.chemical_registration.events import MoleculeRegistered
from cellar.infrastructure.messaging.audit_event_handler import register_audit_handler
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher


async def test_worker_dispatcher_writes_audit_row_for_set_actor(
    session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    dispatcher = EventDispatcher()
    register_audit_handler(dispatcher, session_factory)

    actor, molecule_id = uuid.uuid4(), uuid.uuid4()
    event = MoleculeRegistered(
        aggregate_id=molecule_id,
        aggregate_type="Molecule",
        workspace_id=uuid.uuid4(),
        registration_number="CV-000001",
        molecule_type="small_molecule",
    )
    set_current_actor(actor)
    try:
        await dispatcher.dispatch_all([event])
    finally:
        set_current_actor(None)

    row = (
        await db_session.execute(
            text("SELECT user_id, operation_type FROM audit_operations WHERE entity_id = :e"),
            {"e": molecule_id},
        )
    ).one()
    assert row.user_id == actor
    assert row.operation_type == "registration"
