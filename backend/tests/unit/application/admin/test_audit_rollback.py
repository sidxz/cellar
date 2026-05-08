"""Unit tests: audit failure inside the deletion transaction must roll back the delete.

The production fix moves audit.record() *before* uow.commit() so that the two
writes share the same transaction.  These tests verify:

1. AdminHardDelete — if audit.record() raises, uow.commit() is never called and
   the mock repo's delete() is effectively rolled back (UoW exits without commit).
2. CascadeDelete — same guarantee: audit failure prevents commit.

Both tests use a fully in-memory mock UoW + mock repo so they run fast and
without a real DB.  The key assertion in each case is:

    - audit.record() was called (inside the UoW block)
    - uow.commit() was NOT called (transaction stayed open, then rolled back)
    - the use case returns a Failure (the exception propagated)

Because the UoW context manager's __aexit__ calls rollback on any unhandled
exception, "commit was never called" is sufficient to prove atomicity.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chem_vault.application.admin.admin_delete_registry import register_admin_delete
from chem_vault.application.admin.admin_hard_delete import (
    AdminHardDelete,
    AdminHardDeleteCommand,
)
from chem_vault.application.admin.cascade_delete import (
    CascadeDelete,
    CascadeDeleteCommand,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _admin_auth(workspace_id: uuid.UUID) -> MagicMock:
    auth = MagicMock()
    auth.workspace_id = workspace_id
    auth.user_id = uuid.uuid4()
    auth.workspace_role = "admin"
    auth.is_admin = True
    auth.has_role = lambda r: True
    return auth


class _FakeUoW:
    """Minimal async context-manager UoW that tracks whether commit() was called."""

    def __init__(self, session: MagicMock) -> None:
        self.session = session
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> list:
        self.committed = True
        return []

    async def rollback(self) -> None:
        self.rolled_back = True

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.rollback()
        # Don't suppress the exception — let it propagate.


# ---------------------------------------------------------------------------
# AdminHardDelete — audit failure rolls back delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_hard_delete_audit_failure_prevents_commit(
    _admin_delete_registry_isolation,
) -> None:
    """If audit.record() raises inside the UoW, commit() must not be called."""
    workspace_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    # Fake entity returned by the repo
    fake_entity = MagicMock()
    fake_entity.__dataclass_fields__ = {}
    fake_entity.__dict__ = {"id": entity_id, "name": "test"}

    # Fake repo: find_by_id returns an object, delete is a no-op
    fake_repo = MagicMock()
    fake_repo.find_by_id = AsyncMock(return_value=fake_entity)
    fake_repo.delete = AsyncMock()

    # Register the entity type so get_entry() resolves it
    register_admin_delete(
        entity_type="vocabulary",
        table="controlled_vocabularies",
        label_field="name",
    )

    # UoW with a mock session
    fake_session = MagicMock()
    fake_uow = _FakeUoW(session=fake_session)

    # Audit service raises on record()
    boom = RuntimeError("audit DB is down")
    fake_audit = MagicMock()
    fake_audit.record = AsyncMock(side_effect=boom)

    # Patch find_inbound_references so it returns no blockers
    with (
        patch(
            "chem_vault.application.admin.admin_hard_delete.find_inbound_references",
            new=AsyncMock(return_value=[]),
        ),
        pytest.raises(RuntimeError, match="audit DB is down"),
    ):
        # repos is a dict mapping entity_type -> repo; no container needed
        uc = AdminHardDelete(
            uow=fake_uow,
            audit=fake_audit,
            repos={"vocabulary": fake_repo},
        )
        await uc(
            AdminHardDeleteCommand(
                workspace_id=workspace_id,
                entity_type="vocabulary",
                entity_id=entity_id,
                reason="cleanup",
            ),
            auth=_admin_auth(workspace_id),
        )

    # The exception propagated out of the UoW block — commit() must NOT have been called.
    assert not fake_uow.committed, (
        "uow.commit() was called even though audit.record() raised — "
        "the delete would be permanent without an audit trail."
    )
    assert fake_uow.rolled_back, "UoW should have rolled back on exception"


# ---------------------------------------------------------------------------
# CascadeDelete — audit failure rolls back cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_delete_audit_failure_prevents_commit(
    _admin_delete_registry_isolation,
) -> None:
    """If audit.record() raises inside the cascade UoW, commit() must not be called."""
    workspace_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    proto_name = "My Protocol"

    # Register protocol as a Tier-2 entity for this test
    register_admin_delete(
        entity_type="protocol",
        table="protocols",
        label_field="name",
    )

    fake_session = MagicMock()
    fake_uow = _FakeUoW(session=fake_session)

    # Audit service raises on record()
    boom = RuntimeError("audit DB is down")
    fake_audit = MagicMock()
    fake_audit.record = AsyncMock(side_effect=boom)

    # Fake cascade service that "deletes" successfully and returns entries
    fake_entries: list = []
    fake_cascade_service = MagicMock()
    fake_cascade_service.execute = AsyncMock(return_value=fake_entries)

    with (
        patch(
            "chem_vault.application.admin.cascade_delete._fetch_label",
            new=AsyncMock(return_value=proto_name),
        ),
        patch(
            "chem_vault.application.admin.cascade_delete.TIER2_ENTITY_TYPES",
            new={"protocol"},
        ),
        pytest.raises(RuntimeError, match="audit DB is down"),
    ):
        uc = CascadeDelete(
            uow=fake_uow,
            audit=fake_audit,
            cascade_service=fake_cascade_service,
        )
        await uc(
            CascadeDeleteCommand(
                workspace_id=workspace_id,
                entity_type="protocol",
                entity_id=entity_id,
                typed_name=proto_name,
                reason="cleanup",
            ),
            auth=_admin_auth(workspace_id),
        )

    # The exception propagated out of the UoW block — commit() must NOT have been called.
    assert not fake_uow.committed, (
        "uow.commit() was called even though audit.record() raised — "
        "the cascade would be permanent without an audit trail."
    )
    assert fake_uow.rolled_back, "UoW should have rolled back on exception"
