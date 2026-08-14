from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from scripts.migrate_legacy_plate_tracker import (
    LegacyData,
    LegacyLibrary,
    LegacyPlate,
    LegacySet,
    LegacySetPlate,
    apply_group_tree,
    apply_plate_ownership,
    assign_plates_to_groups,
    backfill_null_owner,
    match_plates,
    plan_group_tree,
)

from cellar.domain.inventory.enums import PlateStatus, PlateType
from cellar.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_sync_repository import (
    CddPlateSyncRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    RegisteredPlateTagLinkRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

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
    fallback = uuid.uuid4()
    async with session_factory() as s:
        await _seed_plate(s, plate_id=cdd_plate, barcode="900001", ws=ws, cdd_plate_id=555)
        await _seed_plate(s, plate_id=bc_plate, barcode="000042", ws=ws)  # matched by pad-left
        # cdd_plate_id present but NO sync row → must fall through to barcode
        await _seed_plate(s, plate_id=fallback, barcode="900002", ws=ws)
        await s.commit()

    legacy = LegacyData(plates=[
        LegacyPlate(1, 555, "irrelevant", "P1", "Active", "MASTER", None),   # cdd hit
        LegacyPlate(2, None, "42", "P2", "Active", "MASTER", None),          # barcode hit → 000042
        LegacyPlate(3, 999, "no-such", "P3", "Active", "MASTER", None),      # unmatched
        LegacyPlate(4, 777, "900002", "P4", "Active", "MASTER", None),       # cdd miss → barcode
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
    assert matched[4] == fallback  # cdd_plate_id=777 has no sync row → barcode fallback
    assert 3 not in matched
    assert len(unmatched) == 1
    assert unmatched[0].legacy_plate_id == 3
    assert unmatched[0].plate_barcode == "no-such"
    assert unmatched[0].cdd_plate_id == 999
    assert unmatched[0].reason  # non-empty


@pytest.mark.asyncio
async def test_apply_ownership_sets_owner_type_status_tags_inactive_and_is_idempotent(session_factory):
    ws = uuid.uuid4()
    org = uuid.uuid4()
    active = uuid.uuid4()
    inactive = uuid.uuid4()
    async with session_factory() as s:
        await _seed_plate(s, plate_id=active, barcode="900010", ws=ws, cdd_plate_id=101)
        await _seed_plate(s, plate_id=inactive, barcode="900011", ws=ws, cdd_plate_id=102)
        await s.commit()
    legacy = LegacyData(plates=[
        LegacyPlate(1, 101, "x", "P1", "Active", "MASTER", None),
        LegacyPlate(2, 102, "y", "P2", "Inactive", "VENDOR", None),
    ])
    for _ in range(2):  # idempotent: run twice
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            plate_repo = SQLAlchemyRegisteredPlateRepository(uow)
            cdd_repo = CddPlateSyncRepository(uow)
            tag_repo = SQLAlchemyTagRepository(uow)
            link_repo = RegisteredPlateTagLinkRepository(uow)
            matched, _ = await match_plates(legacy, plate_repo=plate_repo, cdd_repo=cdd_repo,
                                            workspace_id=ws, cdd_vault_id=VAULT)
            await apply_plate_ownership(
                legacy, matched, plate_repo=plate_repo, tag_repo=tag_repo,
                plate_tag_link_repo=link_repo, uow=uow, workspace_id=ws,
                internal_org_id=org, actor_id=org)
            await uow.commit()
    async with session_factory() as s:
        rows = (await s.execute(sa.text(
            "SELECT id, owner_org_id, plate_type, status FROM registered_plates "
            "WHERE id IN (:a, :b)"), {"a": active, "b": inactive})).mappings().all()
        by_id = {r["id"]: r for r in rows}
        tagged = (await s.execute(sa.text(
            "SELECT rpt.registered_plate_id FROM registered_plate_tags rpt "
            "JOIN tags t ON t.id = rpt.tag_id "
            "WHERE t.workspace_id = :ws AND t.normalized_key = 'legacy' "
            "AND t.normalized_value = 'inactive'"), {"ws": ws})).scalars().all()
    assert by_id[active]["owner_org_id"] == org
    assert by_id[active]["plate_type"] == PlateType.MOTHER.value
    assert by_id[active]["status"] == PlateStatus.STORED.value
    assert by_id[inactive]["plate_type"] == PlateType.COMPOUND_STORAGE.value
    assert by_id[inactive]["status"] == PlateStatus.DEPLETED.value   # registered→stored→depleted
    assert tagged == [inactive]   # legacy:inactive tagged once (idempotent), active untouched


@pytest.mark.asyncio
async def test_backfill_null_owner_only_touches_nulls(session_factory):
    ws = uuid.uuid4()          # unique ws → backfill count is deterministic
    org = uuid.uuid4()
    orphan = uuid.uuid4()
    owned = uuid.uuid4()
    async with session_factory() as s:
        await _seed_plate(s, plate_id=orphan, barcode="900020", ws=ws)   # owner NULL
        await _seed_plate(s, plate_id=owned, barcode="900021", ws=ws, owner_org_id=uuid.uuid4())
        await s.commit()
    async with session_factory() as s:
        n = await backfill_null_owner(s, workspace_id=ws, internal_org_id=org)
        await s.commit()
    assert n == 1   # only the orphan (ws is unique to this test)
    async with session_factory() as s:
        got = (await s.execute(sa.text(
            "SELECT owner_org_id FROM registered_plates WHERE id = :id"), {"id": orphan})).scalar_one()
    assert got == org


@pytest.mark.asyncio
async def test_apply_group_tree_and_assign_is_idempotent(session_factory):
    ws = uuid.uuid4()
    org = uuid.uuid4()
    plate = uuid.uuid4()
    async with session_factory() as s:
        await _seed_plate(s, plate_id=plate, barcode="900030", ws=ws, cdd_plate_id=201,
                          owner_org_id=org)
        await s.commit()
    legacy = LegacyData(
        libraries=[LegacyLibrary(10, "Lib Z", "SacchettiniLibrary")],
        sets=[LegacySet(1, "SCREENING", "Set One", "Dry", None, None, 10)],
        set_parents=[],
        set_plates=[LegacySetPlate(set_id=1, plate_id=99)],  # legacy plate 99 → cellar `plate`
        plates=[LegacyPlate(99, 201, "x", "P", "Active", "MASTER", None)],
    )
    for _ in range(2):
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            plate_repo = SQLAlchemyRegisteredPlateRepository(uow)
            cdd_repo = CddPlateSyncRepository(uow)
            group_repo = SQLAlchemyPlateGroupRepository(uow)
            matched, _ = await match_plates(legacy, plate_repo=plate_repo, cdd_repo=cdd_repo,
                                            workspace_id=ws, cdd_vault_id=VAULT)
            specs = plan_group_tree(legacy, {})
            key_to_group = await apply_group_tree(specs, group_repo=group_repo, workspace_id=ws,
                                                  owner_org_id=org, actor_id=org)
            await assign_plates_to_groups(legacy, key_to_group, matched,
                                          plate_repo=plate_repo, workspace_id=ws)
            await uow.commit()
    async with session_factory() as s:
        groups = (await s.execute(sa.text(
            "SELECT id, name, parent_group_id FROM plate_groups WHERE workspace_id = :ws "
            "AND owner_org_id = :o ORDER BY name"), {"ws": ws, "o": org})).mappings().all()
        assert [g["name"] for g in groups] == ["Lib Z", "Set One"]   # unique ws → no dupes/contamination
        by_name = {g["name"]: g for g in groups}
        assert by_name["Lib Z"]["parent_group_id"] is None                       # library root
        assert by_name["Set One"]["parent_group_id"] == by_name["Lib Z"]["id"]   # set nested under its library
        grp = (await s.execute(sa.text("SELECT group_id FROM registered_plates WHERE id = :id"),
                               {"id": plate})).scalar_one()
        assert grp == by_name["Set One"]["id"]                                    # plate assigned to its set's group
