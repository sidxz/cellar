"""Migrate the legacy plate-tracker (MySQL) into Cellar. See Task 7 for the runbook."""
from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pymysql
import sqlalchemy as sa
import structlog

from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.domain.inventory.enums import (
    VALID_PLATE_TRANSITIONS,
    LoanItemStatus,
    PlateStatus,
    PlateType,
)
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.plate_loan import PlateLoan
from cellar.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from cellar.domain.workspace_config.tagging.tag import TagName

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


@dataclass(frozen=True)
class LegacySetParent:
    set_id: int      # child
    parent_id: int   # parent


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


@dataclass(frozen=True)
class LegacyTransaction:
    transaction_id: int
    t_status: str
    scientist: int          # requester UIN
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


_PLATE_TYPE_BY_ROLE = {
    "MASTER": PlateType.MOTHER, "SCREENING": PlateType.ASSAY,
    "HIT_COLLECTION": PlateType.CHERRY_PICK, "VENDOR": PlateType.COMPOUND_STORAGE,
}
_PLATE_STATUS = {
    "Active": (PlateStatus.STORED, []), "AVAIL": (PlateStatus.STORED, []),
    "Inactive": (PlateStatus.DEPLETED, ["legacy:inactive"]),
}
_LOAN_ITEM_STATUS = {
    "COUT_REQ": LoanItemStatus.REQUESTED, "COUT_WSCAN": LoanItemStatus.APPROVED,
    "ASSIGNED": LoanItemStatus.CHECKED_OUT,
    "CIN_REQ": LoanItemStatus.RETURN_PENDING, "CIN_WSCAN": LoanItemStatus.RETURN_PENDING,
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
    parts: list[str] = []
    if s.set_state:
        parts.append(f"State: {s.set_state}")
    if s.scientist and s.scientist in account_names:
        parts.append(f"Scientist: {account_names[s.scientist]}")
    if s.generating_conditions:
        parts.append(s.generating_conditions)
    return "\n".join(parts) if parts else None


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


def read_legacy(dsn: str) -> LegacyData:
    """Read every needed legacy table once into dataclasses via pymysql.
    `dsn` = mysql://user:pass@host:port/dbname."""
    u = urlparse(dsn)
    conn = pymysql.connect(
        host=u.hostname, port=u.port or 3306, user=u.username,
        password=u.password or "", database=u.path.lstrip("/"),
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        d = LegacyData()
        with conn.cursor() as cur:
            cur.execute(f"SELECT library_id, library_name, library_type FROM {_P}LIBRARY")
            d.libraries = [LegacyLibrary(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT set_id, set_type, set_name, set_state, scientist, "
                        f"generating_conditions, library_id FROM {_P}SET")
            d.sets = [LegacySet(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT set_id, parent_id FROM {_P}SET_PARENT")
            d.set_parents = [LegacySetParent(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT set_id, plate_id FROM {_P}SET_PLATE")
            d.set_plates = [LegacySetPlate(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT plate_id, cdd_plate_id, plate_barcode, plate_name, "
                        f"plate_status, plate_role, library_id FROM {_P}PLATE")
            d.plates = [LegacyPlate(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT transaction_id, t_status, scientist, last_activity_date "
                        f"FROM {_P}TRANSACTIONS WHERE t_status = 'OPEN'")
            d.transactions = [LegacyTransaction(**r) for r in cur.fetchall()]
            cur.execute(f"SELECT plate_id, p_status, transaction_id FROM {_P}TRANSACTION_PLATE")
            d.transaction_plates = [LegacyTransactionPlate(**r) for r in cur.fetchall()]
            cur.execute("SELECT UIN AS uin, netid, email, alt_email, "
                        "firstName AS first_name, lastName AS last_name FROM account")
            d.accounts = [LegacyAccount(**r) for r in cur.fetchall()]
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
                workspace_id, cdd_vault_id, p.cdd_plate_id)
        if cellar_id is None:
            hit = await resolve_barcode(plate_repo, workspace_id, p.plate_barcode)
            cellar_id = hit.id if hit is not None else None
        if cellar_id is None:
            unmatched.append(UnmatchedPlate(p.plate_id, p.plate_barcode, p.cdd_plate_id,
                                            "no cdd_plate_sync row and no barcode match"))
        else:
            matched[p.plate_id] = cellar_id
    return matched, unmatched


def _set_plate_status(plate, target: PlateStatus) -> None:
    """Drive plate.status to `target` through valid transitions; idempotent.
    Only STORED and DEPLETED are ever requested here."""
    if plate.status == target:
        return
    if target in VALID_PLATE_TRANSITIONS[plate.status]:
        plate.transition_status(target)
        return
    # DEPLETED is unreachable in one hop from REGISTERED — go via STORED.
    if target == PlateStatus.DEPLETED and PlateStatus.STORED in VALID_PLATE_TRANSITIONS[plate.status]:
        plate.transition_status(PlateStatus.STORED)
        plate.transition_status(PlateStatus.DEPLETED)
        return
    raise ValueError(f"cannot reach {target} from {plate.status} for plate {plate.id}")


async def apply_plate_ownership(legacy, matched, *, plate_repo, tag_repo, plate_tag_link_repo,
                                uow, workspace_id, internal_org_id, actor_id) -> dict[str, int]:
    stats = {"classified": 0, "skipped_unmapped": 0, "inactive_tagged": 0}
    inactive_tag_id: uuid.UUID | None = None   # created lazily, once
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
            _set_plate_status(plate, pstatus)
            changed = True
        if changed:
            await plate_repo.save(plate)
            stats["classified"] += 1
        if "legacy:inactive" in tags:
            if inactive_tag_id is None:
                tag = await tag_repo.get_or_create(
                    workspace_id, TagName(key="legacy", value="inactive"), created_by=actor_id)
                inactive_tag_id = tag.id
            if await plate_tag_link_repo.add(workspace_id, cellar_id, inactive_tag_id,
                                             assigned_by=actor_id):
                stats["inactive_tagged"] += 1
    return stats


async def backfill_null_owner(session, *, workspace_id, internal_org_id) -> int:
    """S2-deferred backfill: every NULL-owner plate in this workspace -> internal org.
    Bulk SQL (matches alembic backfill precedent 042/021); bumps version for OCC safety."""
    result = await session.execute(sa.text(
        "UPDATE registered_plates SET owner_org_id = :org, version = version + 1, "
        "updated_at = now() WHERE workspace_id = :ws AND owner_org_id IS NULL"
    ), {"org": internal_org_id, "ws": workspace_id})
    return result.rowcount or 0


@dataclass(frozen=True)
class GroupSpec:
    key: str
    name: str
    group_type: str | None
    description: str | None
    parent_key: str | None


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
        specs.append(GroupSpec(f"set:{s.set_id}", s.set_name, s.set_type,
                               compose_set_description(s, account_names), parent_key))
    # topological order: roots first, then nodes whose parent already emitted
    ordered: list[GroupSpec] = []
    emitted: set[str] = set()
    pending = list(specs)
    while pending:
        progressed = False
        rest = []
        for g in pending:
            if g.parent_key is None or g.parent_key in emitted:
                ordered.append(g); emitted.add(g.key); progressed = True
            else:
                rest.append(g)
        pending = rest
        if not progressed:   # broken parent ref (shouldn't happen) — emit as roots
            for g in pending:
                ordered.append(GroupSpec(g.key, g.name, g.group_type, g.description, None))
            break
    return ordered


_GROUP_TYPE_VOCAB = "plate_group_type"


async def apply_group_tree(specs, *, group_repo, workspace_id, owner_org_id, actor_id):
    key_to_group: dict[str, uuid.UUID] = {}
    for g in specs:
        parent_id = key_to_group.get(g.parent_key) if g.parent_key else None
        existing = await group_repo.find_by_name(workspace_id, owner_org_id, parent_id, g.name)
        if existing is not None:
            key_to_group[g.key] = existing.id
            continue
        group = PlateGroup.create(
            workspace_id=workspace_id, owner_org_id=owner_org_id, name=g.name,
            created_by=actor_id, parent_group_id=parent_id,
            group_type=g.group_type, description=g.description,
        )
        await group_repo.save(group)
        key_to_group[g.key] = group.id
    return key_to_group


async def assign_plates_to_groups(legacy, key_to_group, matched, *, plate_repo, workspace_id) -> int:
    n = 0
    for sp in legacy.set_plates:
        group_id = key_to_group.get(f"set:{sp.set_id}")
        cellar_id = matched.get(sp.plate_id)
        if group_id is None or cellar_id is None:
            continue
        plate = await plate_repo.find_by_id_in_workspace(workspace_id, cellar_id)
        if plate is None or plate.group_id == group_id:   # guard: no-op if unchanged (avoids event spam)
            continue
        plate.assign_to_group(group_id)
        await plate_repo.save(plate)
        n += 1
    return n


async def seed_group_type_vocab(legacy, *, cv_repo, workspace_id, actor_id) -> None:
    values = sorted({s.set_type for s in legacy.sets if s.set_type})
    if not values:
        return
    vocab = await cv_repo.find_by_name(workspace_id, _GROUP_TYPE_VOCAB)
    if vocab is None:
        vocab = ControlledVocabulary.create(workspace_id=workspace_id, name=_GROUP_TYPE_VOCAB,
                                             terms=values, created_by=actor_id)
    else:
        for v in values:
            if v not in vocab.terms:
                vocab.add_term(v)
    await cv_repo.save(vocab)


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
    for txn in legacy.transactions:              # already filtered to OPEN at read time
        email = account_email.get(txn.scientist)
        user_id = user_map.get(email) if email else None
        if user_id is None:
            unresolved.append(UnresolvedRequester(
                txn.transaction_id, txn.scientist, email,
                "no email" if not email else "email not in --user-map"))
            continue
        items: list[LoanItemSpec] = []
        for tp in tps_by_txn.get(txn.transaction_id, []):
            cellar_id = matched.get(tp.plate_id)
            if cellar_id is None:
                continue                          # unmatched plate — skip item (reported in Task 3)
            items.append(LoanItemSpec(cellar_id, map_loan_item_status(tp.p_status)))
        if items:
            specs.append(LoanSpec(txn.transaction_id, user_id,
                                  due_date_from(txn.last_activity_date), items))
    return specs, unresolved


async def apply_loan(spec, *, loan_repo, workspace_id, internal_org_id) -> bool:
    plate_ids = [i.cellar_plate_id for i in spec.items]
    already = await loan_repo.active_plate_ids(workspace_id, plate_ids)
    if set(plate_ids) <= already:          # every plate already in an active loan → idempotent skip
        return False
    # Create with all items REQUESTED, then drive subsets forward via the aggregate.
    loan = PlateLoan.request(
        workspace_id=workspace_id, owner_org_id=internal_org_id,
        borrower_org_id=internal_org_id, requested_by=spec.requester_user_id,
        plate_ids=plate_ids, auto_approved=False, due_date=spec.due_date,
        notes="Migrated from legacy plate-tracker",
    )
    item_by_plate = {it.plate_id: it for it in loan.items}
    target_by_plate = {i.cellar_plate_id: i.target for i in spec.items}
    ids = lambda *ts: [item_by_plate[pid].id for pid, t in target_by_plate.items() if t in ts]
    # REQUESTED items: leave as-is. Others: approve then push to their target.
    fwd = ids(LoanItemStatus.CHECKED_OUT, LoanItemStatus.RETURN_PENDING)
    if fwd:
        loan.approve_items(fwd, approved_by=spec.requester_user_id)   # legacy authorized_by is NULL → self-approve
        loan.confirm_checkout(fwd)
    ret = ids(LoanItemStatus.RETURN_PENDING)
    if ret:
        loan.request_return(ret)
    await loan_repo.save(loan)
    return True
