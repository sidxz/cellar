"""Migrate the legacy plate-tracker (MySQL) into Cellar inventory plates.

Idempotent + re-runnable. Reads the legacy DB once (pymysql), then, in one
transaction: backfills NULL plate owners, builds the Site → Building → Room →
Freezer StorageLocation tree, matches legacy plates to Cellar plates
(cdd_plate_sync → barcode) and registers whatever doesn't match (+ a
cdd_plate_sync row when the legacy row carries a CDD plate id), sets
ownership/type/status (tolerating plates whose current status can't reach the
legacy target — recorded, not fatal), builds the PlateGroup tree, and
recreates the OPEN checkouts as PlateLoans. Closed history is NOT migrated
(stays in the read-only legacy DB).

Usage (from backend/):
    uv run python scripts/migrate_legacy_plate_tracker.py \\
        --legacy-dsn mysql://user:pass@host:3306/sacnet_prod \\
        --workspace-id <ws-uuid> --internal-org-id <org-uuid> \\
        --cdd-vault-id <vault> --actor-id <sentinel-user-uuid> \\
        --user-map user_map.csv --report-dir ./reports \\
        [--site-name TAMU] [--building-name Main] [--dry-run]

Cutover runbook:
  1. Grant `cellar:approve_loan` is NOT needed (migrated loans bypass approval).
  2. Freeze the legacy plate-tracker (read-only announcement).
  3. Build user_map.csv: for each distinct OPEN-transaction requester email,
     look up the Duar user id (admin UI → Users) → `email,user_id` rows.
     (No service-key email→user lookup exists, so this step is manual.)
  4. Dry-run: add --dry-run; review MIGRATION SUMMARY + reports/*.csv.
     Resolve unmatched_plates.csv (plates registered under neither a cdd
     plate id nor a barcode — check plate_role/plate_format for typos) and
     unresolved_requesters.csv (add to user_map.csv) until acceptable.
  5. Real run (no --dry-run). Re-run is safe (idempotent) if interrupted.
  6. Spot-check in the UI: plate owners, the storage location tree under
     --site-name/--building-name, the group tree, the ~15 open loans, the
     `legacy:inactive` tag on depleted plates (summary inactive_tagged), and
     status_conflicts.csv (plates whose Cellar status couldn't reach the
     legacy-mapped target — usually already `disposed`; resolve by hand).
  7. Announce cutover.

Summary counters: owner_backfilled, locations_created, plates_matched,
plates_created, cdd_sync_rows, unmatched_plates, plates_classified,
inactive_tagged, status_conflicts, groups_created, plates_grouped,
loans_created, unresolved_requesters.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pymysql
import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.domain.inventory.enums import (
    VALID_PLATE_TRANSITIONS,
    LoanItemStatus,
    PlateStatus,
    PlateType,
    StorageLocationType,
)
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.plate_loan import PlateLoan
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.storage_location import StorageLocation
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from cellar.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from cellar.domain.workspace_config.tagging.tag import TagName
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_sync_repository import (
    CddPlateSyncRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.storage_location_repository import (
    SQLAlchemyStorageLocationRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    RegisteredPlateTagLinkRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (  # noqa: E501
    SQLAlchemyControlledVocabularyRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class LegacyLibrary:
    library_id: int
    library_name: str
    library_type: str


@dataclass(frozen=True)
class LegacySet:
    set_id: int
    set_type: str
    set_name: str
    set_state: str | None
    scientist: int | None
    generating_conditions: str | None
    library_id: int | None
    plate_format_id: int | None = None
    set_location_id: int | None = None
    initial_volume: float | None = None
    initial_concentration: float | None = None
    no_of_compounds: int | None = None
    compound_file: str | None = None
    comments: str | None = None


@dataclass(frozen=True)
class LegacySetParent:
    set_id: int  # child
    parent_id: int  # parent


@dataclass(frozen=True)
class LegacySetPlate:
    set_id: int
    plate_id: int


@dataclass(frozen=True)
class LegacyPlate:
    plate_id: int
    cdd_plate_id: int | None
    plate_barcode: str
    plate_name: str
    plate_status: str
    plate_role: str
    library_id: int | None
    plate_format_id: int | None = None


@dataclass(frozen=True)
class LegacyTransaction:
    transaction_id: int
    t_status: str
    scientist: int  # requester UIN
    last_activity_date: datetime


@dataclass(frozen=True)
class LegacyTransactionPlate:
    plate_id: int
    p_status: str
    transaction_id: int


@dataclass(frozen=True)
class LegacyAccount:
    uin: int
    netid: str
    email: str | None
    alt_email: str | None
    first_name: str | None
    last_name: str | None


@dataclass(frozen=True)
class LegacyLocation:
    location_id: int
    room_no: str
    freezer: str


@dataclass(frozen=True)
class LegacyPlateFormat:
    plate_format_id: int
    plate_format_name: str
    no_of_wells: int


@dataclass(frozen=True)
class LegacyActivity:
    act_id: int
    act_type: str
    transaction_id: int | None
    plate_id: int | None
    set_id: int | None
    comments: str
    scientist: int
    act_date: datetime


@dataclass(frozen=True)
class LocationSpec:
    location_id: int
    room_no: str
    freezer: str


_PLATE_TYPE_BY_ROLE = {
    "MASTER": PlateType.MOTHER,
    "SCREENING": PlateType.ASSAY,
    "HIT_COLLECTION": PlateType.CHERRY_PICK,
    "VENDOR": PlateType.COMPOUND_STORAGE,
}
_PLATE_STATUS = {
    "Active": (PlateStatus.STORED, []),
    "AVAIL": (PlateStatus.STORED, []),
    "Inactive": (PlateStatus.DEPLETED, ["legacy:inactive"]),
}
_LOAN_ITEM_STATUS = {
    "COUT_REQ": LoanItemStatus.REQUESTED,
    "COUT_WSCAN": LoanItemStatus.APPROVED,
    "ASSIGNED": LoanItemStatus.CHECKED_OUT,
    "CIN_REQ": LoanItemStatus.RETURN_PENDING,
    "CIN_WSCAN": LoanItemStatus.RETURN_PENDING,
}
_DUE_DAYS = 14


def map_plate_type(role: str) -> PlateType:
    try:
        return _PLATE_TYPE_BY_ROLE[role]
    except KeyError:
        raise ValueError(f"unknown legacy plate_role: {role!r}") from None


def map_plate_status(status: str) -> tuple[PlateStatus, list[str]]:
    try:
        target, tags = _PLATE_STATUS[status]
    except KeyError:
        raise ValueError(f"unknown legacy plate_status: {status!r}") from None
    return target, list(tags)


def map_loan_item_status(p_status: str) -> LoanItemStatus:
    try:
        return _LOAN_ITEM_STATUS[p_status]
    except KeyError:
        raise ValueError(f"unknown legacy p_status: {p_status!r}") from None


def due_date_from(last_activity: datetime) -> date:
    return (last_activity + timedelta(days=_DUE_DAYS)).date()


def compose_set_description(s: LegacySet, account_names: dict[int, str]) -> str | None:
    """State and scientist now live on GroupSpec/PlateGroup as first-class fields
    (see plan_group_tree) — the description folds only free-text content.
    `account_names` is unused here; kept so callers don't change."""
    parts: list[str] = []
    if s.generating_conditions:
        parts.append(s.generating_conditions)
    if s.compound_file:
        parts.append(f"Compound file: {s.compound_file}")
    if s.comments:
        parts.append(s.comments)
    return "\n".join(parts) if parts else None


_WELLS_TO_FORMAT = {96: PlateFormat.F96, 384: PlateFormat.F384}


def format_for_plate(
    plate: LegacyPlate, set_for_plate: LegacySet | None, formats: dict[int, int]
) -> PlateFormat:
    """Plate's own format, else its set's, else 96-well (109 legacy plates carry
    the 'Invalid Plate Format' sentinel, wells = -1)."""
    for fid in (plate.plate_format_id, set_for_plate.plate_format_id if set_for_plate else None):
        fmt = _WELLS_TO_FORMAT.get(formats.get(fid, -1)) if fid is not None else None
        if fmt is not None:
            return fmt
    return PlateFormat.F96


def full_name(a: LegacyAccount) -> str:
    name = f"{(a.first_name or '').strip()} {(a.last_name or '').strip()}".strip()
    return name or a.netid or f"UIN {a.uin}"


def open_transactions(legacy: LegacyData) -> list[LegacyTransaction]:
    return [t for t in legacy.transactions if t.t_status == "OPEN"]


def plan_locations(legacy: LegacyData) -> tuple[list[LocationSpec], dict[int, int]]:
    """Distinct (room, freezer) pairs; UNKNOWN/UNKNOWN is 'no location'.
    Returns the specs plus an alias map duplicate-id → kept-id."""
    seen: dict[tuple[str, str], int] = {}
    specs: list[LocationSpec] = []
    alias: dict[int, int] = {}
    for loc in legacy.locations:
        key = (loc.room_no.strip(), loc.freezer.strip())
        if key == ("UNKNOWN", "UNKNOWN"):
            continue
        if key in seen:
            alias[loc.location_id] = seen[key]
            continue
        seen[key] = loc.location_id
        specs.append(LocationSpec(loc.location_id, key[0], key[1]))
    return specs, alias


async def _find_child_by_name(location_repo, workspace_id, parent_id, name, loc_type):
    kids = await location_repo.find_children(workspace_id, parent_id) if parent_id else [
        loc for loc in await location_repo.find_by_workspace(workspace_id) if loc.parent_id is None
    ]
    return next((k for k in kids if k.name == name and k.type == loc_type), None)


async def _ensure_location(location_repo, *, workspace_id, name, loc_type, parent, counter):
    existing = await _find_child_by_name(
        location_repo, workspace_id, parent.id if parent else None, name, loc_type
    )
    if existing is not None:
        return existing
    loc = StorageLocation.create(
        workspace_id=workspace_id, name=name, type=loc_type,
        parent_id=parent.id if parent else None, parent_type=parent.type if parent else None,
    )
    await location_repo.save(loc)
    counter["created"] += 1
    return loc


async def apply_locations(
    specs, alias, *, location_repo, workspace_id, site_name, building_name
) -> tuple[dict[int, uuid.UUID], int]:
    """Site → Building → Room {room_no} → Freezer {freezer}; idempotent by name under parent."""
    counter = {"created": 0}
    site = await _ensure_location(
        location_repo, workspace_id=workspace_id, name=site_name,
        loc_type=StorageLocationType.SITE, parent=None, counter=counter,
    )
    building = await _ensure_location(
        location_repo, workspace_id=workspace_id, name=building_name,
        loc_type=StorageLocationType.BUILDING, parent=site, counter=counter,
    )
    ids: dict[int, uuid.UUID] = {}
    rooms: dict[str, StorageLocation] = {}
    for spec in specs:
        room = rooms.get(spec.room_no)
        if room is None:
            room = await _ensure_location(
                location_repo, workspace_id=workspace_id, name=f"Room {spec.room_no}",
                loc_type=StorageLocationType.ROOM, parent=building, counter=counter,
            )
            rooms[spec.room_no] = room
        freezer = await _ensure_location(
            location_repo, workspace_id=workspace_id, name=f"Freezer {spec.freezer}",
            loc_type=StorageLocationType.FREEZER, parent=room, counter=counter,
        )
        ids[spec.location_id] = freezer.id
    for dup, kept in alias.items():
        if kept in ids:
            ids[dup] = ids[kept]
    return ids, counter["created"]


@dataclass
class LegacyData:
    libraries: list[LegacyLibrary] = field(default_factory=list)
    sets: list[LegacySet] = field(default_factory=list)
    set_parents: list[LegacySetParent] = field(default_factory=list)
    set_plates: list[LegacySetPlate] = field(default_factory=list)
    plates: list[LegacyPlate] = field(default_factory=list)
    transactions: list[LegacyTransaction] = field(default_factory=list)
    transaction_plates: list[LegacyTransactionPlate] = field(default_factory=list)
    accounts: list[LegacyAccount] = field(default_factory=list)
    locations: list[LegacyLocation] = field(default_factory=list)
    plate_formats: list[LegacyPlateFormat] = field(default_factory=list)
    activities: list[LegacyActivity] = field(default_factory=list)


_P = "APPS_PLATE_TRACKER_"  # table prefix


def build_account_email_map(accounts: list[LegacyAccount]) -> dict[int, str]:
    """UIN -> email, preferring `email`, falling back to `alt_email`;
    skips NULL/empty and auto-provisioned `AUTO_RAN*` placeholders."""
    out: dict[int, str] = {}
    for a in accounts:
        for candidate in (a.email, a.alt_email):
            if candidate and not candidate.startswith("AUTO_RAN"):
                out[a.uin] = candidate
                break
    return out


def _row_to_set(r: dict) -> LegacySet:
    """MySQL DECIMAL columns arrive as decimal.Decimal — coerce to float/int."""
    r = dict(r)
    for key in ("initial_volume", "initial_concentration"):
        if r.get(key) is not None:
            r[key] = float(r[key])
    if r.get("no_of_compounds") is not None:
        r["no_of_compounds"] = int(r["no_of_compounds"])
    return LegacySet(**r)


def read_legacy(dsn: str) -> LegacyData:
    """Read every needed legacy table once into dataclasses via pymysql.
    `dsn` = mysql://user:pass@host:port/dbname."""
    u = urlparse(dsn)
    conn = pymysql.connect(
        host=u.hostname,
        port=u.port or 3306,
        user=u.username,
        password=u.password or "",
        database=u.path.lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        d = LegacyData()
        with conn.cursor() as cur:
            cur.execute(f"SELECT library_id, library_name, library_type FROM {_P}LIBRARY")
            d.libraries = [LegacyLibrary(**r) for r in cur.fetchall()]
            cur.execute(
                f"SELECT set_id, set_type, set_name, set_state, scientist, "
                f"generating_conditions, library_id, plate_format_id, "
                f"set_location_id, initial_volume, initial_concentration, "
                f"no_of_compounds, compound_file, comments FROM {_P}SET"
            )
            d.sets = [_row_to_set(r) for r in cur.fetchall()]
            cur.execute(f"SELECT set_id, parent_id FROM {_P}SET_PARENT")
            d.set_parents = [LegacySetParent(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT set_id, plate_id FROM {_P}SET_PLATE")
            d.set_plates = [LegacySetPlate(**r) for r in cur.fetchall()]
            cur.execute(
                f"SELECT plate_id, cdd_plate_id, plate_barcode, plate_name, "
                f"plate_status, plate_role, library_id, plate_format_id FROM {_P}PLATE"
            )
            d.plates = [LegacyPlate(**r) for r in cur.fetchall()]
            cur.execute(
                f"SELECT transaction_id, t_status, scientist, last_activity_date "
                f"FROM {_P}TRANSACTIONS"
            )
            d.transactions = [
                LegacyTransaction(
                    **{**r, "last_activity_date": r["last_activity_date"].replace(tzinfo=UTC)}
                )
                for r in cur.fetchall()
            ]
            cur.execute(f"SELECT plate_id, p_status, transaction_id FROM {_P}TRANSACTION_PLATE")
            d.transaction_plates = [LegacyTransactionPlate(**r) for r in cur.fetchall()]
            cur.execute(
                "SELECT UIN AS uin, netid, email, alt_email, "
                "firstName AS first_name, lastName AS last_name FROM account"
            )
            d.accounts = [LegacyAccount(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT location_id, room_no, freezer FROM {_P}LOCATION")
            d.locations = [LegacyLocation(**r) for r in cur.fetchall()]
            cur.execute(
                f"SELECT plate_format_id, plate_format_name, no_of_wells "
                f"FROM {_P}PLATE_FORMAT"
            )
            d.plate_formats = [LegacyPlateFormat(**r) for r in cur.fetchall()]
            cur.execute(
                f"SELECT act_id, act_type, transaction_id, plate_id, set_id, "
                f"comments, scientist, act_date FROM {_P}ACTIVITY_LOG"
            )
            d.activities = [
                LegacyActivity(
                    **{
                        **r,
                        "comments": r["comments"] or "",
                        "act_date": r["act_date"].replace(tzinfo=UTC),
                    }
                )
                for r in cur.fetchall()
            ]
        return d
    finally:
        conn.close()


@dataclass(frozen=True)
class UnmatchedPlate:
    legacy_plate_id: int
    plate_barcode: str
    cdd_plate_id: int | None
    reason: str


async def match_plates(legacy, *, plate_repo, cdd_repo, workspace_id, cdd_vault_id):
    matched: dict[int, uuid.UUID] = {}
    unmatched: list[UnmatchedPlate] = []
    for p in legacy.plates:
        cellar_id = None
        if p.cdd_plate_id is not None:
            cellar_id = await cdd_repo.find_plate_id_by_cdd_plate_id(
                workspace_id, cdd_vault_id, p.cdd_plate_id
            )
        if cellar_id is None:
            hit = await resolve_barcode(plate_repo, workspace_id, p.plate_barcode)
            cellar_id = hit.id if hit is not None else None
        if cellar_id is None:
            unmatched.append(
                UnmatchedPlate(
                    p.plate_id,
                    p.plate_barcode,
                    p.cdd_plate_id,
                    "no cdd_plate_sync row and no barcode match",
                )
            )
        else:
            matched[p.plate_id] = cellar_id
    return matched, unmatched


@dataclass(frozen=True)
class CreatedPlate:
    legacy_plate_id: int
    plate_barcode: str
    format: str
    plate_type: str


async def create_missing_plates(
    legacy, unmatched, *, plate_repo, cdd_repo, workspace_id, internal_org_id, actor_id,
    cdd_vault_id, location_ids,
) -> tuple[dict[int, uuid.UUID], list[CreatedPlate], list[UnmatchedPlate]]:
    """Register every legacy plate Cellar doesn't have. Format from the plate, else its set,
    else 96; storage location = its set's freezer; cdd_plate_sync row when the legacy row
    carries a CDD plate id so a later CDD import merges instead of duplicating."""
    plates_by_id = {p.plate_id: p for p in legacy.plates}
    sets_by_id = {s.set_id: s for s in legacy.sets}
    set_of_plate = {sp.plate_id: sets_by_id.get(sp.set_id) for sp in legacy.set_plates}
    formats = {f.plate_format_id: f.no_of_wells for f in legacy.plate_formats}
    created_ids: dict[int, uuid.UUID] = {}
    created: list[CreatedPlate] = []
    still: list[UnmatchedPlate] = []
    sync: list[tuple[int, uuid.UUID]] = []
    for um in unmatched:
        p = plates_by_id.get(um.legacy_plate_id)
        if p is None:
            still.append(um)
            continue
        try:
            plate_type = map_plate_type(p.plate_role)
        except ValueError as exc:
            still.append(UnmatchedPlate(p.plate_id, p.plate_barcode, p.cdd_plate_id, str(exc)))
            continue
        s = set_of_plate.get(p.plate_id)
        fmt = format_for_plate(p, s, formats)
        storage_location_id = (
            location_ids.get(s.set_location_id) if s and s.set_location_id else None
        )
        plate = RegisteredPlate.register(
            workspace_id=workspace_id,
            owner_org_id=internal_org_id,
            barcode=Barcode(value=p.plate_barcode),
            plate_label=p.plate_name,
            format=fmt,
            plate_type=plate_type,
            registered_by=actor_id,
            storage_location_id=storage_location_id,
        )
        await plate_repo.save(plate)
        created_ids[p.plate_id] = plate.id
        created.append(CreatedPlate(p.plate_id, p.plate_barcode, fmt.value, plate_type.value))
        if p.cdd_plate_id is not None:
            sync.append((p.cdd_plate_id, plate.id))
    if sync:
        await cdd_repo.bulk_upsert(workspace_id, cdd_vault_id, sync)
    return created_ids, created, still


def _set_plate_status(plate, target: PlateStatus) -> bool:
    """Drive plate.status to `target` through valid transitions; idempotent.
    Only STORED and DEPLETED are ever requested here. Returns False (no-op)
    when `target` is unreachable from the plate's current status instead of
    raising — the caller records a StatusConflict and keeps going."""
    if plate.status == target:
        return True
    if target in VALID_PLATE_TRANSITIONS[plate.status]:
        plate.transition_status(target)
        return True
    # DEPLETED is unreachable in one hop from REGISTERED — go via STORED.
    if (
        target == PlateStatus.DEPLETED
        and PlateStatus.STORED in VALID_PLATE_TRANSITIONS[plate.status]
    ):
        plate.transition_status(PlateStatus.STORED)
        plate.transition_status(PlateStatus.DEPLETED)
        return True
    return False


@dataclass(frozen=True)
class StatusConflict:
    legacy_plate_id: int
    plate_barcode: str
    current_status: str
    target_status: str


async def apply_plate_ownership(
    legacy,
    matched,
    *,
    plate_repo,
    tag_repo,
    plate_tag_link_repo,
    uow,
    workspace_id,
    internal_org_id,
    actor_id,
) -> tuple[dict[str, int], list[StatusConflict]]:
    stats = {
        "classified": 0, "skipped_unmapped": 0, "inactive_tagged": 0, "status_conflicts": 0,
    }
    conflicts: list[StatusConflict] = []
    inactive_tag_id: uuid.UUID | None = None  # created lazily, once
    by_legacy_id = {p.plate_id: p for p in legacy.plates}
    for legacy_id, cellar_id in matched.items():
        p = by_legacy_id[legacy_id]
        try:
            ptype = map_plate_type(p.plate_role)
            pstatus, tags = map_plate_status(p.plate_status)
        except ValueError as e:
            logger.warning("legacy_plate_unmapped", legacy_plate_id=legacy_id, error=str(e))
            stats["skipped_unmapped"] += 1
            continue
        plate = await plate_repo.find_by_id_in_workspace(workspace_id, cellar_id)
        if plate is None:
            continue
        changed = False
        if plate.owner_org_id != internal_org_id or plate.plate_type != ptype:
            plate.update(owner_org_id=internal_org_id, plate_type=ptype)
            changed = True
        if plate.status != pstatus:
            current_status = plate.status
            if _set_plate_status(plate, pstatus):
                changed = True
            else:
                logger.warning(
                    "legacy_plate_status_conflict", legacy_plate_id=legacy_id,
                    current_status=current_status.value, target_status=pstatus.value,
                )
                stats["status_conflicts"] += 1
                conflicts.append(
                    StatusConflict(legacy_id, p.plate_barcode, current_status.value, pstatus.value)
                )
        if changed:
            await plate_repo.save(plate)
            stats["classified"] += 1
        if "legacy:inactive" in tags:
            if inactive_tag_id is None:
                tag = await tag_repo.get_or_create(
                    workspace_id, TagName(key="legacy", value="inactive"), created_by=actor_id
                )
                inactive_tag_id = tag.id
            if await plate_tag_link_repo.add(
                workspace_id, cellar_id, inactive_tag_id, assigned_by=actor_id
            ):
                stats["inactive_tagged"] += 1
    return stats, conflicts


async def backfill_null_owner(session, *, workspace_id, internal_org_id) -> int:
    """S2-deferred backfill: every NULL-owner plate in this workspace -> internal org.
    Bulk SQL (matches alembic backfill precedent 042/021); bumps version for OCC safety."""
    result = await session.execute(
        sa.text(
            "UPDATE registered_plates SET owner_org_id = :org, version = version + 1, "
            "updated_at = now() WHERE workspace_id = :ws AND owner_org_id IS NULL"
        ),
        {"org": internal_org_id, "ws": workspace_id},
    )
    return result.rowcount or 0


@dataclass(frozen=True)
class GroupSpec:
    key: str
    name: str
    group_type: str | None
    description: str | None
    parent_key: str | None
    state: str | None = None
    location_id: int | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None


def plan_group_tree(legacy, account_names: dict[int, str]) -> list[GroupSpec]:
    specs: list[GroupSpec] = []
    for lib in legacy.libraries:
        specs.append(GroupSpec(f"lib:{lib.library_id}", lib.library_name, None, None, None))
    child_to_parent = {sp.set_id: sp.parent_id for sp in legacy.set_parents}
    for s in legacy.sets:
        if s.set_id in child_to_parent:
            parent_key = f"set:{child_to_parent[s.set_id]}"
        elif s.library_id is not None:
            parent_key = f"lib:{s.library_id}"
        else:
            parent_key = None
        specs.append(
            GroupSpec(
                f"set:{s.set_id}",
                s.set_name,
                s.set_type,
                compose_set_description(s, account_names),
                parent_key,
                state=s.set_state or None,
                location_id=s.set_location_id,
                initial_volume_ul=s.initial_volume,
                initial_concentration_mm=s.initial_concentration,
                compound_count=s.no_of_compounds,
                scientist=account_names.get(s.scientist) if s.scientist else None,
            )
        )
    # topological order: roots first, then nodes whose parent already emitted
    ordered: list[GroupSpec] = []
    emitted: set[str] = set()
    pending = list(specs)
    while pending:
        progressed = False
        rest = []
        for g in pending:
            if g.parent_key is None or g.parent_key in emitted:
                ordered.append(g)
                emitted.add(g.key)
                progressed = True
            else:
                rest.append(g)
        pending = rest
        if not progressed:  # broken parent ref (shouldn't happen) — emit as roots
            for g in pending:
                ordered.append(replace(g, parent_key=None))
            break
    return ordered


_GROUP_TYPE_VOCAB = "plate_group_type"
_GROUP_STATE_VOCAB = "plate_group_state"


async def apply_group_tree(
    specs, *, group_repo, workspace_id, owner_org_id, actor_id,
    location_ids: dict[int, uuid.UUID] | None = None,
):
    key_to_group: dict[str, uuid.UUID] = {}
    created = 0
    location_ids = location_ids or {}
    for g in specs:
        parent_id = key_to_group.get(g.parent_key) if g.parent_key else None
        storage_location_id = (
            location_ids.get(g.location_id) if g.location_id is not None else None
        )
        existing = await group_repo.find_by_name(workspace_id, owner_org_id, parent_id, g.name)
        if existing is not None:
            key_to_group[g.key] = existing.id
            current = (
                existing.state, existing.storage_location_id, existing.initial_volume_ul,
                existing.initial_concentration_mm, existing.compound_count, existing.scientist,
            )
            target = (
                g.state, storage_location_id, g.initial_volume_ul,
                g.initial_concentration_mm, g.compound_count, g.scientist,
            )
            if current != target:
                existing.update(
                    state=g.state,
                    storage_location_id=storage_location_id,
                    initial_volume_ul=g.initial_volume_ul,
                    initial_concentration_mm=g.initial_concentration_mm,
                    compound_count=g.compound_count,
                    scientist=g.scientist,
                )
                await group_repo.save(existing)
            continue
        group = PlateGroup.create(
            workspace_id=workspace_id,
            owner_org_id=owner_org_id,
            name=g.name,
            created_by=actor_id,
            parent_group_id=parent_id,
            group_type=g.group_type,
            description=g.description,
            state=g.state,
            storage_location_id=storage_location_id,
            initial_volume_ul=g.initial_volume_ul,
            initial_concentration_mm=g.initial_concentration_mm,
            compound_count=g.compound_count,
            scientist=g.scientist,
        )
        await group_repo.save(group)
        key_to_group[g.key] = group.id
        created += 1
    return key_to_group, created


async def assign_plates_to_groups(
    legacy, key_to_group, matched, *, plate_repo, workspace_id
) -> int:
    n = 0
    for sp in legacy.set_plates:
        group_id = key_to_group.get(f"set:{sp.set_id}")
        cellar_id = matched.get(sp.plate_id)
        if group_id is None or cellar_id is None:
            continue
        plate = await plate_repo.find_by_id_in_workspace(workspace_id, cellar_id)
        if (
            plate is None or plate.group_id == group_id
        ):  # guard: no-op if unchanged (avoids event spam)
            continue
        plate.assign_to_group(group_id)
        await plate_repo.save(plate)
        n += 1
    return n


async def seed_vocab(*, cv_repo, workspace_id, actor_id, name: str, values: list[str]) -> None:
    """Create the vocabulary or add any missing terms (idempotent)."""
    if not values:
        return
    vocab = await cv_repo.find_by_name(workspace_id, name)
    if vocab is None:
        vocab = ControlledVocabulary.create(
            workspace_id=workspace_id, name=name, terms=values, created_by=actor_id
        )
        await cv_repo.save(vocab)
        return
    changed = False
    for v in values:
        if v not in vocab.terms:
            vocab.add_term(v)
            changed = True
    if changed:
        await cv_repo.save(vocab)


async def seed_group_type_vocab(legacy, *, cv_repo, workspace_id, actor_id) -> None:
    await seed_vocab(
        cv_repo=cv_repo, workspace_id=workspace_id, actor_id=actor_id,
        name=_GROUP_TYPE_VOCAB, values=sorted({s.set_type for s in legacy.sets if s.set_type}),
    )
    await seed_vocab(
        cv_repo=cv_repo, workspace_id=workspace_id, actor_id=actor_id,
        name=_GROUP_STATE_VOCAB,
        values=sorted({s.set_state for s in legacy.sets if getattr(s, "set_state", None)}),
    )


@dataclass(frozen=True)
class LoanItemSpec:
    cellar_plate_id: uuid.UUID
    target: LoanItemStatus


@dataclass(frozen=True)
class LoanSpec:
    transaction_id: int
    requester_user_id: uuid.UUID
    due_date: date
    items: list[LoanItemSpec]


@dataclass(frozen=True)
class UnresolvedRequester:
    transaction_id: int
    scientist_uin: int
    email: str | None
    reason: str


def plan_loans(legacy, matched, account_email, user_map):
    specs: list[LoanSpec] = []
    unresolved: list[UnresolvedRequester] = []
    tps_by_txn: dict[int, list] = {}
    for tp in legacy.transaction_plates:
        tps_by_txn.setdefault(tp.transaction_id, []).append(tp)
    for txn in legacy.transactions:  # caller passes only OPEN transactions
        email = account_email.get(txn.scientist)
        user_id = user_map.get(email) if email else None
        if user_id is None:
            unresolved.append(
                UnresolvedRequester(
                    txn.transaction_id,
                    txn.scientist,
                    email,
                    "no email" if not email else "email not in --user-map",
                )
            )
            continue
        items: list[LoanItemSpec] = []
        for tp in tps_by_txn.get(txn.transaction_id, []):
            cellar_id = matched.get(tp.plate_id)
            if cellar_id is None:
                continue  # unmatched plate — skip item (reported in Task 3)
            items.append(LoanItemSpec(cellar_id, map_loan_item_status(tp.p_status)))
        if items:
            specs.append(
                LoanSpec(txn.transaction_id, user_id, due_date_from(txn.last_activity_date), items)
            )
    return specs, unresolved


async def apply_loan(spec, *, loan_repo, workspace_id, internal_org_id) -> bool:
    already = await loan_repo.active_plate_ids(
        workspace_id, [i.cellar_plate_id for i in spec.items]
    )
    fresh = [i for i in spec.items if i.cellar_plate_id not in already]
    if not fresh:  # every plate already in an active loan → idempotent skip
        return False
    loan = PlateLoan.request(
        workspace_id=workspace_id,
        owner_org_id=internal_org_id,
        borrower_org_id=internal_org_id,
        requested_by=spec.requester_user_id,
        plate_ids=[i.cellar_plate_id for i in fresh],
        auto_approved=False,
        due_date=spec.due_date,
        notes="Migrated from legacy plate-tracker",
    )
    item_by_plate = {it.plate_id: it for it in loan.items}
    target_by_plate = {i.cellar_plate_id: i.target for i in fresh}

    def ids(*targets):
        return [item_by_plate[pid].id for pid, t in target_by_plate.items() if t in targets]

    # Items stay REQUESTED unless a later status is targeted. Approve everything
    # past REQUESTED first, then advance the checkout/return subsets.
    to_approve = ids(
        LoanItemStatus.APPROVED, LoanItemStatus.CHECKED_OUT, LoanItemStatus.RETURN_PENDING
    )
    if to_approve:
        loan.approve_items(
            to_approve, approved_by=spec.requester_user_id
        )  # legacy authorized_by is NULL → self-approve
    to_checkout = ids(LoanItemStatus.CHECKED_OUT, LoanItemStatus.RETURN_PENDING)
    if to_checkout:
        loan.confirm_checkout(to_checkout)
    to_return = ids(LoanItemStatus.RETURN_PENDING)
    if to_return:
        loan.request_return(to_return)
    await loan_repo.save(loan)
    return True


def _write_csv(path: Path, rows: list, header: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([getattr(r, h) for h in header])


async def run_migration(
    session_factory,
    legacy,
    *,
    workspace_id,
    internal_org_id,
    cdd_vault_id,
    user_map,
    actor_id,
    report_dir,
    dry_run,
    site_name: str = "TAMU",
    building_name: str = "Main",
) -> dict:
    account_email = build_account_email_map(legacy.accounts)
    account_names = {a.uin: full_name(a) for a in legacy.accounts}
    summary: dict[str, int] = {}
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        plate_repo = SQLAlchemyRegisteredPlateRepository(uow)
        cdd_repo = CddPlateSyncRepository(uow)
        group_repo = SQLAlchemyPlateGroupRepository(uow)
        loan_repo = SQLAlchemyPlateLoanRepository(uow)
        cv_repo = SQLAlchemyControlledVocabularyRepository(uow)
        tag_repo = SQLAlchemyTagRepository(uow)
        plate_tag_link_repo = RegisteredPlateTagLinkRepository(uow)
        location_repo = SQLAlchemyStorageLocationRepository(uow)

        # Phase 0: NULL-owner backfill (S2-deferred)
        summary["owner_backfilled"] = await backfill_null_owner(
            uow.session, workspace_id=workspace_id, internal_org_id=internal_org_id
        )

        # Phase 1: storage locations (Site → Building → Room → Freezer)
        location_specs, location_alias = plan_locations(legacy)
        location_ids, summary["locations_created"] = await apply_locations(
            location_specs, location_alias, location_repo=location_repo,
            workspace_id=workspace_id, site_name=site_name, building_name=building_name,
        )

        # Phase 2: match, then register whatever Cellar doesn't already have
        matched, unmatched = await match_plates(
            legacy,
            plate_repo=plate_repo,
            cdd_repo=cdd_repo,
            workspace_id=workspace_id,
            cdd_vault_id=cdd_vault_id,
        )
        created_ids, created, still_unmatched = await create_missing_plates(
            legacy, unmatched, plate_repo=plate_repo, cdd_repo=cdd_repo,
            workspace_id=workspace_id, internal_org_id=internal_org_id, actor_id=actor_id,
            cdd_vault_id=cdd_vault_id, location_ids=location_ids,
        )
        matched = {**matched, **created_ids}
        plates_by_id = {p.plate_id: p for p in legacy.plates}
        summary["plates_matched"] = len(matched)
        summary["plates_created"] = len(created)
        summary["cdd_sync_rows"] = sum(
            1 for c in created if plates_by_id[c.legacy_plate_id].cdd_plate_id is not None
        )
        summary["unmatched_plates"] = len(still_unmatched)
        await uow.session.flush()  # created plate rows must be visible to tag-link checks below

        # Phase 3: ownership + classification (+ legacy:inactive tag)
        own, conflicts = await apply_plate_ownership(
            legacy,
            matched,
            plate_repo=plate_repo,
            tag_repo=tag_repo,
            plate_tag_link_repo=plate_tag_link_repo,
            uow=uow,
            workspace_id=workspace_id,
            internal_org_id=internal_org_id,
            actor_id=actor_id,
        )
        summary["plates_classified"] = own["classified"]
        summary["inactive_tagged"] = own["inactive_tagged"]
        summary["status_conflicts"] = own["status_conflicts"]

        # Phase 4: groups + CV + assignment
        await seed_group_type_vocab(
            legacy, cv_repo=cv_repo, workspace_id=workspace_id, actor_id=actor_id
        )
        specs = plan_group_tree(legacy, account_names)
        key_to_group, summary["groups_created"] = await apply_group_tree(
            specs,
            group_repo=group_repo,
            workspace_id=workspace_id,
            owner_org_id=internal_org_id,
            actor_id=actor_id,
            location_ids=location_ids,
        )
        summary["plates_grouped"] = await assign_plates_to_groups(
            legacy, key_to_group, matched, plate_repo=plate_repo, workspace_id=workspace_id
        )

        # Phase 5: loans — read_legacy now reads ALL transactions (not just OPEN),
        # so filter here to keep open-loan behaviour unchanged.
        loan_specs, unresolved = plan_loans(
            replace(legacy, transactions=open_transactions(legacy)),
            matched, account_email, user_map,
        )
        loans_created = 0
        for ls in loan_specs:
            if await apply_loan(
                ls, loan_repo=loan_repo, workspace_id=workspace_id, internal_org_id=internal_org_id
            ):
                loans_created += 1
        summary["loans_created"] = loans_created
        summary["unresolved_requesters"] = len(unresolved)

        if dry_run:
            await uow.rollback()
            logger.info("dry_run_rolled_back", **summary)
        else:
            await uow.commit()  # events discarded — no side-effect dispatch

    _write_csv(
        report_dir / "unmatched_plates.csv",
        still_unmatched,
        ["legacy_plate_id", "plate_barcode", "cdd_plate_id", "reason"],
    )
    _write_csv(
        report_dir / "created_plates.csv",
        created,
        ["legacy_plate_id", "plate_barcode", "format", "plate_type"],
    )
    _write_csv(
        report_dir / "status_conflicts.csv",
        conflicts,
        ["legacy_plate_id", "plate_barcode", "current_status", "target_status"],
    )
    _write_csv(
        report_dir / "unresolved_requesters.csv",
        unresolved,
        ["transaction_id", "scientist_uin", "email", "reason"],
    )
    logger.info("migration_done", dry_run=dry_run, **summary)
    return summary


async def _main() -> None:
    p = argparse.ArgumentParser(description="Migrate legacy plate-tracker into Cellar.")
    p.add_argument("--legacy-dsn", required=True, help="mysql://user:pass@host:port/db")
    p.add_argument("--workspace-id", type=uuid.UUID, required=True)
    p.add_argument("--internal-org-id", type=uuid.UUID, required=True)
    p.add_argument(
        "--cdd-vault-id", required=True, help="cdd_plate_sync.cdd_vault_id for legacy plates"
    )
    p.add_argument(
        "--actor-id",
        type=uuid.UUID,
        required=True,
        help="Duar user id running the migration (group/CV created_by)",
    )
    p.add_argument("--user-map", type=Path, default=None, help="CSV email,duar_user_id")
    p.add_argument("--report-dir", type=Path, default=Path("."))
    p.add_argument("--site-name", default="TAMU", help="Root StorageLocation (type=site) name")
    p.add_argument(
        "--building-name", default="Main", help="StorageLocation (type=building) under --site-name"
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    user_map: dict[str, uuid.UUID] = {}
    if args.user_map:
        with args.user_map.open() as f:
            for row in csv.reader(f):
                if len(row) >= 2 and "@" in row[0]:
                    user_map[row[0].strip()] = uuid.UUID(row[1].strip())

    legacy = read_legacy(args.legacy_dsn)
    engine = create_async_engine(DatabaseSettings().database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        summary = await run_migration(
            session_factory,
            legacy,
            workspace_id=args.workspace_id,
            internal_org_id=args.internal_org_id,
            cdd_vault_id=args.cdd_vault_id,
            user_map=user_map,
            actor_id=args.actor_id,
            report_dir=args.report_dir,
            dry_run=args.dry_run,
            site_name=args.site_name,
            building_name=args.building_name,
        )
        print("MIGRATION SUMMARY:", summary)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
