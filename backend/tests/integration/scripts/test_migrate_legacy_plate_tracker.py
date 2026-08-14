from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_sync_repository import (
    CddPlateSyncRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

from scripts.migrate_legacy_plate_tracker import LegacyData, LegacyPlate, match_plates

VAULT = "1"
REGISTRAR = uuid.uuid4()

# The test DB is SESSION-SCOPED and session_factory COMMITS without rollback
# (tests/conftest.py: engine/session_factory/postgres_container are scope="session").
# => every test MUST use a unique per-test workspace_id (and owner_org_id) so
# committed data from sibling tests can't contaminate scoped assertions.


async def _seed_plate(session, *, plate_id, barcode, ws, cdd_plate_id=None, owner_org_id=None):
    # registered_plates NOT-NULL cols: barcode, plate_label, format, plate_type,
    # registered_by, workspace_id (status has a server_default; created_at/updated_at too).
    # format MUST be a valid PlateFormat value → "96" (NOT "96_well").
    await session.execute(sa.text(
        "INSERT INTO registered_plates (id, workspace_id, owner_org_id, barcode, "
        "plate_label, format, plate_type, status, registered_by, version) "
        "VALUES (:id, :ws, :owner, :bc, :bc, '96', 'assay', 'registered', :rb, 1)"
    ), {"id": plate_id, "ws": ws, "owner": owner_org_id, "bc": barcode, "rb": REGISTRAR})
    if cdd_plate_id is not None:
        await session.execute(sa.text(
            "INSERT INTO cdd_plate_sync (id, workspace_id, cdd_vault_id, cdd_plate_id, "
            "plate_id, created_at, updated_at) VALUES "
            "(gen_random_uuid(), :ws, :vault, :cpid, :pid, now(), now())"
        ), {"ws": ws, "vault": VAULT, "cpid": cdd_plate_id, "pid": plate_id})


@pytest.mark.asyncio
async def test_match_plates_cdd_then_barcode_then_unmatched(session_factory):
    ws = uuid.uuid4()
    cdd_plate = uuid.uuid4()
    bc_plate = uuid.uuid4()
    async with session_factory() as s:
        await _seed_plate(s, plate_id=cdd_plate, barcode="900001", ws=ws, cdd_plate_id=555)
        await _seed_plate(s, plate_id=bc_plate, barcode="000042", ws=ws)  # matched by pad-left
        await s.commit()

    legacy = LegacyData(plates=[
        LegacyPlate(1, 555, "irrelevant", "P1", "Active", "MASTER", None),   # cdd hit
        LegacyPlate(2, None, "42", "P2", "Active", "MASTER", None),          # barcode hit → pad to 000042
        LegacyPlate(3, 999, "no-such", "P3", "Active", "MASTER", None),      # unmatched
    ])
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        plate_repo = SQLAlchemyRegisteredPlateRepository(uow)
        cdd_repo = CddPlateSyncRepository(uow)
        matched, unmatched = await match_plates(
            legacy, plate_repo=plate_repo, cdd_repo=cdd_repo,
            workspace_id=ws, cdd_vault_id=VAULT,
        )
    assert matched[1] == cdd_plate
    assert matched[2] == bc_plate
    assert 3 not in matched
    assert [u.legacy_plate_id for u in unmatched] == [3]
