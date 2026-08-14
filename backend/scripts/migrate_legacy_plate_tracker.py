"""Migrate the legacy plate-tracker (MySQL) into Cellar. See Task 7 for the runbook."""
from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

import pymysql
import structlog

from cellar.domain.inventory.enums import LoanItemStatus, PlateStatus, PlateType

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
