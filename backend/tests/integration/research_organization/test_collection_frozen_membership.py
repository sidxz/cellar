"""Frozen-collection membership-guard integration tests.

These tests exercise the repository-level guards added so that
``add_molecules`` / ``remove_molecules`` reject mutation of frozen
``Collection`` aggregates with :class:`CollectionFrozenError`.
``replace_molecule`` (used by molecule merge) must silently skip
frozen collections — closed campaigns are never retroactively
rewired.

The file follows the same fixture pattern as ``tests/integration/
test_research_organization.py`` (``uow`` fixture from
``tests/conftest.py``).

NOTE: end-to-end execution depends on the 026 migration that adds
the ``is_frozen`` + ``derived_from_campaign_id`` columns on
``collections`` and the corresponding ORM-mapping updates (Task
1.3). Until that ships, the persisted aggregate always rehydrates
with ``is_frozen=False`` regardless of in-memory state, so these
tests are intentionally collected but not run. See the task plan
for the activation point.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.shared.errors import CollectionFrozenError
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
    """Insert a minimal molecule row + originating org (mirrors helper in
    ``test_research_organization.py``)."""
    org_id = ws_id  # reuse ws_id deterministically
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, "
                "is_active, version) "
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
# add_molecules / remove_molecules — guard
# ---------------------------------------------------------------------------


class TestFrozenMembershipGuard:
    async def test_add_molecules_rejected_when_frozen(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        await _insert_molecule(uow, mol_id, ws_id)

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            coll = Collection.create(
                workspace_id=ws_id, name="Frozen Hits", created_by=user_id
            )
            coll.freeze(derived_from_campaign_id=uuid.uuid4())
            await repo.save(coll)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            with pytest.raises(CollectionFrozenError):
                await repo.add_molecules(ws_id, coll.id, [mol_id])

    async def test_remove_molecules_rejected_when_frozen(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mol_id = uuid.uuid4()

        await _insert_molecule(uow, mol_id, ws_id)

        # Create + populate the collection BEFORE freezing so we have
        # something to attempt removal of.
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            coll = Collection.create(
                workspace_id=ws_id, name="Soon Frozen", created_by=user_id
            )
            await repo.save(coll)
            await repo.add_molecules(ws_id, coll.id, [mol_id])
            await uow.commit()

        # Freeze the persisted collection.
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id_in_workspace(ws_id, coll.id)
            assert loaded is not None
            loaded.freeze(derived_from_campaign_id=uuid.uuid4())
            await repo.save(loaded)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            with pytest.raises(CollectionFrozenError):
                await repo.remove_molecules(ws_id, coll.id, [mol_id])

    async def test_replace_molecule_skips_frozen_collections(
        self, uow: AsyncUnitOfWork
    ) -> None:
        """Molecule merge must NOT rewire membership of frozen collections.

        Closed campaigns are historical artifacts; their derived
        Collection's membership is preserved as it was at close.
        """
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        old_mol = uuid.uuid4()
        new_mol = uuid.uuid4()

        await _insert_molecule(uow, old_mol, ws_id)
        await _insert_molecule(uow, new_mol, ws_id)

        # Build two collections: one to freeze, one to keep mutable.
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            frozen = Collection.create(
                workspace_id=ws_id, name="Frozen Hits", created_by=user_id
            )
            mutable = Collection.create(
                workspace_id=ws_id, name="Mutable", created_by=user_id
            )
            await repo.save(frozen)
            await repo.save(mutable)
            await repo.add_molecules(ws_id, frozen.id, [old_mol])
            await repo.add_molecules(ws_id, mutable.id, [old_mol])
            await uow.commit()

        # Freeze the first AFTER membership is set.
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id_in_workspace(ws_id, frozen.id)
            assert loaded is not None
            loaded.freeze(derived_from_campaign_id=uuid.uuid4())
            await repo.save(loaded)
            await uow.commit()

        # Run the rewire — frozen collection must be skipped silently.
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            await repo.replace_molecule(ws_id, old_mol, new_mol)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            mutable_ids = await repo.get_molecule_ids(ws_id, mutable.id)
            frozen_ids = await repo.get_molecule_ids(ws_id, frozen.id)

        # Mutable: rewired.
        assert new_mol in mutable_ids
        assert old_mol not in mutable_ids
        # Frozen: untouched.
        assert old_mol in frozen_ids
        assert new_mol not in frozen_ids
