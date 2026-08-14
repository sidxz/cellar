# S6 — Legacy Plate-Tracker Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One idempotent script that ports the legacy MySQL plate-tracker (libraries, sets, plates, open checkouts) into Cellar — setting plate ownership + classification, building the PlateGroup tree, and recreating the 15 open loans — plus the S2-deferred NULL-owner ownership backfill and a cutover runbook.

**Architecture:** A single `scripts/migrate_legacy_plate_tracker.py`, structured as a **functional core + imperative shell**: pure functions (value mappers, tree planner, loan planner — unit-tested, no DB) and thin async apply-phases that drive the existing Cellar aggregates/repositories through a `AsyncUnitOfWork` (integration-tested against a real Postgres). Legacy data is read once via `pymysql` into dataclasses. All writes go through the domain aggregates (`RegisteredPlate.update/transition_status/assign_to_group`, `PlateGroup.create`, `PlateLoan.request` + transition verbs) — never raw ORM — except the ownership backfill, which is a bulk SQL UPDATE (matches alembic backfill precedent 042/021). `uow.commit()` returns domain events without dispatching them, so the import fires no audit/notification side-effects.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async (asyncpg) for the Cellar side, `pymysql` (new, pure-Python, script-only) for the legacy MySQL read, structlog, argparse, `uv run`.

## Global Constraints

- **Idempotent + re-runnable.** Groups dedupe via `PlateGroupRepository.find_by_name`; plate mutations are value-guarded (only call a mutator if the field actually changes); loans pre-check `PlateLoanRepository.active_plate_ids`; the backfill is `WHERE owner_org_id IS NULL`. A second run makes zero new writes.
- **Single workspace, single internal org.** All migrated plates/groups are owned by `--internal-org-id`; all legacy users belong to that one org (legacy has no org model). Loans are same-org (`owner_org_id == borrower_org_id == internal org`).
- **All writes through aggregates via `AsyncUnitOfWork`.** Construct `uow = AsyncUnitOfWork(session_factory)`; `async with uow:`; repos take `uow`; call `await uow.commit()` and **discard** the returned events (no dispatch). Only the NULL-owner backfill uses raw `session.execute(sa.text(...))`.
- **Invocation:** `cd backend && uv run python scripts/migrate_legacy_plate_tracker.py <args>`. Cellar DB from `DATABASE_URL` (via `DatabaseSettings().database_url`); legacy DB from `--legacy-dsn`.
- **Closed history is NOT migrated** (spec §12.6/§13): only `t_status='OPEN'` transactions. `APPS_PLATE_TRACKER_TRANSACTION_PLATE` is a current-state table (PK `plate_id`), holding exactly the 203 rows of the 15 open loans; `ACTIVITY_LOG` closed-loan reconstruction is explicitly out of scope.
- **No service-key email→user lookup exists** in Sentinel. Requester resolution = legacy `account.UIN → email` → operator-supplied `--user-map` CSV (`email,sentinel_user_id`); unmatched → reported and that loan skipped.
- **`pymysql` added to `[project.dependencies]`** (pure-Python, no build deps). Removable after cutover.

### Verbatim legacy value domains (extracted from the dump — the source of truth, NOT spec §12's assumptions)

- `PLATE.plate_role` ∈ {`MASTER`, `SCREENING`, `HIT_COLLECTION`, `VENDOR`} — **no `MASTER_TWIN`** (that is a `set_type`, not a plate role).
- `PLATE.plate_status` ∈ {`Active` (1694), `AVAIL` (373), `Inactive` (9)} — note `AVAIL`, absent from spec §12.4.
- `SET.set_type` ∈ {`SCREENING`, `HIT_COLLECTION`, `VENDOR`, `MASTER_TWIN`}.
- `TRANSACTION_PLATE.p_status` ∈ {`ASSIGNED` (108), `COUT_REQ` (71), `CIN_REQ` (24)}.
- `TRANSACTIONS.t_status` ∈ {`OPEN` (15), `CLOSED` (630)}; open rows have `authorized_by = NULL`; only timestamp is `last_activity_date`.

### Locked mappings (a task must NOT "correct" these back to spec §12)

| Legacy | Cellar | Notes |
|---|---|---|
| `plate_role` MASTER | `PlateType.MOTHER` (`mother`) | |
| `plate_role` SCREENING | `PlateType.ASSAY` (`assay`) | |
| `plate_role` HIT_COLLECTION | `PlateType.CHERRY_PICK` (`cherry_pick`) | |
| `plate_role` VENDOR | `PlateType.COMPOUND_STORAGE` (`compound_storage`) | |
| `plate_status` Active | `PlateStatus.STORED` | |
| `plate_status` **AVAIL** | `PlateStatus.STORED` | available-in-inventory = stored; only stored/depleted/disposed exist as targets |
| `plate_status` Inactive | `PlateStatus.DEPLETED` + tag `legacy:inactive` | |
| `set_type` (any) | `PlateGroup.group_type` = legacy string verbatim | + seeded into `plate_group_type` CV |
| `p_status` COUT_REQ | `LoanItemStatus.REQUESTED` | |
| `p_status` ASSIGNED | `LoanItemStatus.CHECKED_OUT` | |
| `p_status` CIN_REQ | `LoanItemStatus.RETURN_PENDING` | |
| (defensive) COUT_WSCAN | `LoanItemStatus.APPROVED` | absent in dump; include in map |
| (defensive) CIN_WSCAN | `LoanItemStatus.RETURN_PENDING` | absent in dump; include in map |

Unknown `plate_role`/`plate_status`/`p_status` value → raise inside the pure mapper; the caller catches, reports the row, and skips its classification/loan (never guesses).

---

## File Structure

- **Create** `backend/scripts/migrate_legacy_plate_tracker.py` — the whole migration: legacy dataclasses, `pymysql` reader, pure mappers/planners, async apply-phases, `main()`. Module docstring = the cutover runbook.
- **Create** `backend/tests/unit/scripts/test_legacy_plate_tracker_core.py` — unit tests for the pure functions.
- **Create** `backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py` — real-DB tests for the apply-phases (mirrors `test_backfill_batch_identifier_mirrors.py`, uses the `session_factory` fixture from the root conftest).
- **Modify** `backend/pyproject.toml` — add `pymysql` to `[project.dependencies]`.

### Key signatures (consumed from the existing codebase — copy verbatim)

```python
# cellar.domain.inventory.enums
class PlateType(StrEnum): COMPOUND_STORAGE="compound_storage"; MOTHER="mother"; ASSAY="assay"; CHERRY_PICK="cherry_pick"; REPLICATE="replicate"  # + others
class PlateStatus(StrEnum): REGISTERED="registered"; IN_USE="in_use"; STORED="stored"; DEPLETED="depleted"; DISPOSED="disposed"
class LoanItemStatus(StrEnum): REQUESTED="requested"; APPROVED="approved"; CHECKED_OUT="checked_out"; RETURN_PENDING="return_pending"; RETURNED="returned"; DENIED="denied"; CANCELLED="cancelled"
VALID_PLATE_TRANSITIONS = {REGISTERED:{IN_USE,STORED,DISPOSED}, IN_USE:{STORED,DEPLETED}, STORED:{IN_USE,DEPLETED,DISPOSED}, DEPLETED:{DISPOSED}, DISPOSED:set()}

# cellar.domain.inventory.registered_plate.RegisteredPlate
def update(self, *, plate_label=None, format=..., plate_type=None, project_id=..., owner_org_id=..., storage_location_id=..., template_id=..., notes=..., custom_fields=...) -> None
def transition_status(self, new_status: PlateStatus) -> None   # guarded by VALID_PLATE_TRANSITIONS
def assign_to_group(self, group_id: uuid.UUID | None) -> None  # emits event every call; guard by comparing current group_id

# cellar.domain.inventory.plate_group.PlateGroup
@classmethod
def create(cls, *, workspace_id, owner_org_id, name, created_by, parent_group_id=None, group_type=None, description=None) -> PlateGroup

# cellar.domain.inventory.plate_loan.PlateLoan
@classmethod
def request(cls, *, workspace_id, owner_org_id, borrower_org_id, requested_by, plate_ids: list[uuid.UUID], auto_approved: bool, due_date: date | None = None, notes: str | None = None) -> PlateLoan
def approve_items(self, item_ids: list[uuid.UUID], *, approved_by: uuid.UUID) -> list[LoanItem]
def confirm_checkout(self, item_ids: list[uuid.UUID]) -> list[LoanItem]
def request_return(self, item_ids: list[uuid.UUID]) -> list[LoanItem]
# loan.items -> list[LoanItem]; LoanItem has .id and .plate_id and .status

# Repos (all take AsyncUnitOfWork)
SQLAlchemyRegisteredPlateRepository(uow);  .find_by_id_in_workspace(ws, id); .find_by_barcode(ws, barcode); .save(agg)
SQLAlchemyPlateGroupRepository(uow);       .find_by_name(ws, owner_org_id, parent_group_id, name); .save(agg)
SQLAlchemyPlateLoanRepository(uow);        .active_plate_ids(ws, plate_ids)->set; .save(agg)
CddPlateSyncRepository(uow);               .find_plate_id_by_cdd_plate_id(ws, cdd_vault_id: str, cdd_plate_id: int) -> uuid.UUID | None
SQLAlchemyControlledVocabularyRepository(uow); .find_by_name(ws, name); .save(agg)
# cellar.application.inventory.barcode_resolution
async def resolve_barcode(repo, workspace_id, raw: str) -> RegisteredPlate | None

# cellar.infrastructure.persistence.settings.DatabaseSettings().database_url  (reads DATABASE_URL)
# cellar.infrastructure.persistence.unit_of_work.AsyncUnitOfWork(session_factory)
# cellar.domain.workspace_config.controlled_vocabulary.ControlledVocabulary.create(*, workspace_id, name, terms=None, created_by); .add_term(term)
```

---

## Task 1: Legacy reader, dataclasses, CLI skeleton, `pymysql` dep

**Files:**
- Create: `backend/scripts/migrate_legacy_plate_tracker.py`
- Modify: `backend/pyproject.toml` (add `pymysql`)
- Test: `backend/tests/unit/scripts/test_legacy_plate_tracker_core.py`

**Interfaces:**
- Produces: dataclasses `LegacyLibrary`, `LegacySet`, `LegacySetParent`, `LegacySetPlate`, `LegacyPlate`, `LegacyTransaction`, `LegacyTransactionPlate`, `LegacyAccount`, and container `LegacyData` (all fields below). `read_legacy(dsn: str) -> LegacyData`. `build_account_email_map(accounts: list[LegacyAccount]) -> dict[int, str]` (UIN→email, skipping NULL/`AUTO_RAN*`).

- [ ] **Step 1: add the dependency**

Edit `backend/pyproject.toml`, add to `[project.dependencies]` (keep alphabetical-ish with the others):
```toml
  "pymysql>=1.1",  # legacy plate-tracker migration read (scripts/migrate_legacy_plate_tracker.py); removable post-cutover
```
Run: `cd backend && uv sync` — Expected: resolves, installs pymysql.

- [ ] **Step 2: write the failing test** — `backend/tests/unit/scripts/test_legacy_plate_tracker_core.py`

```python
from __future__ import annotations

from scripts.migrate_legacy_plate_tracker import LegacyAccount, build_account_email_map


def _acct(uin: int, netid: str, email: str | None, alt: str | None = None) -> LegacyAccount:
    return LegacyAccount(uin=uin, netid=netid, email=email, alt_email=alt,
                         first_name="F", last_name="L")


def test_build_account_email_map_uses_email_and_skips_placeholders():
    accounts = [
        _acct(124007171, "sid", "sid@tamu.edu"),
        _acct(999, "AUTO_RAN999", "AUTO_RAN999"),   # placeholder → skip
        _acct(1000, "bob", None, alt="bob@x.org"),   # null email → fall back to alt_email
        _acct(1001, "nul", None),                    # no email at all → absent
    ]
    m = build_account_email_map(accounts)
    assert m == {124007171: "sid@tamu.edu", 1000: "bob@x.org"}
```

- [ ] **Step 3: run it, verify it fails**

Run: `cd backend && uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py -q`
Expected: FAIL (ModuleNotFoundError / ImportError — file/functions don't exist).

- [ ] **Step 4: create the script with dataclasses, reader, and the account-map helper**

`backend/scripts/migrate_legacy_plate_tracker.py` — module docstring is a placeholder for now (Task 7 replaces it with the runbook). Add:

```python
"""Migrate the legacy plate-tracker (MySQL) into Cellar. See Task 7 for the runbook."""
from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import pymysql
import structlog

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
```

Note: `SET` is a MySQL reserved word but the prefixed table name `APPS_PLATE_TRACKER_SET` is not, so no backticks needed. `TRANSACTIONS` is filtered to `OPEN` at read time.

- [ ] **Step 5: run the test, verify it passes**

Run: `cd backend && uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py -q`
Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/unit/scripts/test_legacy_plate_tracker_core.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(scripts): legacy plate-tracker reader + dataclasses (S6 task 1)"
```

---

## Task 2: Pure value mappers

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py`
- Test: `backend/tests/unit/scripts/test_legacy_plate_tracker_core.py`

**Interfaces:**
- Consumes: enums from `cellar.domain.inventory.enums`.
- Produces: `map_plate_type(role: str) -> PlateType`; `map_plate_status(status: str) -> tuple[PlateStatus, list[str]]` (status + tags); `map_loan_item_status(p_status: str) -> LoanItemStatus`; `due_date_from(last_activity: datetime) -> date`; `compose_set_description(s: LegacySet, account_names: dict[int, str]) -> str | None`. Unknown enum-like value → `raise ValueError`.

- [ ] **Step 1: write the failing tests** (append to the unit test file)

```python
from datetime import date, datetime

import pytest

from cellar.domain.inventory.enums import LoanItemStatus, PlateStatus, PlateType
from scripts.migrate_legacy_plate_tracker import (
    LegacySet, compose_set_description, due_date_from,
    map_loan_item_status, map_plate_status, map_plate_type,
)


@pytest.mark.parametrize("role,expected", [
    ("MASTER", PlateType.MOTHER), ("SCREENING", PlateType.ASSAY),
    ("HIT_COLLECTION", PlateType.CHERRY_PICK), ("VENDOR", PlateType.COMPOUND_STORAGE),
])
def test_map_plate_type(role, expected):
    assert map_plate_type(role) == expected


def test_map_plate_type_unknown_raises():
    with pytest.raises(ValueError):
        map_plate_type("MASTER_TWIN")   # a set_type, never a plate_role


@pytest.mark.parametrize("status,expected_status,expected_tags", [
    ("Active", PlateStatus.STORED, []),
    ("AVAIL", PlateStatus.STORED, []),
    ("Inactive", PlateStatus.DEPLETED, ["legacy:inactive"]),
])
def test_map_plate_status(status, expected_status, expected_tags):
    assert map_plate_status(status) == (expected_status, expected_tags)


def test_map_plate_status_unknown_raises():
    with pytest.raises(ValueError):
        map_plate_status("Frozen")


@pytest.mark.parametrize("p,expected", [
    ("COUT_REQ", LoanItemStatus.REQUESTED), ("ASSIGNED", LoanItemStatus.CHECKED_OUT),
    ("CIN_REQ", LoanItemStatus.RETURN_PENDING),
])
def test_map_loan_item_status(p, expected):
    assert map_loan_item_status(p) == expected


def test_due_date_is_last_activity_plus_14_days():
    assert due_date_from(datetime(2024, 1, 4, 11, 15)) == date(2024, 1, 18)


def test_compose_set_description_includes_state_scientist_conditions():
    s = LegacySet(set_id=1, set_type="SCREENING", set_name="S", set_state="Solubilized",
                  scientist=42, generating_conditions="DMSO 10mM", library_id=None)
    out = compose_set_description(s, {42: "Ann Lee"})
    assert "Solubilized" in out and "Ann Lee" in out and "DMSO 10mM" in out
```

- [ ] **Step 2: run, verify fail**

Run: `cd backend && uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py -q`
Expected: FAIL (ImportError on the new names).

- [ ] **Step 3: implement the mappers** (append to the script, after the dataclasses)

```python
from datetime import date, timedelta

from cellar.domain.inventory.enums import LoanItemStatus, PlateStatus, PlateType

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
```

- [ ] **Step 4: run, verify pass**

Run: `cd backend && uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py -q`
Expected: PASS (all mapper tests green).

- [ ] **Step 5: commit**

```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/unit/scripts/test_legacy_plate_tracker_core.py
git commit -m "feat(scripts): legacy value mappers (plate type/status, loan status, due date) (S6 task 2)"
```

---

## Task 3: Plate matching (cdd_plate_sync → barcode fallback)

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py`
- Test: `backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py`

**Interfaces:**
- Consumes: `CddPlateSyncRepository`, `SQLAlchemyRegisteredPlateRepository`, `resolve_barcode`.
- Produces: `@dataclass UnmatchedPlate(legacy_plate_id, plate_barcode, cdd_plate_id, reason)`. `async def match_plates(legacy, *, plate_repo, cdd_repo, workspace_id, cdd_vault_id) -> tuple[dict[int, uuid.UUID], list[UnmatchedPlate]]` — maps legacy `plate_id` → Cellar plate id. Chain per plate: `cdd_plate_id` via `cdd_repo.find_plate_id_by_cdd_plate_id` → else `resolve_barcode(plate_repo, ws, plate_barcode)` → else unmatched.

- [ ] **Step 1: write the failing integration test**

`backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py`:
```python
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
```

Note on plate 2: `resolve_barcode` tries `"42"` (exact), then `zfill(6)` = `"000042"` — the seeded barcode. `barcode_candidates("42")` yields `["42", "000042"]`, so the seed matches.

- [ ] **Step 2: run, verify fail**

Run: `cd backend && uv run pytest tests/integration/scripts/test_migrate_legacy_plate_tracker.py -q`
Expected: FAIL (ImportError: `match_plates`).

- [ ] **Step 3: implement `match_plates`** (append to the script)

```python
from cellar.application.inventory.barcode_resolution import resolve_barcode


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
```

- [ ] **Step 4: run, verify pass**

Run: `cd backend && uv run pytest tests/integration/scripts/test_migrate_legacy_plate_tracker.py -q`
Expected: PASS.

- [ ] **Step 5: commit**

```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py
git commit -m "feat(scripts): legacy plate matching via cdd_plate_sync then barcode (S6 task 3)"
```

---

## Task 4: Ownership + classification phase, and NULL-owner backfill

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py`
- Test: `backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py`

**Interfaces:**
- Consumes: `match_plates` output, `map_plate_type`, `map_plate_status`, `SQLAlchemyRegisteredPlateRepository`.
- Produces: `_set_plate_status(plate, target: PlateStatus) -> None` (guarded, multi-hop, idempotent); `async def apply_plate_ownership(legacy, matched, *, plate_repo, uow, workspace_id, internal_org_id) -> dict[str, int]` (sets owner_org_id + plate_type + status on each matched plate); `async def backfill_null_owner(session, *, workspace_id, internal_org_id) -> int` (bulk SQL). Applies the `legacy:inactive` tag is **out of scope here** (tags need the tag repo; record it in the returned stats as `inactive_needs_tag` and note in the report — the plan keeps this task to the plate aggregate; tagging is a follow-up bullet in Task 7's report).

- [ ] **Step 1: write the failing integration test** (append)

```python
from cellar.domain.inventory.enums import PlateStatus, PlateType
from scripts.migrate_legacy_plate_tracker import (
    apply_plate_ownership, backfill_null_owner,
)


@pytest.mark.asyncio
async def test_apply_ownership_sets_owner_type_status_and_is_idempotent(session_factory):
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
            matched, _ = await match_plates(legacy, plate_repo=plate_repo, cdd_repo=cdd_repo,
                                            workspace_id=ws, cdd_vault_id=VAULT)
            await apply_plate_ownership(legacy, matched, plate_repo=plate_repo, uow=uow,
                                        workspace_id=ws, internal_org_id=org)
            await uow.commit()
    async with session_factory() as s:
        rows = (await s.execute(sa.text(
            "SELECT id, owner_org_id, plate_type, status FROM registered_plates "
            "WHERE id IN (:a, :b)"), {"a": active, "b": inactive})).mappings().all()
    by_id = {r["id"]: r for r in rows}
    assert by_id[active]["owner_org_id"] == org
    assert by_id[active]["plate_type"] == PlateType.MOTHER.value
    assert by_id[active]["status"] == PlateStatus.STORED.value
    assert by_id[inactive]["plate_type"] == PlateType.COMPOUND_STORAGE.value
    assert by_id[inactive]["status"] == PlateStatus.DEPLETED.value   # registered→stored→depleted


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
```

- [ ] **Step 2: run, verify fail**

Run: `cd backend && uv run pytest tests/integration/scripts/test_migrate_legacy_plate_tracker.py -k "ownership or backfill" -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: implement the phase + helpers** (append to the script)

```python
import sqlalchemy as sa
from cellar.domain.inventory.enums import VALID_PLATE_TRANSITIONS


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


async def apply_plate_ownership(legacy, matched, *, plate_repo, uow,
                                workspace_id, internal_org_id) -> dict[str, int]:
    stats = {"classified": 0, "skipped_unmapped": 0, "inactive_needs_tag": 0}
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
            stats["inactive_needs_tag"] += 1
    return stats


async def backfill_null_owner(session, *, workspace_id, internal_org_id) -> int:
    """S2-deferred backfill: every NULL-owner plate in this workspace -> internal org.
    Bulk SQL (matches alembic backfill precedent 042/021); bumps version for OCC safety."""
    result = await session.execute(sa.text(
        "UPDATE registered_plates SET owner_org_id = :org, version = version + 1, "
        "updated_at = now() WHERE workspace_id = :ws AND owner_org_id IS NULL"
    ), {"org": internal_org_id, "ws": workspace_id})
    return result.rowcount or 0
```

Note: the `legacy:inactive` tag is counted but not written here (tagging needs the tag repo/use case; the count surfaces in Task 7's report as a manual follow-up so this task stays a clean plate-aggregate change). If the reviewer prefers, wiring `TagRepository.get_or_create` is a small add — but keep it out of the red-green cycle for this task.

- [ ] **Step 4: run, verify pass**

Run: `cd backend && uv run pytest tests/integration/scripts/test_migrate_legacy_plate_tracker.py -k "ownership or backfill" -q`
Expected: PASS.

- [ ] **Step 5: commit**

```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py
git commit -m "feat(scripts): plate ownership+classification phase and NULL-owner backfill (S6 task 4)"
```

---

## Task 5: PlateGroup tree + plate assignment + CV seeding

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py`
- Test: `backend/tests/unit/scripts/test_legacy_plate_tracker_core.py` (planner) + `backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py` (apply)

**Interfaces:**
- Produces (pure): `@dataclass GroupSpec(key, name, group_type, description, parent_key)` where `key`/`parent_key` are stable strings (`lib:{id}` / `set:{id}`, `parent_key=None` for roots). `plan_group_tree(legacy, account_names) -> list[GroupSpec]` — one root per library, one node per set (parent = its `SET_PARENT` set if present, else its library root, else None), topologically ordered (parents before children).
- Produces (I/O): `async def apply_group_tree(specs, *, group_repo, workspace_id, owner_org_id, actor_id) -> dict[str, uuid.UUID]` (key→group id, idempotent via `find_by_name`); `async def assign_plates_to_groups(legacy, key_to_group, matched, *, plate_repo, workspace_id) -> int` (SET_PLATE → `assign_to_group`, guarded); `async def seed_group_type_vocab(legacy, *, cv_repo, workspace_id, actor_id) -> None`.

- [ ] **Step 1: write the failing planner unit test** (append to unit file)

```python
from scripts.migrate_legacy_plate_tracker import (
    LegacyLibrary, LegacySetParent, plan_group_tree,
)


def test_plan_group_tree_roots_by_library_and_nests_sets():
    legacy = LegacyData(
        libraries=[LegacyLibrary(10, "Lib A", "SacchettiniLibrary")],
        sets=[
            LegacySet(1, "MASTER_TWIN", "Parent Set", "Dry", None, None, 10),
            LegacySet(2, "SCREENING", "Child Set", "Solubilized", None, None, 10),
            LegacySet(3, "VENDOR", "Orphan Set", None, None, None, None),  # no library
        ],
        set_parents=[LegacySetParent(set_id=2, parent_id=1)],  # set2 child of set1
    )
    specs = plan_group_tree(legacy, {})
    by_key = {g.key: g for g in specs}
    assert by_key["lib:10"].parent_key is None and by_key["lib:10"].name == "Lib A"
    assert by_key["set:1"].parent_key == "lib:10"       # top-level set → library root
    assert by_key["set:2"].parent_key == "set:1"        # nested via SET_PARENT
    assert by_key["set:3"].parent_key is None           # orphan set → its own root
    # parents precede children
    order = [g.key for g in specs]
    assert order.index("lib:10") < order.index("set:1") < order.index("set:2")
```

- [ ] **Step 2: run, verify fail** — `uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py -k tree -q` → FAIL.

- [ ] **Step 3: implement the planner** (append to script)

```python
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
```

- [ ] **Step 4: run, verify pass** — `uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py -k tree -q` → PASS.

- [ ] **Step 5: write the failing apply integration test** (append to integration file)

```python
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from scripts.migrate_legacy_plate_tracker import (
    LegacyLibrary, LegacySet, LegacySetParent, LegacySetPlate,
    apply_group_tree, assign_plates_to_groups, plan_group_tree,
)


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
            "SELECT name, parent_group_id FROM plate_groups WHERE workspace_id = :ws "
            "AND owner_org_id = :o ORDER BY name"), {"ws": ws, "o": org})).mappings().all()
        assert [g["name"] for g in groups] == ["Lib Z", "Set One"]   # unique ws → no dupes/contamination
        grp = (await s.execute(sa.text("SELECT group_id FROM registered_plates WHERE id = :id"),
                               {"id": plate})).scalar_one()
        assert grp is not None
```

- [ ] **Step 6: run, verify fail** — `-k "group_tree"` → FAIL (ImportError).

- [ ] **Step 7: implement apply + assign + CV seed** (append to script)

```python
from cellar.domain.workspace_config.controlled_vocabulary import ControlledVocabulary

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
```

Import `PlateGroup` at the top of the script: `from cellar.domain.inventory.plate_group import PlateGroup`.

- [ ] **Step 8: run, verify pass** — `-k "group_tree"` → PASS.

- [ ] **Step 9: commit**

```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/unit/scripts/test_legacy_plate_tracker_core.py backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py
git commit -m "feat(scripts): PlateGroup tree build + plate assignment + CV seed (S6 task 5)"
```

---

## Task 6: Open loans → PlateLoan

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py`
- Test: unit (planner) + integration (apply)

**Interfaces:**
- Produces (pure): `@dataclass LoanItemSpec(cellar_plate_id, target: LoanItemStatus)`; `@dataclass LoanSpec(transaction_id, requester_user_id, due_date, items: list[LoanItemSpec])`; `@dataclass UnresolvedRequester(transaction_id, scientist_uin, email, reason)`. `plan_loans(legacy, matched, account_email, user_map) -> tuple[list[LoanSpec], list[UnresolvedRequester]]`.
- Produces (I/O): `async def apply_loan(spec, *, loan_repo, workspace_id, internal_org_id) -> bool` (returns False if all plates already in an active loan — idempotent skip). Drives item subsets to their target via the aggregate verbs.

- [ ] **Step 1: write the failing planner unit test** (append to unit file)

```python
from cellar.domain.inventory.enums import LoanItemStatus
from scripts.migrate_legacy_plate_tracker import (
    LegacyTransaction, LegacyTransactionPlate, plan_loans,
)


def test_plan_loans_resolves_requester_maps_states_and_reports_unresolved():
    import uuid as _uuid
    p_ok = _uuid.uuid4()
    legacy = LegacyData(
        transactions=[
            LegacyTransaction(1, "OPEN", 42, datetime(2024, 1, 4)),
            LegacyTransaction(2, "OPEN", 77, datetime(2024, 2, 1)),  # requester has no email
        ],
        transaction_plates=[
            LegacyTransactionPlate(plate_id=10, p_status="ASSIGNED", transaction_id=1),
            LegacyTransactionPlate(plate_id=11, p_status="COUT_REQ", transaction_id=1),
            LegacyTransactionPlate(plate_id=12, p_status="CIN_REQ", transaction_id=2),
        ],
    )
    matched = {10: p_ok, 11: _uuid.uuid4(), 12: _uuid.uuid4()}
    account_email = {42: "ann@x.org"}   # 77 absent
    user_map = {"ann@x.org": _uuid.uuid4()}
    specs, unresolved = plan_loans(legacy, matched, account_email, user_map)
    assert len(specs) == 1 and specs[0].transaction_id == 1
    assert specs[0].due_date.isoformat() == "2024-01-18"
    targets = {i.cellar_plate_id: i.target for i in specs[0].items}
    assert targets[p_ok] == LoanItemStatus.CHECKED_OUT
    assert list(targets.values()).count(LoanItemStatus.REQUESTED) == 1
    assert [u.transaction_id for u in unresolved] == [2]
```

- [ ] **Step 2: run, verify fail** — `-k plan_loans` → FAIL.

- [ ] **Step 3: implement `plan_loans`** (append to script)

```python
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
```

- [ ] **Step 4: run, verify pass** — `-k plan_loans` → PASS.

- [ ] **Step 5: write the failing apply integration test** (append to integration file)

```python
from cellar.domain.inventory.enums import LoanItemStatus
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from scripts.migrate_legacy_plate_tracker import LoanItemSpec, LoanSpec, apply_loan


@pytest.mark.asyncio
async def test_apply_loan_reaches_target_states_and_is_idempotent(session_factory):
    ws = uuid.uuid4()
    org = uuid.uuid4()
    p_out = uuid.uuid4(); p_req = uuid.uuid4(); p_ret = uuid.uuid4()
    async with session_factory() as s:
        for pid, bc in [(p_out, "900040"), (p_req, "900041"), (p_ret, "900042")]:
            await _seed_plate(s, plate_id=pid, barcode=bc, ws=ws, owner_org_id=org)
        await s.commit()
    requester = uuid.uuid4()
    spec = LoanSpec(transaction_id=1, requester_user_id=requester,
                    due_date=__import__("datetime").date(2024, 1, 18), items=[
        LoanItemSpec(p_out, LoanItemStatus.CHECKED_OUT),
        LoanItemSpec(p_req, LoanItemStatus.REQUESTED),
        LoanItemSpec(p_ret, LoanItemStatus.RETURN_PENDING),
    ])
    created_flags = []
    for _ in range(2):
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            loan_repo = SQLAlchemyPlateLoanRepository(uow)
            created_flags.append(await apply_loan(spec, loan_repo=loan_repo, workspace_id=ws,
                                                  internal_org_id=org))
            await uow.commit()
    assert created_flags == [True, False]   # 2nd run skips (active plates already loaned)
    async with session_factory() as s:
        statuses = dict((await s.execute(sa.text(
            "SELECT plate_id, status FROM plate_loan_items WHERE plate_id IN (:a,:b,:c)"),
            {"a": p_out, "b": p_req, "c": p_ret})).all())
    assert statuses[p_out] == LoanItemStatus.CHECKED_OUT.value
    assert statuses[p_req] == LoanItemStatus.REQUESTED.value
    assert statuses[p_ret] == LoanItemStatus.RETURN_PENDING.value
```

- [ ] **Step 6: run, verify fail** — `-k apply_loan` → FAIL.

- [ ] **Step 7: implement `apply_loan`** (append to script)

```python
from cellar.domain.inventory.plate_loan import PlateLoan


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
```

- [ ] **Step 8: run, verify pass** — `-k apply_loan` → PASS.

- [ ] **Step 9: commit**

```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/unit/scripts/test_legacy_plate_tracker_core.py backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py
git commit -m "feat(scripts): open-transaction → PlateLoan migration with state replay (S6 task 6)"
```

---

## Task 7: Orchestration, reports, `--dry-run`, runbook

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py` (add `main()`, argparse, phase wiring, report writing; replace the docstring with the runbook)
- Test: `backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py` (end-to-end summary)

**Interfaces:**
- Consumes: every phase above.
- Produces: `async def run_migration(session_factory, legacy, *, workspace_id, internal_org_id, cdd_vault_id, user_map, actor_id, report_dir, dry_run) -> dict` (summary counts); `main()`.

- [ ] **Step 1: write the failing end-to-end test** (append to integration file)

```python
from scripts.migrate_legacy_plate_tracker import run_migration


@pytest.mark.asyncio
async def test_run_migration_end_to_end_summary(session_factory, tmp_path):
    ws = uuid.uuid4()
    org = uuid.uuid4()
    plate = uuid.uuid4()
    async with session_factory() as s:
        await _seed_plate(s, plate_id=plate, barcode="900050", ws=ws, cdd_plate_id=301)
        await s.commit()
    requester = uuid.uuid4()
    legacy = LegacyData(
        libraries=[LegacyLibrary(10, "Lib E2E", "SacchettiniLibrary")],
        sets=[LegacySet(1, "SCREENING", "Set E2E", "Dry", 42, None, 10)],
        set_plates=[LegacySetPlate(set_id=1, plate_id=99)],
        plates=[LegacyPlate(99, 301, "x", "P", "Active", "MASTER", None)],
        transactions=[LegacyTransaction(1, "OPEN", 42, datetime(2024, 1, 4))],
        transaction_plates=[LegacyTransactionPlate(99, "ASSIGNED", 1)],
        accounts=[LegacyAccount(42, "ann", "ann@x.org", None, "Ann", "Lee")],
    )
    summary = await run_migration(
        session_factory, legacy, workspace_id=ws, internal_org_id=org,
        cdd_vault_id=VAULT, user_map={"ann@x.org": requester}, actor_id=org,
        report_dir=tmp_path, dry_run=False,
    )
    assert summary["plates_matched"] == 1
    assert summary["groups_created"] == 2   # library root + set
    assert summary["loans_created"] == 1
    assert summary["unmatched_plates"] == 0
    assert (tmp_path / "unmatched_plates.csv").exists()
```

- [ ] **Step 2: run, verify fail** — `-k end_to_end` → FAIL.

- [ ] **Step 3: implement `run_migration` + `main()` + reports** (append to script). Replace the module docstring with the runbook (Step 4).

```python
import csv
from pathlib import Path

from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_repository import (
    SQLAlchemyPlateLoanRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (
    SQLAlchemyControlledVocabularyRepository,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _write_csv(path: Path, rows: list, header: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows:
            w.writerow([getattr(r, h) for h in header])


async def run_migration(session_factory, legacy, *, workspace_id, internal_org_id,
                        cdd_vault_id, user_map, actor_id, report_dir, dry_run) -> dict:
    from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
    account_email = build_account_email_map(legacy.accounts)
    account_names = {a.uin: f"{a.first_name or ''} {a.last_name or ''}".strip()
                     for a in legacy.accounts}
    summary: dict[str, int] = {}
    report_dir = Path(report_dir)

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        plate_repo = SQLAlchemyRegisteredPlateRepository(uow)
        cdd_repo = CddPlateSyncRepository(uow)
        group_repo = SQLAlchemyPlateGroupRepository(uow)
        loan_repo = SQLAlchemyPlateLoanRepository(uow)
        cv_repo = SQLAlchemyControlledVocabularyRepository(uow)

        # Phase 0: NULL-owner backfill (S2-deferred)
        summary["owner_backfilled"] = await backfill_null_owner(
            uow.session, workspace_id=workspace_id, internal_org_id=internal_org_id)

        # Phase 1: match
        matched, unmatched = await match_plates(
            legacy, plate_repo=plate_repo, cdd_repo=cdd_repo,
            workspace_id=workspace_id, cdd_vault_id=cdd_vault_id)
        summary["plates_matched"] = len(matched)
        summary["unmatched_plates"] = len(unmatched)

        # Phase 2: ownership + classification
        own = await apply_plate_ownership(
            legacy, matched, plate_repo=plate_repo, uow=uow,
            workspace_id=workspace_id, internal_org_id=internal_org_id)
        summary["plates_classified"] = own["classified"]
        summary["inactive_needs_tag"] = own["inactive_needs_tag"]

        # Phase 3: groups + CV + assignment
        await seed_group_type_vocab(legacy, cv_repo=cv_repo,
                                    workspace_id=workspace_id, actor_id=actor_id)
        specs = plan_group_tree(legacy, account_names)
        key_to_group = await apply_group_tree(
            specs, group_repo=group_repo, workspace_id=workspace_id,
            owner_org_id=internal_org_id, actor_id=actor_id)
        summary["groups_created"] = len(key_to_group)
        summary["plates_grouped"] = await assign_plates_to_groups(
            legacy, key_to_group, matched, plate_repo=plate_repo, workspace_id=workspace_id)

        # Phase 4: loans
        loan_specs, unresolved = plan_loans(legacy, matched, account_email, user_map)
        created = 0
        for ls in loan_specs:
            if await apply_loan(ls, loan_repo=loan_repo, workspace_id=workspace_id,
                                internal_org_id=internal_org_id):
                created += 1
        summary["loans_created"] = created
        summary["unresolved_requesters"] = len(unresolved)

        if dry_run:
            await uow.rollback()
            logger.info("dry_run_rolled_back", **summary)
        else:
            await uow.commit()   # events discarded — no side-effect dispatch

    _write_csv(report_dir / "unmatched_plates.csv", unmatched,
               ["legacy_plate_id", "plate_barcode", "cdd_plate_id", "reason"])
    _write_csv(report_dir / "unresolved_requesters.csv", unresolved,
               ["transaction_id", "scientist_uin", "email", "reason"])
    logger.info("migration_done", dry_run=dry_run, **summary)
    return summary


async def _main() -> None:
    p = argparse.ArgumentParser(description="Migrate legacy plate-tracker into Cellar.")
    p.add_argument("--legacy-dsn", required=True, help="mysql://user:pass@host:port/db")
    p.add_argument("--workspace-id", type=uuid.UUID, required=True)
    p.add_argument("--internal-org-id", type=uuid.UUID, required=True)
    p.add_argument("--cdd-vault-id", required=True, help="cdd_plate_sync.cdd_vault_id for legacy plates")
    p.add_argument("--actor-id", type=uuid.UUID, required=True, help="Sentinel user id running the migration (group/CV created_by)")
    p.add_argument("--user-map", type=Path, default=None, help="CSV email,sentinel_user_id")
    p.add_argument("--report-dir", type=Path, default=Path("."))
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
            session_factory, legacy, workspace_id=args.workspace_id,
            internal_org_id=args.internal_org_id, cdd_vault_id=args.cdd_vault_id,
            user_map=user_map, actor_id=args.actor_id, report_dir=args.report_dir,
            dry_run=args.dry_run)
        print("MIGRATION SUMMARY:", summary)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: replace the module docstring with the cutover runbook**

Replace the top-of-file docstring with:
```python
"""Migrate the legacy plate-tracker (MySQL) into Cellar inventory plates.

Idempotent + re-runnable. Reads the legacy DB once (pymysql), then, in one
transaction: backfills NULL plate owners, matches legacy plates to Cellar
plates (cdd_plate_sync → barcode), sets ownership/type/status, builds the
PlateGroup tree, and recreates the OPEN checkouts as PlateLoans. Closed
history is NOT migrated (stays in the read-only legacy DB).

Usage (from backend/):
    uv run python scripts/migrate_legacy_plate_tracker.py \\
        --legacy-dsn mysql://user:pass@host:3306/sacnet_prod \\
        --workspace-id <ws-uuid> --internal-org-id <org-uuid> \\
        --cdd-vault-id <vault> --actor-id <sentinel-user-uuid> \\
        --user-map user_map.csv --report-dir ./reports [--dry-run]

Cutover runbook:
  1. Grant `cellar:approve_loan` is NOT needed (migrated loans bypass approval).
  2. Freeze the legacy plate-tracker (read-only announcement).
  3. Build user_map.csv: for each distinct OPEN-transaction requester email,
     look up the Sentinel user id (admin UI → Users) → `email,user_id` rows.
     (No service-key email→user lookup exists, so this step is manual.)
  4. Dry-run: add --dry-run; review MIGRATION SUMMARY + reports/*.csv.
     Resolve unmatched_plates.csv (barcode/cdd gaps) and
     unresolved_requesters.csv (add to user_map.csv) until acceptable.
  5. Real run (no --dry-run). Re-run is safe (idempotent) if interrupted.
  6. Spot-check in the UI: plate owners, the group tree, the ~15 open loans.
  7. Apply the `legacy:inactive` tag to depleted plates if summary
     inactive_needs_tag > 0 (manual, via the tags UI — see Task 4 note).
  8. Announce cutover.
"""
```

- [ ] **Step 5: run the full script test suite, verify pass**

Run: `cd backend && uv run pytest tests/unit/scripts/test_legacy_plate_tracker_core.py tests/integration/scripts/test_migrate_legacy_plate_tracker.py -q`
Expected: PASS (all tasks' tests green together).

- [ ] **Step 6: lint + commit**

Run: `cd backend && uv run ruff check scripts/migrate_legacy_plate_tracker.py && uv run ruff format scripts/migrate_legacy_plate_tracker.py`
```bash
git add backend/scripts/migrate_legacy_plate_tracker.py backend/tests/integration/scripts/test_migrate_legacy_plate_tracker.py
git commit -m "feat(scripts): migration orchestration, reports, dry-run + cutover runbook (S6 task 7)"
```

---

## Post-plan verification (not a task — do after all 7)

1. **Full targeted suite:** `cd backend && uv run pytest tests/unit/scripts tests/integration/scripts -q` → all green.
2. **Real dry-run against the legacy dump** (per the memory verify-rig recipe): restore `~/workspace/legacy/intranet/sacnet_prod.sql` into a local MySQL, point `--legacy-dsn` at it, target the dev workspace/org, `--dry-run`. Confirm the SUMMARY is sane (≈15 libraries→root groups, 78 set groups, matched-plate count, ≈15 loans) and both report CSVs look right.
3. **`docs/implementation-status.md`** — check off S6.
4. **Issue sidxz/cellar#71** — comment S6 shipped with the pushed range.
5. **Spec S6 sync note** — append to `docs/superpowers/specs/2026-08-10-inventory-plate-org-loans-spec.md` recording deviations (AVAIL→stored; plate_role has no MASTER_TWIN; TRANSACTION_PLATE is open-only current-state; pymysql dep; loans same-org + self-approved; `legacy:inactive` tagging deferred to a manual post-step).
6. **Memory** — update `project_plate_tracker_port.md`: S6 shipped; note the alembic-env root-cause fix (5 tables) landed first.

## Self-review notes (author)

- **Spec §12 coverage:** §12.1 plate matching → Task 3; §12.2 ownership → Task 4; §12.3 groups/CV/description → Task 5; §12.4 role/status maps → Task 2 (with the two documented corrections); §12.5 open checkouts → Task 6; §12.6 closed-history-excluded → enforced at read time (Task 1) + Global Constraints; §12.7 reports + runbook → Task 7. S2-deferred ownership backfill → Task 4.
- **Type consistency:** `matched: dict[int→uuid]`, `key_to_group: dict[str→uuid]`, `LoanItemStatus` targets, and repo/aggregate signatures are used identically across tasks.
- **Known simplification:** the `legacy:inactive` tag is counted, not written, inside the aggregate phase (kept out of the red-green cycle); Task 7 runbook step 7 + the report make it an explicit manual follow-up. Wiring `TagRepository.get_or_create` into Task 4 is a reasonable reviewer upgrade if they want it automated.
