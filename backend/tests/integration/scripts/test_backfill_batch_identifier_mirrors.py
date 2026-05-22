"""Integration: backfill_batch_identifier_mirrors is idempotent.

Seeds a workspace with 1 molecule × 2 synonyms × 2 batches, then runs
run_backfill twice and verifies:
  - First run: created=4, skipped=0, malformed=0
  - Second run: created=0, skipped=4, malformed=0

Uses the session_factory fixture from the root conftest (testcontainers-backed).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.enums import BatchSource
from cellar.domain.shared.value_objects import Amount, AmountUnit, BatchNumber
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

from scripts.backfill_batch_identifier_mirrors import run_backfill


# ---------------------------------------------------------------------------
# Helpers — self-contained raw-SQL seed (no shared fixtures from inventory/)
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


async def _seed_molecule_with_synonyms_and_batches(
    session_factory,
    workspace_id: uuid.UUID,
    actor: uuid.UUID,
) -> tuple[uuid.UUID, list[uuid.UUID], list[uuid.UUID]]:
    """
    Inserts:
      - organization
      - 1 molecule
      - 2 molecule_identifiers ("SACC-0001", "VENDOR-FOO")
      - 2 batches ("CC-000001-001", "CC-000001-002")

    Returns (molecule_id, [ident_id_1, ident_id_2], [batch_id_1, batch_id_2]).
    """
    mol_id = uuid.uuid4()
    ident1_id = uuid.uuid4()
    ident2_id = uuid.uuid4()
    batch1_id = uuid.uuid4()
    batch2_id = uuid.uuid4()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _ensure_org(uow.session, workspace_id, workspace_id)

        # Molecule
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

        # Two molecule identifiers
        for ident_id, ident_val in [(ident1_id, "SACC-0001"), (ident2_id, "VENDOR-FOO")]:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO molecule_identifiers "
                    "(id, molecule_id, workspace_id, identifier, identifier_type, "
                    "source, registered_by) "
                    "VALUES (:id, :mol, :ws, :ident, 'custom', 'Registration', :actor)"
                ),
                {"id": ident_id, "mol": mol_id, "ws": workspace_id,
                 "ident": ident_val, "actor": actor},
            )

        # Two batches
        for batch_id, batch_num in [
            (batch1_id, "CC-000001-001"),
            (batch2_id, "CC-000001-002"),
        ]:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO batches "
                    "(id, workspace_id, molecule_id, batch_number, amount_value, "
                    "amount_unit, source, chemist, version) "
                    "VALUES (:id, :ws, :mol, :bnum, 10.0, 'mg', 'synthesized', :actor, 1)"
                ),
                {
                    "id": batch_id, "ws": workspace_id, "mol": mol_id,
                    "bnum": batch_num, "actor": actor,
                },
            )

        await uow.commit()

    return mol_id, [ident1_id, ident2_id], [batch1_id, batch2_id]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_idempotent_and_creates_expected_mirrors(
    session_factory,
) -> None:
    """run_backfill creates 4 mirrors on first call, 0 on second (idempotent)."""
    workspace_id = uuid.uuid4()
    actor = uuid.uuid4()

    mol_id, ident_ids, batch_ids = await _seed_molecule_with_synonyms_and_batches(
        session_factory, workspace_id, actor
    )

    # First run: 2 synonyms × 2 batches = 4 mirrors created.
    stats1 = await run_backfill(session_factory, workspace_id=workspace_id)
    assert stats1["created"] == 4, f"Expected 4 created, got {stats1}"
    assert stats1["skipped"] == 0
    assert stats1["malformed"] == 0

    # Second run: all 4 already exist → all skipped.
    stats2 = await run_backfill(session_factory, workspace_id=workspace_id)
    assert stats2["created"] == 0
    assert stats2["skipped"] == 4, f"Expected 4 skipped, got {stats2}"
    assert stats2["malformed"] == 0
