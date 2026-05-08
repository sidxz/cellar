# Admin Hard Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give workspace admins audited hard-delete on every entity — RESTRICT-by-default with informative blocker payload (Tier 1, ~17 entities) plus force-cascade-with-preview for Protocol, Run, Molecule (Tier 2).

**Architecture:** Two-tier system on top of existing `AuditOperation`/`AuditEntry` append-only audit infra. Tier 1 introspects inbound FKs at attempt time and 409s with named blockers. Tier 2 reads per-module-registered `CascadeRule`s, builds a preview tree (counts + named heads + actions), and executes deletes/nulls in topological order — all inside one AuditOperation. Admin role gate (`require_admin`) on every endpoint; workspace scoping enforced at repository layer.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Pydantic v2 / Lagom DI / dry-python returns / Next.js 16 / React 19 / shadcn/ui / TanStack Query / Zod.

**Spec:** `docs/superpowers/specs/2026-05-08-admin-cascade-delete-design.md`

---

## File Structure

### New files (backend)

```
backend/src/chem_vault/
  domain/shared/cascade/
    __init__.py                  # Public exports
    rules.py                     # CascadeRule, CascadeAction enum
    registry.py                  # register_rules(), get_rules_for_parent()
    nodes.py                     # CascadeNode dataclass

  application/admin/
    __init__.py
    admin_delete_registry.py     # Tier-1 entity-type allow-list
    admin_hard_delete.py         # Tier-1 use case (RESTRICT)
    cascade_preview.py           # Tier-2 preview use case
    cascade_delete.py            # Tier-2 execute use case

  infrastructure/cascade/
    __init__.py
    inbound_refs.py              # SQLA-metadata-driven inbound FK utility
    cascade_runner.py            # Tier-2 preview + execute engine
    label_fields.py              # entity_type → (table, label_column) map

  interface/routes/
    admin_delete.py              # All admin delete endpoints

  domain/screening_assay/cascade.py        # Tier-2 rules (Protocol, Run subtrees)
  domain/chemical_registration/cascade.py  # Tier-2 rules (Molecule subtree)
  domain/research_organization/cascade.py  # Set-null rules (saved_searches, project_molecules etc.)
  domain/inventory/cascade.py              # Cascade rules under Molecule (batches, samples)
  domain/audit_compliance/cascade.py       # Warn rules (audit refs)
```

### Modified files (backend)

```
backend/src/chem_vault/
  domain/audit_compliance/enums.py         # +ADMIN_HARD_DELETE
  interface/dependencies.py                # +AdminHardDeleteDep, +CascadePreviewDep, +CascadeDeleteDep
  infrastructure/di/_audit.py              # Wire admin use cases
  interface/__init__.py (or main)          # Register admin_delete router
backend/tests/unit/cascade/                # Test directory (new)
backend/tests/integration/cascade/         # Test directory (new)
backend/tests/api/test_admin_delete.py     # API tests (new)
```

### New files (frontend)

```
frontend/src/shared/components/
  admin-delete-button.tsx        # Tier 1 button + reason dialog
  cascade-delete-dialog.tsx      # Tier 2 preview + typed-name confirm

frontend/src/shared/hooks/
  use-admin-delete.ts            # Tier 1 mutation
  use-cascade-preview.ts         # Tier 2 preview query
  use-cascade-delete.ts          # Tier 2 mutation
```

### Modified files (frontend)

Per-entity menu locations (Protocol detail, Run detail, Molecule detail, vocab list, etc.). Each gets one menu-item addition — listed as a single broad task rather than enumerated.

---

## Task 1: Add ADMIN_HARD_DELETE to OperationType enum

**Files:**
- Modify: `backend/src/chem_vault/domain/audit_compliance/enums.py`
- Test: `backend/tests/unit/audit_compliance/test_enums.py`

**No DB migration needed** — the column is `String(64)`, not a SQL enum. Verified at `alembic/versions/001_001_initial_schema.py:47`.

- [ ] **Step 1: Add the enum value**

```python
# enums.py — add to OperationType (append at end of class body before ActorType)
class OperationType(StrEnum):
    # ... existing values ...
    MARKUSH_DEFINITION = "markush_definition"
    ADMIN_HARD_DELETE = "admin_hard_delete"  # NEW
```

- [ ] **Step 2: Test the enum value resolves**

```python
# tests/unit/audit_compliance/test_enums.py
from chem_vault.domain.audit_compliance.enums import OperationType

def test_admin_hard_delete_value():
    assert OperationType.ADMIN_HARD_DELETE.value == "admin_hard_delete"
    assert OperationType("admin_hard_delete") == OperationType.ADMIN_HARD_DELETE
```

- [ ] **Step 3: Run test**

```bash
cd backend && uv run pytest tests/unit/audit_compliance/test_enums.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/chem_vault/domain/audit_compliance/enums.py backend/tests/unit/audit_compliance/test_enums.py
git commit -m "feat(audit): add ADMIN_HARD_DELETE operation type"
```

---

## Task 2: Inbound FK introspection utility

**Files:**
- Create: `backend/src/chem_vault/infrastructure/cascade/__init__.py` (empty)
- Create: `backend/src/chem_vault/infrastructure/cascade/inbound_refs.py`
- Create: `backend/src/chem_vault/infrastructure/cascade/label_fields.py`
- Create: `backend/tests/integration/cascade/__init__.py` (empty)
- Test: `backend/tests/integration/cascade/test_inbound_refs.py`

This walks `Base.metadata` to find inbound FKs *at the moment a delete is attempted*. No registry. No per-entity boilerplate.

- [ ] **Step 1: Create label-fields map**

```python
# infrastructure/cascade/label_fields.py
"""Maps SQL table name → (entity_type, label_column).

Used by the inbound FK utility to render human-readable 'samples' in
blocker payloads and cascade previews.
"""

# table_name -> (entity_type, label_column or None)
TABLE_LABELS: dict[str, tuple[str, str | None]] = {
    "protocols": ("protocol", "name"),
    "runs": ("run", "name"),
    "plates": ("plate", "barcode"),
    "wells": ("well", None),  # leaf, count-only
    "molecules": ("molecule", "registration_number"),
    "batches": ("batch", "lot_number"),
    "samples": ("sample", "barcode"),
    "shipments": ("shipment", "tracking_number"),
    "shipment_lines": ("shipment_line", None),
    "controlled_vocabularies": ("vocabulary", "name"),
    "registration_forms": ("registration_form", "name"),
    "protocol_forms": ("protocol_form", "name"),
    "salt_entries": ("salt_entry", "code"),
    "ontology_slot_definitions": ("ontology_slot", "name"),
    "data_sources": ("data_source", "name"),
    "custom_field_definitions": ("custom_field", "label"),
    "compound_flags": ("compound_flag", "name"),
    "saved_searches": ("saved_search", "name"),
    "collections": ("collection", "name"),
    "projects": ("project", "name"),
    "synthesis_routes": ("synthesis_route", "name"),
    "synthesis_requests": ("synthesis_request", "title"),
    "plate_templates": ("plate_template", "name"),
    "run_import_templates": ("run_import_template", "name"),
    "external_api_keys": ("api_key", "label"),
    "molecule_relationships": ("molecule_relationship", None),
    "readout_definitions": ("readout_definition", "name"),
    "readout_data": ("readout_data", None),
    "dose_response_curves": ("dose_response_curve", None),
    "hit_calls": ("hit_call", None),
    "hit_call_rules": ("hit_call_rule", "name"),
    "audit_operations": ("audit_operation", None),
    "audit_entries": ("audit_entry", None),
}


def label_for_table(table: str) -> tuple[str, str | None]:
    """Return (entity_type, label_column) for a table, defaulting to ('unknown', None)."""
    return TABLE_LABELS.get(table, (table, None))


def table_for_entity_type(entity_type: str) -> str | None:
    """Reverse lookup: entity_type → table name."""
    for tbl, (et, _label) in TABLE_LABELS.items():
        if et == entity_type:
            return tbl
    return None
```

- [ ] **Step 2: Create inbound FK utility**

```python
# infrastructure/cascade/inbound_refs.py
"""Inbound FK introspection — Tier-1 RESTRICT helper.

For a given (table, primary_key_value), enumerate every row in OTHER
tables that has a FK pointing at it. Used to compute the blocker
payload for the admin RESTRICT delete path.

Skips tables that don't carry FK relationships (audit_operations,
audit_entries — entity_id is a plain UUID, not a FK).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Table, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.infrastructure.persistence.sqlalchemy.base import Base
from chem_vault.infrastructure.cascade.label_fields import label_for_table


@dataclass(frozen=True)
class InboundReference:
    table: str
    fk_column: str
    entity_type: str
    count: int
    samples: list[dict]  # [{"id": "uuid", "label": "..."}]
    truncated: bool


async def find_inbound_references(
    session: AsyncSession,
    *,
    parent_table: str,
    parent_id: uuid.UUID,
    sample_limit: int = 5,
) -> list[InboundReference]:
    """Return all rows referencing (parent_table, parent_id) via FK.

    Walks Base.metadata to find every Table with a ForeignKey whose
    `target_fullname` is `<parent_table>.id`. For each match, executes
    a COUNT and a LIMIT-N sample query.
    """
    references: list[InboundReference] = []
    for table in Base.metadata.tables.values():
        for fk in _foreign_keys_pointing_to(table, parent_table):
            count = await _count_rows(session, table, fk.parent.name, parent_id)
            if count == 0:
                continue
            samples = await _fetch_samples(
                session, table, fk.parent.name, parent_id, sample_limit
            )
            entity_type, _label = label_for_table(table.name)
            references.append(
                InboundReference(
                    table=table.name,
                    fk_column=fk.parent.name,
                    entity_type=entity_type,
                    count=count,
                    samples=samples,
                    truncated=count > len(samples),
                )
            )
    return references


def _foreign_keys_pointing_to(table: Table, parent_table: str):
    """Yield ForeignKey objects on `table` that point at `<parent_table>.id`."""
    for col in table.columns:
        for fk in col.foreign_keys:
            target = fk.target_fullname  # e.g., "protocols.id"
            if target.split(".")[0] == parent_table:
                yield fk


async def _count_rows(
    session: AsyncSession,
    table: Table,
    fk_column: str,
    parent_id: uuid.UUID,
) -> int:
    stmt = select(func.count()).select_from(table).where(
        table.c[fk_column] == parent_id
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _fetch_samples(
    session: AsyncSession,
    table: Table,
    fk_column: str,
    parent_id: uuid.UUID,
    limit: int,
) -> list[dict]:
    """Fetch up to `limit` rows; render label using TABLE_LABELS."""
    _entity_type, label_column = label_for_table(table.name)
    cols = [table.c.id]
    if label_column and label_column in table.c:
        cols.append(table.c[label_column])
    stmt = select(*cols).where(table.c[fk_column] == parent_id).limit(limit)
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "id": str(row.id),
            "label": getattr(row, label_column, None) if label_column else None,
        }
        for row in rows
    ]
```

- [ ] **Step 3: Write integration test against a real test DB**

```python
# tests/integration/cascade/test_inbound_refs.py
"""Integration test: find inbound FK refs in a real DB session."""
import pytest
import uuid

from chem_vault.infrastructure.cascade.inbound_refs import find_inbound_references


@pytest.mark.asyncio
async def test_protocol_with_no_runs_has_no_blockers(db_session, protocol_factory):
    protocol = await protocol_factory()
    refs = await find_inbound_references(
        db_session, parent_table="protocols", parent_id=protocol.id
    )
    assert refs == []


@pytest.mark.asyncio
async def test_protocol_with_runs_returns_run_blocker(
    db_session, protocol_factory, run_factory
):
    protocol = await protocol_factory()
    run_a = await run_factory(protocol_id=protocol.id, name="R-A")
    run_b = await run_factory(protocol_id=protocol.id, name="R-B")

    refs = await find_inbound_references(
        db_session, parent_table="protocols", parent_id=protocol.id
    )
    run_ref = next(r for r in refs if r.table == "runs")
    assert run_ref.count == 2
    assert run_ref.entity_type == "run"
    labels = {s["label"] for s in run_ref.samples}
    assert {"R-A", "R-B"}.issubset(labels)
    assert run_ref.truncated is False


@pytest.mark.asyncio
async def test_truncated_when_more_than_sample_limit(
    db_session, protocol_factory, run_factory
):
    protocol = await protocol_factory()
    for i in range(7):
        await run_factory(protocol_id=protocol.id, name=f"R-{i}")
    refs = await find_inbound_references(
        db_session, parent_table="protocols", parent_id=protocol.id, sample_limit=5,
    )
    run_ref = next(r for r in refs if r.table == "runs")
    assert run_ref.count == 7
    assert len(run_ref.samples) == 5
    assert run_ref.truncated is True
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/integration/cascade/test_inbound_refs.py -v
```

Expected: 3 PASS. (If the test fixtures `protocol_factory` / `run_factory` don't exist, see existing `tests/integration/conftest.py` — most contexts already have factories; reuse them or add minimal ones.)

- [ ] **Step 5: Commit**

```bash
git add backend/src/chem_vault/infrastructure/cascade/ backend/tests/integration/cascade/
git commit -m "feat(cascade): inbound FK introspection utility for Tier-1 RESTRICT"
```

---

## Task 3: Tier-1 admin delete entity registry

**Files:**
- Create: `backend/src/chem_vault/application/admin/__init__.py` (empty)
- Create: `backend/src/chem_vault/application/admin/admin_delete_registry.py`
- Test: `backend/tests/unit/admin/test_admin_delete_registry.py`

The Tier-1 endpoint dispatches by `entity_type`. The registry maps each entity_type to: (a) its repository and (b) a `delete_by_id` callable. Each entry is a small Lagom-resolvable factory.

- [ ] **Step 1: Create registry module**

```python
# application/admin/admin_delete_registry.py
"""Registry of entity types that support admin hard-delete (Tier 1).

Each entry is a (table_name, RepoProtocol) pair plus a small adapter
that knows how to fetch+delete from that repo. The adapter signatures
are uniform: `find(workspace_id, id)` and `delete(workspace_id, id)`.

The registry is populated at module import time. New entities opt-in
by adding an entry here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


class _DeletableRepo(Protocol):
    async def find_by_id(self, workspace_id: uuid.UUID, id: uuid.UUID): ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...


@dataclass(frozen=True)
class AdminDeleteEntry:
    entity_type: str
    table: str
    label_field: str | None
    repo_resolver: Callable[..., _DeletableRepo]  # (container) -> repo


# entity_type -> AdminDeleteEntry. Populated by register_admin_delete().
_REGISTRY: dict[str, AdminDeleteEntry] = {}


def register_admin_delete(
    *,
    entity_type: str,
    table: str,
    label_field: str | None,
    repo_resolver: Callable[..., _DeletableRepo],
) -> None:
    """Register an entity type as admin-deletable (Tier 1)."""
    if entity_type in _REGISTRY:
        raise RuntimeError(f"{entity_type} already registered for admin-delete")
    _REGISTRY[entity_type] = AdminDeleteEntry(
        entity_type=entity_type,
        table=table,
        label_field=label_field,
        repo_resolver=repo_resolver,
    )


def get_entry(entity_type: str) -> AdminDeleteEntry | None:
    return _REGISTRY.get(entity_type)


def all_entity_types() -> list[str]:
    return sorted(_REGISTRY.keys())
```

- [ ] **Step 2: Test the registry**

```python
# tests/unit/admin/test_admin_delete_registry.py
import pytest
from chem_vault.application.admin.admin_delete_registry import (
    AdminDeleteEntry,
    register_admin_delete,
    get_entry,
    all_entity_types,
    _REGISTRY,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    snapshot = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


def _dummy_resolver():
    return object()


def test_register_and_lookup():
    register_admin_delete(
        entity_type="vocabulary", table="controlled_vocabularies",
        label_field="name", repo_resolver=_dummy_resolver,
    )
    e = get_entry("vocabulary")
    assert e is not None and e.table == "controlled_vocabularies"


def test_double_register_raises():
    register_admin_delete(
        entity_type="x", table="x", label_field=None, repo_resolver=_dummy_resolver
    )
    with pytest.raises(RuntimeError):
        register_admin_delete(
            entity_type="x", table="x", label_field=None, repo_resolver=_dummy_resolver
        )


def test_all_entity_types_sorted():
    register_admin_delete(entity_type="b", table="b", label_field=None, repo_resolver=_dummy_resolver)
    register_admin_delete(entity_type="a", table="a", label_field=None, repo_resolver=_dummy_resolver)
    assert all_entity_types() == ["a", "b"]
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/unit/admin/test_admin_delete_registry.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/chem_vault/application/admin/ backend/tests/unit/admin/
git commit -m "feat(admin): Tier-1 admin-delete entity registry"
```

---

## Task 4: AdminHardDelete generic use case (Tier 1)

**Files:**
- Create: `backend/src/chem_vault/application/admin/admin_hard_delete.py`
- Test: `backend/tests/unit/admin/test_admin_hard_delete.py`

This is the single use case used for every Tier-1 entity. Caller-provided `entity_type` is dispatched via the registry; on success, snapshots the row and writes one `AuditOperation` with one `AuditEntry`.

- [ ] **Step 1: Define result types**

```python
# application/admin/admin_hard_delete.py
"""Tier-1 admin hard-delete use case.

Behavior:
  1. require_admin(auth)
  2. Look up the entity in its repo (404 if missing).
  3. find_inbound_references(...) — RESTRICT if any.
  4. Snapshot the entity, hard-delete, and write one AuditOperation
     with operation_type=ADMIN_HARD_DELETE.

Returns:
  Success(None) on delete.
  Failure(BlockedByDependenciesError) with structured payload on blockers.
  Failure(NotFoundError) / Failure(AuthorizationError) on the obvious failures.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from returns.result import Failure, Result, Success

from chem_vault.application.admin.admin_delete_registry import get_entry
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.audit_compliance.enums import AuditAction, OperationType
from chem_vault.domain.audit_compliance.models import AuditEntry
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from chem_vault.infrastructure.cascade.inbound_refs import (
    InboundReference,
    find_inbound_references,
)


@dataclass(frozen=True, kw_only=True)
class AdminHardDeleteCommand(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    reason: str


@dataclass(frozen=True)
class BlockedByDependenciesError(DomainError):
    """Tier-1 RESTRICT: caller must clean up dependents first."""
    blockers: Sequence[InboundReference]

    @property
    def message(self) -> str:
        parts = [f"{r.count} {r.entity_type}(s)" for r in self.blockers]
        return "Cannot delete: " + ", ".join(parts) + " reference this entity."


class AdminHardDelete:
    def __init__(
        self,
        uow: UnitOfWork,
        audit: AuditRecordingService,
        container,  # Lagom Container — used to resolve per-entity repos
    ) -> None:
        self._uow = uow
        self._audit = audit
        self._container = container

    async def __call__(
        self,
        input: AdminHardDeleteCommand,
        auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        try:
            require_admin(auth)
        except AuthorizationError as e:
            return Failure(e)

        if not (input.reason or "").strip():
            return Failure(ValidationError("reason is required"))

        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        repo = entry.repo_resolver(self._container)

        async with self._uow:
            obj = await repo.find_by_id(input.workspace_id, input.entity_id)
            if obj is None:
                return Failure(NotFoundError(input.entity_type, str(input.entity_id)))

            blockers = await find_inbound_references(
                self._uow.session,  # see note below
                parent_table=entry.table,
                parent_id=input.entity_id,
            )
            if blockers:
                return Failure(BlockedByDependenciesError(blockers=tuple(blockers)))

            snapshot = _to_snapshot_dict(obj)
            await repo.delete(input.workspace_id, input.entity_id)
            await self._uow.commit()

        # Audit *after* commit — admin delete records actual outcome, not intent.
        assert auth is not None  # require_admin already enforced
        now = datetime.now(UTC)
        await self._audit.record(
            workspace_id=input.workspace_id,
            operation_type=OperationType.ADMIN_HARD_DELETE,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            user_id=auth.user_id,
            reason=input.reason,
            entries=[
                AuditEntry(
                    entity_type=input.entity_type,
                    entity_id=input.entity_id,
                    field_name="*",
                    action=AuditAction.DELETE,
                    old_value=json.dumps(snapshot, default=str, sort_keys=True),
                    new_value=None,
                    timestamp=now,
                )
            ],
        )

        return Success(None)


def _to_snapshot_dict(obj) -> dict:
    """Best-effort serialize a domain object or ORM row to a dict.

    Order of preference: __dataclass_fields__ → __dict__ → str().
    """
    if hasattr(obj, "__dataclass_fields__"):
        return {f: getattr(obj, f) for f in obj.__dataclass_fields__}
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": str(obj)}
```

> **Note on `self._uow.session`:** the existing UoW exposes the session for repos; check `application/shared/unit_of_work.py` and use whatever the established attribute name is (likely `.session`). If not directly exposed, refactor inbound_refs to take an explicit session-getter or thread the session through via UoW.

- [ ] **Step 2: Write unit tests with mocked repo + UoW**

```python
# tests/unit/admin/test_admin_hard_delete.py
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.admin.admin_delete_registry import (
    register_admin_delete, _REGISTRY,
)
from chem_vault.application.admin.admin_hard_delete import (
    AdminHardDelete, AdminHardDeleteCommand, BlockedByDependenciesError,
)
from chem_vault.domain.shared.errors import (
    AuthorizationError, NotFoundError, ValidationError,
)
from chem_vault.infrastructure.cascade.inbound_refs import InboundReference


@pytest.fixture(autouse=True)
def _registry_isolation():
    snapshot = dict(_REGISTRY); _REGISTRY.clear()
    yield
    _REGISTRY.clear(); _REGISTRY.update(snapshot)


def _auth(workspace_id, role="admin"):
    a = MagicMock()
    a.workspace_id = workspace_id
    a.user_id = uuid.uuid4()
    a.workspace_role = role
    a.is_admin = role == "admin"
    a.has_role = lambda r: True if role == "admin" else (r != "admin")
    return a


@pytest.mark.asyncio
async def test_non_admin_blocked():
    uc = AdminHardDelete(uow=MagicMock(), audit=MagicMock(), container=MagicMock())
    result = await uc(
        AdminHardDeleteCommand(
            workspace_id=uuid.uuid4(),
            entity_type="vocabulary", entity_id=uuid.uuid4(), reason="x",
        ),
        auth=_auth(uuid.uuid4(), role="editor"),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), AuthorizationError)


@pytest.mark.asyncio
async def test_empty_reason_rejected():
    register_admin_delete(
        entity_type="vocabulary", table="controlled_vocabularies",
        label_field="name", repo_resolver=lambda c: MagicMock(),
    )
    uc = AdminHardDelete(uow=MagicMock(), audit=MagicMock(), container=MagicMock())
    result = await uc(
        AdminHardDeleteCommand(
            workspace_id=uuid.uuid4(),
            entity_type="vocabulary", entity_id=uuid.uuid4(), reason="   ",
        ),
        auth=_auth(uuid.uuid4()),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)


@pytest.mark.asyncio
async def test_unknown_entity_type_404():
    uc = AdminHardDelete(uow=MagicMock(), audit=MagicMock(), container=MagicMock())
    result = await uc(
        AdminHardDeleteCommand(
            workspace_id=uuid.uuid4(),
            entity_type="not_a_real_thing", entity_id=uuid.uuid4(), reason="r",
        ),
        auth=_auth(uuid.uuid4()),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
```

> Add an integration test for the happy path + blocker path in Task 7.

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/unit/admin/test_admin_hard_delete.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/chem_vault/application/admin/admin_hard_delete.py backend/tests/unit/admin/test_admin_hard_delete.py
git commit -m "feat(admin): generic Tier-1 hard-delete use case"
```

---

## Task 5: Tier-1 admin delete route

**Files:**
- Create: `backend/src/chem_vault/interface/routes/admin_delete.py`
- Modify: `backend/src/chem_vault/interface/dependencies.py` (+AdminHardDeleteDep)
- Modify: `backend/src/chem_vault/infrastructure/di/_audit.py` (or `_workspace_config.py` — wire AdminHardDelete)
- Modify: wherever the FastAPI app registers routers (search for `app.include_router` or similar)

Pattern follows the existing `vocabularies.py` route file.

- [ ] **Step 1: Wire AdminHardDelete in DI**

Add to the appropriate `_<context>.py` registration module (e.g., create new `infrastructure/di/_admin.py`):

```python
# infrastructure/di/_admin.py
from lagom import Container

from chem_vault.application.admin.admin_hard_delete import AdminHardDelete
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.shared.unit_of_work import UnitOfWork


def register_admin(container: Container) -> None:
    container[AdminHardDelete] = lambda c: AdminHardDelete(
        uow=c[UnitOfWork],
        audit=c[AuditRecordingService],
        container=c,
    )
```

Then register it in `container.py`:

```python
# infrastructure/di/container.py — add import + call
from chem_vault.infrastructure.di._admin import register_admin
# ... in create_container() ...
    register_admin(container)
```

- [ ] **Step 2: Add the dep alias**

```python
# interface/dependencies.py — add near other Delete deps
from chem_vault.application.admin.admin_hard_delete import AdminHardDelete
# ...
AdminHardDeleteDep = Annotated[AdminHardDelete, Depends(_get_use_case(AdminHardDelete))]
```

- [ ] **Step 3: Create the route module**

```python
# interface/routes/admin_delete.py
"""Admin hard-delete endpoints — Tier 1 (RESTRICT) and Tier 2 (cascade).

Tier 1: any registered entity_type. RESTRICT-by-default — 409 if any
        inbound FK refs exist, with named blockers.
Tier 2: Protocol, Run, Molecule. Force-cascade with preview + typed-name confirm.
        (Tier 2 endpoints land in Task 16.)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from returns.result import Failure, Success

from chem_vault.application.admin.admin_hard_delete import (
    AdminHardDeleteCommand, BlockedByDependenciesError,
)
from chem_vault.domain.shared.errors import (
    AuthorizationError, NotFoundError, ValidationError,
)
from chem_vault.interface.dependencies import AuthDep, AdminHardDeleteDep

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AdminDeleteBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BlockerPayload(BaseModel):
    table: str
    entity_type: str
    fk_column: str
    count: int
    samples: list[dict]
    truncated: bool


class BlockedByDependenciesResponse(BaseModel):
    error: str = "delete_blocked_by_dependencies"
    blockers: list[BlockerPayload]


@router.delete(
    "/{entity_type}/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"model": BlockedByDependenciesResponse},
        403: {"description": "Caller is not a workspace admin"},
        404: {"description": "Entity not found or unknown entity_type"},
    },
)
async def admin_hard_delete(
    entity_type: str,
    entity_id: uuid.UUID,
    body: AdminDeleteBody,
    auth: AuthDep,
    use_case: AdminHardDeleteDep,
) -> None:
    cmd = AdminHardDeleteCommand(
        workspace_id=auth.workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=body.reason,
    )
    result = await use_case(cmd, auth=auth)

    if isinstance(result, Success):
        return None

    err = result.failure()
    if isinstance(err, BlockedByDependenciesError):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "delete_blocked_by_dependencies",
                "blockers": [
                    {
                        "table": r.table,
                        "entity_type": r.entity_type,
                        "fk_column": r.fk_column,
                        "count": r.count,
                        "samples": r.samples,
                        "truncated": r.truncated,
                    }
                    for r in err.blockers
                ],
            },
        )
    if isinstance(err, AuthorizationError):
        raise HTTPException(status_code=403, detail=str(err))
    if isinstance(err, NotFoundError):
        raise HTTPException(status_code=404, detail=str(err))
    if isinstance(err, ValidationError):
        raise HTTPException(status_code=422, detail=str(err))
    raise HTTPException(status_code=500, detail=str(err))
```

- [ ] **Step 4: Register the router**

Find the FastAPI `include_router` calls (likely `interface/__init__.py` or `interface/main.py`) and add:

```python
from chem_vault.interface.routes import admin_delete
app.include_router(admin_delete.router)
```

- [ ] **Step 5: Smoke test the route is reachable**

Run the API tests for any existing endpoint to confirm nothing broke:

```bash
cd backend && uv run pytest tests/api/ -k "vocabulary" -v
```

Expected: existing tests still pass. (No admin route tests yet — those land in Task 7.)

- [ ] **Step 6: Commit**

```bash
git add backend/src/chem_vault/interface/routes/admin_delete.py backend/src/chem_vault/interface/dependencies.py backend/src/chem_vault/infrastructure/di/_admin.py backend/src/chem_vault/infrastructure/di/container.py
git commit -m "feat(admin): Tier-1 admin hard-delete route + DI wiring"
```

---

## Task 6: Wire Vocabulary into Tier 1 (pilot)

**Files:**
- Modify: `backend/src/chem_vault/infrastructure/di/_workspace_config.py`

Vocabulary already has a repo (`SQLAlchemyControlledVocabularyRepository`) with `find_by_id_in_workspace()` and `delete()`. We need a tiny adapter so its method names match the registry's `_DeletableRepo` protocol (`find_by_id` not `find_by_id_in_workspace`).

- [ ] **Step 1: Inline-adapt at registration time**

In `infrastructure/di/_workspace_config.py`, at the bottom:

```python
# At the bottom, after existing registrations:
from chem_vault.application.admin.admin_delete_registry import register_admin_delete
from chem_vault.domain.workspace_config.repository import ControlledVocabularyRepository


class _VocabularyAdapter:
    """Adapts ControlledVocabularyRepository to the admin-delete protocol."""
    def __init__(self, repo): self._r = repo
    async def find_by_id(self, workspace_id, id):
        return await self._r.find_by_id_in_workspace(workspace_id, id)
    async def delete(self, workspace_id, id):
        await self._r.delete(workspace_id, id)


def _resolve_vocab(container):
    return _VocabularyAdapter(container[ControlledVocabularyRepository])


register_admin_delete(
    entity_type="vocabulary",
    table="controlled_vocabularies",
    label_field="name",
    repo_resolver=_resolve_vocab,
)
```

- [ ] **Step 2: Verify the registry sees it**

Add a quick smoke test:

```python
# tests/unit/admin/test_registry_population.py
def test_vocabulary_registered_after_di_init():
    from chem_vault.infrastructure.di.container import create_container
    create_container()  # triggers all register_*() calls
    from chem_vault.application.admin.admin_delete_registry import all_entity_types
    assert "vocabulary" in all_entity_types()
```

- [ ] **Step 3: Run**

```bash
cd backend && uv run pytest tests/unit/admin/test_registry_population.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/chem_vault/infrastructure/di/_workspace_config.py backend/tests/unit/admin/test_registry_population.py
git commit -m "feat(admin): wire vocabulary into Tier-1 admin delete"
```

---

## Task 7: Tier-1 end-to-end API tests (Vocabulary)

**Files:**
- Create: `backend/tests/api/test_admin_delete.py`

- [ ] **Step 1: Test happy path, blocker path, auth, missing entity**

```python
# tests/api/test_admin_delete.py
"""End-to-end API tests for admin hard-delete (Tier 1)."""
import uuid
import pytest

# Reuses the project's existing API test harness — see other tests/api/*.py
# for the `client` and `admin_auth` / `editor_auth` fixtures.


@pytest.mark.asyncio
async def test_admin_can_delete_unreferenced_vocabulary(
    client, admin_auth, vocabulary_factory,
):
    vocab = await vocabulary_factory(name="Solvents")
    resp = await client.delete(
        f"/api/v1/admin/vocabulary/{vocab.id}",
        json={"reason": "obsolete"},
        headers=admin_auth,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_editor_cannot_admin_delete(
    client, editor_auth, vocabulary_factory,
):
    vocab = await vocabulary_factory(name="Solvents")
    resp = await client.delete(
        f"/api/v1/admin/vocabulary/{vocab.id}",
        json={"reason": "x"},
        headers=editor_auth,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missing_reason_422(client, admin_auth, vocabulary_factory):
    vocab = await vocabulary_factory(name="X")
    resp = await client.delete(
        f"/api/v1/admin/vocabulary/{vocab.id}",
        json={"reason": ""},
        headers=admin_auth,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_entity_type_404(client, admin_auth):
    resp = await client.delete(
        f"/api/v1/admin/wat/{uuid.uuid4()}",
        json={"reason": "x"},
        headers=admin_auth,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_operation_recorded(
    client, admin_auth, vocabulary_factory, audit_repo,
):
    vocab = await vocabulary_factory(name="Solvents")
    resp = await client.delete(
        f"/api/v1/admin/vocabulary/{vocab.id}",
        json={"reason": "obsolete"},
        headers=admin_auth,
    )
    assert resp.status_code == 204

    ops = await audit_repo.list_for_entity("vocabulary", vocab.id)
    assert any(op.operation_type.value == "admin_hard_delete" for op in ops)
    op = next(op for op in ops if op.operation_type.value == "admin_hard_delete")
    assert op.reason == "obsolete"
    assert any(e.action.value == "delete" for e in op.entries)
```

(For the blocker test, we need a vocabulary that's referenced by a custom field. If a fixture doesn't exist yet, write one inline that creates a custom field def referencing the vocab name; **but note** the existing schema may not have a FK from custom_field_definitions to controlled_vocabularies — vocabulary references are by name in JSON, not FK. In that case the blocker test belongs to a different entity. Skip the blocker test here and add it in Task 8 against an entity with a real FK, e.g., `salt_entries` referenced by `molecules.salt_id`.)

- [ ] **Step 2: Run**

```bash
cd backend && uv run pytest tests/api/test_admin_delete.py -v
```

Expected: 5 PASS (or fewer if blocker test skipped per note).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_admin_delete.py
git commit -m "test(admin): Tier-1 admin delete end-to-end (vocabulary)"
```

---

## Task 8: Tier-1 broad rollout — register remaining entities

**Files:**
- Modify: `backend/src/chem_vault/infrastructure/di/_workspace_config.py` (add: registration_form, protocol_form, salt_entry, ontology_slot, custom_field, data_source, external_api_key)
- Modify: `backend/src/chem_vault/infrastructure/di/_chemical_registration.py` (add: compound_flag, molecule_relationship, synthesis_route)
- Modify: `backend/src/chem_vault/infrastructure/di/_screening.py` (add: protocol, run, plate_template, run_import_template)
- Modify: `backend/src/chem_vault/infrastructure/di/_inventory.py` (add: batch, sample, shipment, synthesis_request)
- Modify: `backend/src/chem_vault/infrastructure/di/_research_organization.py` (add: project, collection, saved_search)

For each entity, follow the same adapter pattern as Vocabulary in Task 6.

- [ ] **Step 1: Define a small reusable adapter helper**

```python
# application/admin/_adapter.py
"""Adapter from arbitrary repos to the _DeletableRepo protocol."""

class RepoAdapter:
    """Wraps a repo with custom method names into find_by_id/delete shape.

    Usage:
        adapter = RepoAdapter(repo, find='find_by_id_in_workspace', delete='delete')
    """
    def __init__(self, repo, *, find: str, delete: str = "delete"):
        self._repo, self._find, self._delete = repo, find, delete

    async def find_by_id(self, workspace_id, id):
        return await getattr(self._repo, self._find)(workspace_id, id)

    async def delete(self, workspace_id, id):
        await getattr(self._repo, self._delete)(workspace_id, id)
```

- [ ] **Step 2: Register every Tier-1 entity in the appropriate `_<context>.py`**

Per entity, add a block like:

```python
from chem_vault.application.admin.admin_delete_registry import register_admin_delete
from chem_vault.application.admin._adapter import RepoAdapter
from chem_vault.domain.workspace_config.repository import RegistrationFormRepository

def _resolve_reg_form(container):
    return RepoAdapter(container[RegistrationFormRepository], find="find_by_id_in_workspace")

register_admin_delete(
    entity_type="registration_form",
    table="registration_forms",
    label_field="name",
    repo_resolver=_resolve_reg_form,
)
```

For each entity, **verify the actual repo method name** by reading the repo file. Some use `find_by_id`, some `find_by_id_in_workspace`, some `get`. Pass the right name to RepoAdapter.

Entities to register (table → entity_type, plus the canonical context file):

| Context file | Entity types |
|---|---|
| `_workspace_config.py` | registration_form, protocol_form, salt_entry, ontology_slot, custom_field, data_source, api_key |
| `_chemical_registration.py` | compound_flag, molecule_relationship, synthesis_route, molecule (Tier-1 fallback even though Tier-2 is preferred — gives admins a path when no cascade exists) |
| `_screening.py` | protocol (Tier-1 fallback), run (Tier-1 fallback), plate_template, run_import_template |
| `_inventory.py` | batch, sample, shipment, synthesis_request |
| `_research_organization.py` | project, collection, saved_search |

> **Important:** Protocol/Run/Molecule are Tier-1-registered too. The Tier-1 path will RESTRICT-block them in 99% of cases (they have children), forcing the admin to use the Tier-2 force-cascade path. Tier-1 only succeeds for childless ones. This is intentional: the entity_type allow-list stays uniform.

- [ ] **Step 3: Update test_registry_population.py**

```python
def test_all_expected_entities_registered():
    from chem_vault.infrastructure.di.container import create_container
    create_container()
    from chem_vault.application.admin.admin_delete_registry import all_entity_types

    expected = {
        "vocabulary", "registration_form", "protocol_form", "salt_entry",
        "ontology_slot", "custom_field", "data_source", "api_key",
        "compound_flag", "molecule_relationship", "synthesis_route", "molecule",
        "protocol", "run", "plate_template", "run_import_template",
        "batch", "sample", "shipment", "synthesis_request",
        "project", "collection", "saved_search",
    }
    missing = expected - set(all_entity_types())
    assert not missing, f"Missing admin-delete registrations: {missing}"
```

- [ ] **Step 4: Run all admin tests**

```bash
cd backend && uv run pytest tests/unit/admin tests/integration/cascade tests/api/test_admin_delete.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/chem_vault/application/admin/_adapter.py backend/src/chem_vault/infrastructure/di/ backend/tests/unit/admin/test_registry_population.py
git commit -m "feat(admin): wire Tier-1 admin delete for all 23 entities"
```

---

## Task 9: Cascade primitives — CascadeRule, registry, CascadeNode

**Files:**
- Create: `backend/src/chem_vault/domain/shared/cascade/__init__.py`
- Create: `backend/src/chem_vault/domain/shared/cascade/rules.py`
- Create: `backend/src/chem_vault/domain/shared/cascade/registry.py`
- Create: `backend/src/chem_vault/domain/shared/cascade/nodes.py`
- Test: `backend/tests/unit/cascade/test_registry.py`

- [ ] **Step 1: rules.py — CascadeRule dataclass**

```python
# domain/shared/cascade/rules.py
"""CascadeRule — a single inbound-FK edge in the cascade graph."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CascadeAction(StrEnum):
    CASCADE = "cascade"
    SET_NULL = "set_null"
    BLOCK = "block"
    WARN = "warn"


@dataclass(frozen=True)
class CascadeRule:
    """Declares: 'rows in `child_table.fk_column` referencing `parent_table.id`
    should be handled with `action` when the parent is deleted.'

    Owned by the module that adds the FK. A new module that adds an FK to an
    existing entity declares its own rule here — no edits to the existing
    module's cascade.py.
    """
    child_table: str
    fk_column: str
    parent_table: str
    action: CascadeAction
    label_field: str | None = None  # column on child_table used for named heads
    display_label: str = ""         # group label in preview, e.g., "Runs"
    recurse_into_entity: str | None = None  # parent_table for recursive walking
```

- [ ] **Step 2: registry.py**

```python
# domain/shared/cascade/registry.py
"""Process-global registry of CascadeRules.

Modules call `register_rules(*rules)` at import time. Lookup by parent_table.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from chem_vault.domain.shared.cascade.rules import CascadeRule


_BY_PARENT: dict[str, list[CascadeRule]] = defaultdict(list)


def register_rules(*rules: CascadeRule) -> None:
    for r in rules:
        _BY_PARENT[r.parent_table].append(r)


def get_rules_for_parent(parent_table: str) -> list[CascadeRule]:
    return list(_BY_PARENT.get(parent_table, []))


def all_rules() -> list[CascadeRule]:
    return [r for rules in _BY_PARENT.values() for r in rules]


def _clear_for_test() -> None:
    """Test-only: reset the registry."""
    _BY_PARENT.clear()
```

- [ ] **Step 3: nodes.py — preview tree shape**

```python
# domain/shared/cascade/nodes.py
"""CascadeNode — preview tree node returned by Tier-2 preview."""
from __future__ import annotations

from dataclasses import dataclass, field

from chem_vault.domain.shared.cascade.rules import CascadeAction


@dataclass
class CascadeNode:
    entity_type: str
    table: str
    display_label: str
    count: int
    samples: list[dict]   # [{"id": str, "label": str | None}]
    truncated: bool
    action: CascadeAction
    children: list["CascadeNode"] = field(default_factory=list)
```

- [ ] **Step 4: __init__.py**

```python
# domain/shared/cascade/__init__.py
from chem_vault.domain.shared.cascade.rules import CascadeAction, CascadeRule
from chem_vault.domain.shared.cascade.registry import (
    register_rules, get_rules_for_parent, all_rules,
)
from chem_vault.domain.shared.cascade.nodes import CascadeNode

__all__ = [
    "CascadeAction", "CascadeRule", "CascadeNode",
    "register_rules", "get_rules_for_parent", "all_rules",
]
```

- [ ] **Step 5: Test the registry**

```python
# tests/unit/cascade/test_registry.py
import pytest
from chem_vault.domain.shared.cascade import (
    CascadeAction, CascadeRule, register_rules, get_rules_for_parent,
)
from chem_vault.domain.shared.cascade.registry import _clear_for_test


@pytest.fixture(autouse=True)
def _reset():
    _clear_for_test()


def test_register_and_lookup_by_parent():
    r = CascadeRule(
        child_table="runs", fk_column="protocol_id", parent_table="protocols",
        action=CascadeAction.CASCADE, label_field="name", display_label="Runs",
        recurse_into_entity="run",
    )
    register_rules(r)
    assert get_rules_for_parent("protocols") == [r]
    assert get_rules_for_parent("nonexistent") == []


def test_multiple_rules_same_parent():
    a = CascadeRule(child_table="a", fk_column="p_id", parent_table="p",
                    action=CascadeAction.CASCADE, display_label="A")
    b = CascadeRule(child_table="b", fk_column="p_id", parent_table="p",
                    action=CascadeAction.SET_NULL, display_label="B")
    register_rules(a, b)
    assert set(get_rules_for_parent("p")) == {a, b}
```

- [ ] **Step 6: Run + commit**

```bash
cd backend && uv run pytest tests/unit/cascade/test_registry.py -v
git add backend/src/chem_vault/domain/shared/cascade/ backend/tests/unit/cascade/
git commit -m "feat(cascade): CascadeRule, registry, CascadeNode primitives"
```

---

## Task 10: Cascade rules — screening_assay (Protocol & Run subtrees)

**Files:**
- Create: `backend/src/chem_vault/domain/screening_assay/cascade.py`
- Modify: `backend/src/chem_vault/infrastructure/di/_screening.py` (add `import chem_vault.domain.screening_assay.cascade  # noqa` to ensure registration runs)

Read the actual schema first: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/screening_assay/models.py`. Translate every inbound FK into a CascadeRule.

- [ ] **Step 1: Write the cascade declarations**

```python
# domain/screening_assay/cascade.py
"""Cascade rules for screening_assay tables.

Declares what happens to children of Protocol, Run, Plate, etc., when those
parents are deleted via Tier-2 admin force-cascade.
"""
from chem_vault.domain.shared.cascade import (
    CascadeAction as A, CascadeRule, register_rules,
)


register_rules(
    # --- Protocol children ---
    CascadeRule(
        child_table="readout_definitions", fk_column="protocol_id",
        parent_table="protocols", action=A.CASCADE,
        label_field="name", display_label="Readout definitions",
    ),
    CascadeRule(
        child_table="plate_templates", fk_column="protocol_id",
        parent_table="protocols", action=A.CASCADE,
        label_field="name", display_label="Plate templates",
    ),
    CascadeRule(
        child_table="hit_call_rules", fk_column="protocol_id",
        parent_table="protocols", action=A.CASCADE,
        label_field="name", display_label="Hit-call rules",
    ),
    CascadeRule(
        child_table="runs", fk_column="protocol_id",
        parent_table="protocols", action=A.CASCADE,
        label_field="name", display_label="Runs",
        recurse_into_entity="run",
    ),
    CascadeRule(
        child_table="protocol_forms", fk_column="protocol_id",
        parent_table="protocols", action=A.SET_NULL,
        label_field="name", display_label="Protocol forms (link cleared)",
    ),

    # --- Run children ---
    CascadeRule(
        child_table="plates", fk_column="run_id",
        parent_table="runs", action=A.CASCADE,
        label_field="barcode", display_label="Plates",
        recurse_into_entity="plate",
    ),
    CascadeRule(
        child_table="dose_response_curves", fk_column="run_id",
        parent_table="runs", action=A.CASCADE,
        label_field=None, display_label="Dose-response curves",
    ),
    CascadeRule(
        child_table="hit_calls", fk_column="run_id",
        parent_table="runs", action=A.CASCADE,
        label_field=None, display_label="Hit calls",
    ),
    CascadeRule(
        child_table="run_imports", fk_column="run_id",
        parent_table="runs", action=A.CASCADE,
        label_field=None, display_label="Run import records",
    ),

    # --- Plate children ---
    CascadeRule(
        child_table="wells", fk_column="plate_id",
        parent_table="plates", action=A.CASCADE,
        label_field=None, display_label="Wells",
        recurse_into_entity="well",
    ),

    # --- Well children ---
    CascadeRule(
        child_table="readout_data", fk_column="well_id",
        parent_table="wells", action=A.CASCADE,
        label_field=None, display_label="Readout values",
    ),
)
```

> **Verify against schema before committing.** If the schema has FKs not listed here (e.g., a `dose_response_points.curve_id`), add them. The FK coverage test (Task 14) will catch any miss anyway.

- [ ] **Step 2: Wire registration on import**

Append to `backend/src/chem_vault/infrastructure/di/_screening.py`:

```python
# Force cascade rules to register at DI bootstrap.
import chem_vault.domain.screening_assay.cascade  # noqa: F401
```

- [ ] **Step 3: Test the registrations**

```python
# tests/unit/cascade/test_screening_rules.py
def test_protocol_runs_rule_exists():
    import chem_vault.domain.screening_assay.cascade  # noqa
    from chem_vault.domain.shared.cascade import get_rules_for_parent
    rules = get_rules_for_parent("protocols")
    assert any(
        r.child_table == "runs" and r.action.value == "cascade"
        for r in rules
    )


def test_well_to_readout_data_recurses():
    import chem_vault.domain.screening_assay.cascade  # noqa
    from chem_vault.domain.shared.cascade import get_rules_for_parent
    rules = get_rules_for_parent("wells")
    rd = next(r for r in rules if r.child_table == "readout_data")
    assert rd.action.value == "cascade"
```

- [ ] **Step 4: Run + commit**

```bash
cd backend && uv run pytest tests/unit/cascade/test_screening_rules.py -v
git add backend/src/chem_vault/domain/screening_assay/cascade.py backend/src/chem_vault/infrastructure/di/_screening.py backend/tests/unit/cascade/test_screening_rules.py
git commit -m "feat(cascade): Tier-2 cascade rules for Protocol/Run/Plate subtrees"
```

---

## Task 11: Cascade rules — chemical_registration & inventory & research_organization

**Files:**
- Create: `backend/src/chem_vault/domain/chemical_registration/cascade.py`
- Create: `backend/src/chem_vault/domain/inventory/cascade.py`
- Create: `backend/src/chem_vault/domain/research_organization/cascade.py`
- Create: `backend/src/chem_vault/domain/audit_compliance/cascade.py`
- Modify: corresponding `infrastructure/di/_*.py` to import the cascade modules

Same pattern as Task 10. Each declares its module-owned outbound rules.

- [ ] **Step 1: chemical_registration/cascade.py — Molecule children**

```python
# domain/chemical_registration/cascade.py
from chem_vault.domain.shared.cascade import CascadeAction as A, CascadeRule, register_rules


register_rules(
    CascadeRule(child_table="molecule_identifiers", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field="value", display_label="Identifiers"),
    CascadeRule(child_table="molecule_properties", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field=None, display_label="Properties"),
    CascadeRule(child_table="molecule_relationships", fk_column="from_molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field=None, display_label="Outbound relationships"),
    CascadeRule(child_table="molecule_relationships", fk_column="to_molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field=None, display_label="Inbound relationships"),
    CascadeRule(child_table="synthesis_routes", fk_column="target_molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field="name", display_label="Synthesis routes",
                recurse_into_entity="synthesis_route"),
    CascadeRule(child_table="synthesis_route_steps", fk_column="route_id",
                parent_table="synthesis_routes", action=A.CASCADE,
                label_field=None, display_label="Synthesis steps"),
    CascadeRule(child_table="compound_flags", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field="name", display_label="Compound flags"),
    CascadeRule(child_table="disclosure_requests", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field=None, display_label="Disclosure requests"),
    CascadeRule(child_table="bulk_registration_items", fk_column="molecule_id",
                parent_table="molecules", action=A.SET_NULL,
                label_field=None, display_label="Bulk-registration item refs (cleared)"),
)
```

- [ ] **Step 2: inventory/cascade.py — Batches/Samples**

```python
# domain/inventory/cascade.py
from chem_vault.domain.shared.cascade import CascadeAction as A, CascadeRule, register_rules


register_rules(
    CascadeRule(child_table="batches", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field="lot_number", display_label="Batches",
                recurse_into_entity="batch"),
    CascadeRule(child_table="samples", fk_column="batch_id",
                parent_table="batches", action=A.CASCADE,
                label_field="barcode", display_label="Samples",
                recurse_into_entity="sample"),
    CascadeRule(child_table="shipment_lines", fk_column="sample_id",
                parent_table="samples", action=A.CASCADE,
                label_field=None, display_label="Shipment lines"),
    CascadeRule(child_table="sample_requests", fk_column="sample_id",
                parent_table="samples", action=A.SET_NULL,
                label_field=None, display_label="Sample requests (link cleared)"),
)
```

- [ ] **Step 3: research_organization/cascade.py**

```python
# domain/research_organization/cascade.py
from chem_vault.domain.shared.cascade import CascadeAction as A, CascadeRule, register_rules


register_rules(
    CascadeRule(child_table="project_molecules", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field=None, display_label="Project memberships"),
    CascadeRule(child_table="collection_molecules", fk_column="molecule_id",
                parent_table="molecules", action=A.CASCADE,
                label_field=None, display_label="Collection memberships"),
    CascadeRule(child_table="saved_searches", fk_column="protocol_id",
                parent_table="protocols", action=A.SET_NULL,
                label_field="name", display_label="Saved searches (scope cleared)"),
)
```

- [ ] **Step 4: audit_compliance/cascade.py — warn rules for orphaned audit refs**

Audit entries don't have a real FK on entity_id, but if your schema has any FKs from audit tables (it shouldn't, by design), declare them as `WARN` here.

```python
# domain/audit_compliance/cascade.py
"""Audit context has no FKs to other tables (entity_id is a plain UUID).

This file exists to document that decision. If the schema ever adds an FK
from audit_entries to a domain table, add a WARN rule here so the cascade
preview surfaces the orphan-by-design behavior to the admin.
"""
from chem_vault.domain.shared.cascade import register_rules  # noqa: F401
# No rules registered.
```

- [ ] **Step 5: Wire registrations**

In each `infrastructure/di/_<context>.py`, add the import alongside the existing pattern:

```python
import chem_vault.domain.chemical_registration.cascade  # noqa: F401
# ...
import chem_vault.domain.inventory.cascade  # noqa: F401
# ...
import chem_vault.domain.research_organization.cascade  # noqa: F401
# ...
import chem_vault.domain.audit_compliance.cascade  # noqa: F401
```

- [ ] **Step 6: Test rule presence**

```python
# tests/unit/cascade/test_cross_context_rules.py
def test_batches_cascade_under_molecule():
    from chem_vault.infrastructure.di.container import create_container
    create_container()
    from chem_vault.domain.shared.cascade import get_rules_for_parent
    rules = get_rules_for_parent("molecules")
    assert any(r.child_table == "batches" and r.action.value == "cascade" for r in rules)


def test_saved_searches_set_null_under_protocol():
    from chem_vault.infrastructure.di.container import create_container
    create_container()
    from chem_vault.domain.shared.cascade import get_rules_for_parent
    rules = get_rules_for_parent("protocols")
    assert any(r.child_table == "saved_searches" and r.action.value == "set_null" for r in rules)
```

- [ ] **Step 7: Run + commit**

```bash
cd backend && uv run pytest tests/unit/cascade/ -v
git add backend/src/chem_vault/domain/chemical_registration/cascade.py backend/src/chem_vault/domain/inventory/cascade.py backend/src/chem_vault/domain/research_organization/cascade.py backend/src/chem_vault/domain/audit_compliance/cascade.py backend/src/chem_vault/infrastructure/di/_chemical_registration.py backend/src/chem_vault/infrastructure/di/_inventory.py backend/src/chem_vault/infrastructure/di/_research_organization.py backend/tests/unit/cascade/test_cross_context_rules.py
git commit -m "feat(cascade): Tier-2 rules for chemical_registration, inventory, research_org"
```

---

## Task 12: CascadeRunner — preview engine

**Files:**
- Create: `backend/src/chem_vault/infrastructure/cascade/cascade_runner.py`
- Test: `backend/tests/integration/cascade/test_cascade_runner_preview.py`

- [ ] **Step 1: Implement preview**

```python
# infrastructure/cascade/cascade_runner.py (preview half)
"""CascadeRunner — Tier-2 preview + execute engine.

Walks the per-module cascade registry to build a CascadeNode tree.
"""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import Table, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.shared.cascade import (
    CascadeAction, CascadeNode, get_rules_for_parent,
)
from chem_vault.infrastructure.cascade.label_fields import label_for_table
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


SAMPLE_LIMIT = 5


class CascadeRunner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def preview(
        self, *, parent_table: str, parent_id: uuid.UUID
    ) -> CascadeNode:
        """Build the full cascade tree rooted at (parent_table, parent_id)."""
        return await self._build_node_for_root(parent_table, parent_id)

    async def _build_node_for_root(self, table: str, id_: uuid.UUID) -> CascadeNode:
        entity_type, _label_col = label_for_table(table)
        sa_table = Base.metadata.tables[table]
        # Root row metadata
        root_label = await self._fetch_label(sa_table, id_)
        root = CascadeNode(
            entity_type=entity_type,
            table=table,
            display_label=entity_type,
            count=1,
            samples=[{"id": str(id_), "label": root_label}],
            truncated=False,
            action=CascadeAction.CASCADE,
            children=[],
        )
        await self._populate_children(root, parent_id=id_)
        return root

    async def _populate_children(
        self, node: CascadeNode, *, parent_id: uuid.UUID
    ) -> None:
        for rule in get_rules_for_parent(node.table):
            child_table = Base.metadata.tables[rule.child_table]
            count = await self._count(child_table, rule.fk_column, parent_id)
            if count == 0 and rule.action != CascadeAction.WARN:
                continue
            samples = await self._fetch_samples(
                child_table, rule.fk_column, parent_id, rule.label_field, SAMPLE_LIMIT,
            )
            child_node = CascadeNode(
                entity_type=label_for_table(rule.child_table)[0],
                table=rule.child_table,
                display_label=rule.display_label or rule.child_table,
                count=count,
                samples=samples,
                truncated=count > len(samples),
                action=rule.action,
                children=[],
            )
            node.children.append(child_node)

            if rule.action == CascadeAction.CASCADE and rule.recurse_into_entity:
                # Recurse: each matched child row becomes a recursion seed.
                for s in samples:
                    sub = CascadeNode(
                        entity_type=child_node.entity_type,
                        table=rule.child_table,
                        display_label=s.get("label") or child_node.entity_type,
                        count=1,
                        samples=[s],
                        truncated=False,
                        action=CascadeAction.CASCADE,
                        children=[],
                    )
                    await self._populate_children(sub, parent_id=uuid.UUID(s["id"]))
                    child_node.children.append(sub)

    # --- helpers ---
    async def _count(self, table: Table, fk_column: str, parent_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(table).where(table.c[fk_column] == parent_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def _fetch_samples(
        self, table: Table, fk_column: str, parent_id: uuid.UUID,
        label_column: str | None, limit: int,
    ) -> list[dict]:
        cols = [table.c.id]
        if label_column and label_column in table.c:
            cols.append(table.c[label_column])
        stmt = select(*cols).where(table.c[fk_column] == parent_id).limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "id": str(row.id),
                "label": getattr(row, label_column, None) if label_column else None,
            }
            for row in rows
        ]

    async def _fetch_label(self, table: Table, id_: uuid.UUID) -> str | None:
        _et, label_col = label_for_table(table.name)
        if not label_col or label_col not in table.c:
            return None
        stmt = select(table.c[label_col]).where(table.c.id == id_)
        return (await self._session.execute(stmt)).scalar_one_or_none()
```

> **Performance note:** the recursion-by-sample loop above bounds depth blowup at `SAMPLE_LIMIT^depth`, which is ≤625 nodes for depth-4 trees. For real previews the user only needs *named heads at each level*, not a full enumeration of every row. The execute path (Task 13) does NOT use this sample-based recursion — it walks the full row set per level.

- [ ] **Step 2: Integration test**

```python
# tests/integration/cascade/test_cascade_runner_preview.py
import pytest
from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner
from chem_vault.domain.shared.cascade import CascadeAction


@pytest.mark.asyncio
async def test_preview_protocol_with_one_run_one_plate(
    db_session, protocol_factory, run_factory, plate_factory,
):
    p = await protocol_factory(name="P1")
    r = await run_factory(protocol_id=p.id, name="R1")
    pl = await plate_factory(run_id=r.id, barcode="B1")

    runner = CascadeRunner(db_session)
    tree = await runner.preview(parent_table="protocols", parent_id=p.id)

    assert tree.entity_type == "protocol"
    assert tree.count == 1
    runs_node = next(c for c in tree.children if c.table == "runs")
    assert runs_node.count == 1
    assert runs_node.action == CascadeAction.CASCADE
    plates_subtree = runs_node.children[0]
    plates_node = next(c for c in plates_subtree.children if c.table == "plates")
    assert plates_node.count == 1
```

- [ ] **Step 3: Run + commit**

```bash
cd backend && uv run pytest tests/integration/cascade/test_cascade_runner_preview.py -v
git add backend/src/chem_vault/infrastructure/cascade/cascade_runner.py backend/tests/integration/cascade/test_cascade_runner_preview.py
git commit -m "feat(cascade): Tier-2 preview engine"
```

---

## Task 13: CascadeRunner — execute engine

**Files:**
- Modify: `backend/src/chem_vault/infrastructure/cascade/cascade_runner.py`

The execute path: collects all rows that will be deleted/nulled across the cascade, snapshots each, then performs deletes in topological order (children before parents). Returns the list of `AuditEntry` records to attach to the AuditOperation.

- [ ] **Step 1: Add execute() method**

```python
# Append to cascade_runner.py
import json
from datetime import UTC, datetime

from sqlalchemy import update, delete
from chem_vault.domain.audit_compliance.enums import AuditAction
from chem_vault.domain.audit_compliance.models import AuditEntry


class CascadeExecutionError(Exception):
    """Raised when a BLOCK rule matched at execute time (race after preview)."""


# ... inside class CascadeRunner:

async def execute(
    self, *, parent_table: str, parent_id: uuid.UUID,
) -> list[AuditEntry]:
    """Execute the cascade. Returns audit entries to attach to the
    AuditOperation by the caller. Raises CascadeExecutionError if a BLOCK
    rule matches at execute time (rare race).

    Strategy:
      1. Topologically collect all rows that will be deleted, in
         dependency order (deepest descendants first).
      2. Snapshot each into an AuditEntry.
      3. Apply: SET NULL for set_null rules, DELETE for cascade rules.
      4. Finally DELETE the root row.
    """
    entries: list[AuditEntry] = []
    null_ops: list[tuple[str, str, list[uuid.UUID]]] = []  # (table, fk_col, ids)
    delete_ops: list[tuple[str, list[uuid.UUID]]] = []     # (table, ids)

    await self._collect(
        parent_table, [parent_id], entries=entries,
        null_ops=null_ops, delete_ops=delete_ops,
    )

    # Apply set-null first (so downstream cascades see NULLs already), then deletes.
    for table_name, fk_col, ids in null_ops:
        sa_table = Base.metadata.tables[table_name]
        await self._session.execute(
            update(sa_table).where(sa_table.c.id.in_(ids)).values(**{fk_col: None})
        )

    # Delete in reverse topological order: collected list has deepest last.
    for table_name, ids in reversed(delete_ops):
        sa_table = Base.metadata.tables[table_name]
        await self._session.execute(
            delete(sa_table).where(sa_table.c.id.in_(ids))
        )

    # Delete the root row last.
    root_table = Base.metadata.tables[parent_table]
    await self._session.execute(
        delete(root_table).where(root_table.c.id == parent_id)
    )
    return entries

async def _collect(
    self, table: str, parent_ids: list[uuid.UUID],
    *, entries: list[AuditEntry],
    null_ops: list[tuple[str, str, list[uuid.UUID]]],
    delete_ops: list[tuple[str, list[uuid.UUID]]],
) -> None:
    """Walk the cascade graph from a set of parent rows, gather plans."""
    sa_table = Base.metadata.tables[table]
    # Snapshot the parents themselves
    rows = (await self._session.execute(
        sa_table.select().where(sa_table.c.id.in_(parent_ids))
    )).mappings().all()
    et, _ = label_for_table(table)
    now = datetime.now(UTC)
    for row in rows:
        entries.append(AuditEntry(
            entity_type=et,
            entity_id=row["id"],
            field_name="*",
            action=AuditAction.DELETE,
            old_value=json.dumps(dict(row), default=str, sort_keys=True),
            new_value=None,
            timestamp=now,
        ))
    # Now walk children
    for rule in get_rules_for_parent(table):
        child_sa = Base.metadata.tables[rule.child_table]
        if rule.action == CascadeAction.BLOCK:
            count = (await self._session.execute(
                select(func.count()).select_from(child_sa).where(
                    child_sa.c[rule.fk_column].in_(parent_ids)
                )
            )).scalar_one()
            if count > 0:
                raise CascadeExecutionError(
                    f"Blocking rule fired: {rule.child_table}.{rule.fk_column}"
                )
            continue
        if rule.action == CascadeAction.WARN:
            continue
        # Find child IDs
        child_ids = [
            row.id for row in (await self._session.execute(
                select(child_sa.c.id).where(
                    child_sa.c[rule.fk_column].in_(parent_ids)
                )
            )).all()
        ]
        if not child_ids:
            continue
        if rule.action == CascadeAction.SET_NULL:
            null_ops.append((rule.child_table, rule.fk_column, child_ids))
            continue
        # CASCADE — recurse if rule says so, otherwise just snapshot+delete
        if rule.recurse_into_entity:
            await self._collect(
                rule.child_table, child_ids,
                entries=entries, null_ops=null_ops, delete_ops=delete_ops,
            )
        else:
            # Snapshot leaf rows
            leaf_rows = (await self._session.execute(
                child_sa.select().where(child_sa.c.id.in_(child_ids))
            )).mappings().all()
            child_et, _ = label_for_table(rule.child_table)
            now2 = datetime.now(UTC)
            for row in leaf_rows:
                entries.append(AuditEntry(
                    entity_type=child_et,
                    entity_id=row["id"],
                    field_name="*",
                    action=AuditAction.DELETE,
                    old_value=json.dumps(dict(row), default=str, sort_keys=True),
                    new_value=None,
                    timestamp=now2,
                ))
        delete_ops.append((rule.child_table, child_ids))
```

- [ ] **Step 2: Integration test the execute path**

```python
# tests/integration/cascade/test_cascade_runner_execute.py
import pytest
from sqlalchemy import select, func

from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


@pytest.mark.asyncio
async def test_execute_deletes_protocol_and_descendants(
    db_session, protocol_factory, run_factory, plate_factory, well_factory,
):
    p = await protocol_factory(name="P1")
    r = await run_factory(protocol_id=p.id, name="R1")
    pl = await plate_factory(run_id=r.id, barcode="B1")
    w = await well_factory(plate_id=pl.id)

    runner = CascadeRunner(db_session)
    entries = await runner.execute(parent_table="protocols", parent_id=p.id)
    await db_session.commit()

    # All rows gone
    for table_name in ("protocols", "runs", "plates", "wells"):
        t = Base.metadata.tables[table_name]
        count = (await db_session.execute(select(func.count()).select_from(t))).scalar_one()
        assert count == 0, f"{table_name} should be empty"

    # Audit entries cover every deleted row (root + 1 run + 1 plate + 1 well)
    assert len(entries) == 4
    assert {e.entity_type for e in entries} == {"protocol", "run", "plate", "well"}


@pytest.mark.asyncio
async def test_execute_sets_null_on_saved_searches(
    db_session, protocol_factory, saved_search_factory,
):
    p = await protocol_factory(name="P1")
    s = await saved_search_factory(scope_protocol_id=p.id, name="My picks")

    runner = CascadeRunner(db_session)
    await runner.execute(parent_table="protocols", parent_id=p.id)
    await db_session.commit()

    # Saved search still exists, but its protocol_id is NULL
    refreshed = await db_session.get(type(s), s.id)
    assert refreshed is not None
    assert refreshed.scope_protocol_id is None
```

- [ ] **Step 3: Run + commit**

```bash
cd backend && uv run pytest tests/integration/cascade/test_cascade_runner_execute.py -v
git add backend/src/chem_vault/infrastructure/cascade/cascade_runner.py backend/tests/integration/cascade/test_cascade_runner_execute.py
git commit -m "feat(cascade): Tier-2 execute engine with set-null + cascade + block"
```

---

## Task 14: Tier-2 endpoints — preview + cascade-delete

**Files:**
- Modify: `backend/src/chem_vault/interface/routes/admin_delete.py`
- Create: `backend/src/chem_vault/application/admin/cascade_preview.py`
- Create: `backend/src/chem_vault/application/admin/cascade_delete.py`
- Modify: `backend/src/chem_vault/interface/dependencies.py`
- Modify: `backend/src/chem_vault/infrastructure/di/_admin.py`

- [ ] **Step 1: cascade_preview.py use case**

```python
# application/admin/cascade_preview.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.admin.admin_delete_registry import get_entry
from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.cascade import CascadeNode
from chem_vault.domain.shared.errors import (
    AuthorizationError, DomainError, NotFoundError,
)
from chem_vault.infrastructure.cascade.cascade_runner import CascadeRunner

# Tier-2 is gated to these entity types only.
TIER2_ENTITY_TYPES = frozenset({"protocol", "run", "molecule"})


@dataclass(frozen=True, kw_only=True)
class CascadePreviewQuery(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID


class CascadePreview:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self, input: CascadePreviewQuery, auth: AuthContext | None = None,
    ) -> Result[CascadeNode, DomainError]:
        try:
            require_admin(auth)
        except AuthorizationError as e:
            return Failure(e)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            runner = CascadeRunner(self._uow.session)
            node = await runner.preview(
                parent_table=entry.table, parent_id=input.entity_id,
            )
            return Success(node)
```

- [ ] **Step 2: cascade_delete.py use case**

```python
# application/admin/cascade_delete.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from chem_vault.application.admin.admin_delete_registry import get_entry
from chem_vault.application.admin.cascade_preview import TIER2_ENTITY_TYPES
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.auth import AuthContext, require_admin
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.audit_compliance.enums import OperationType
from chem_vault.domain.shared.errors import (
    AuthorizationError, DomainError, NotFoundError, ValidationError,
)
from chem_vault.infrastructure.cascade.cascade_runner import (
    CascadeExecutionError, CascadeRunner,
)
from chem_vault.infrastructure.cascade.label_fields import label_for_table


@dataclass(frozen=True, kw_only=True)
class CascadeDeleteCommand(Command):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    typed_name: str
    reason: str


class CascadeDelete:
    def __init__(self, uow: UnitOfWork, audit: AuditRecordingService) -> None:
        self._uow = uow
        self._audit = audit

    async def __call__(
        self, input: CascadeDeleteCommand, auth: AuthContext | None = None,
    ) -> Result[None, DomainError]:
        try:
            require_admin(auth)
        except AuthorizationError as e:
            return Failure(e)
        if input.entity_type not in TIER2_ENTITY_TYPES:
            return Failure(NotFoundError("entity_type", input.entity_type))
        if not input.reason.strip():
            return Failure(ValidationError("reason is required"))

        entry = get_entry(input.entity_type)
        if entry is None:
            return Failure(NotFoundError("entity_type", input.entity_type))

        async with self._uow:
            # Verify typed_name matches the row's label_field exactly.
            actual_label = await _fetch_label(
                self._uow.session, entry.table, input.entity_id,
            )
            if actual_label is None:
                return Failure(NotFoundError(input.entity_type, str(input.entity_id)))
            if input.typed_name != actual_label:
                return Failure(ValidationError(
                    f"typed_name does not match {input.entity_type} name"
                ))

            runner = CascadeRunner(self._uow.session)
            try:
                entries = await runner.execute(
                    parent_table=entry.table, parent_id=input.entity_id,
                )
            except CascadeExecutionError as e:
                return Failure(ValidationError(str(e)))
            await self._uow.commit()

        assert auth is not None
        await self._audit.record(
            workspace_id=input.workspace_id,
            operation_type=OperationType.ADMIN_HARD_DELETE,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            user_id=auth.user_id,
            reason=input.reason,
            entries=entries,
        )
        return Success(None)


async def _fetch_label(session, table_name: str, id_: uuid.UUID):
    from sqlalchemy import select
    from chem_vault.infrastructure.persistence.sqlalchemy.base import Base
    _et, label_col = label_for_table(table_name)
    if not label_col:
        return None
    t = Base.metadata.tables[table_name]
    return (await session.execute(
        select(t.c[label_col]).where(t.c.id == id_)
    )).scalar_one_or_none()
```

- [ ] **Step 3: Wire DI**

```python
# infrastructure/di/_admin.py — extend register_admin
from chem_vault.application.admin.cascade_preview import CascadePreview
from chem_vault.application.admin.cascade_delete import CascadeDelete

def register_admin(container: Container) -> None:
    container[AdminHardDelete] = lambda c: AdminHardDelete(...)  # existing
    container[CascadePreview] = lambda c: CascadePreview(uow=c[UnitOfWork])
    container[CascadeDelete] = lambda c: CascadeDelete(
        uow=c[UnitOfWork], audit=c[AuditRecordingService],
    )
```

```python
# interface/dependencies.py
CascadePreviewDep = Annotated[CascadePreview, Depends(_get_use_case(CascadePreview))]
CascadeDeleteDep  = Annotated[CascadeDelete,  Depends(_get_use_case(CascadeDelete))]
```

- [ ] **Step 4: Routes**

```python
# Append to interface/routes/admin_delete.py

from chem_vault.application.admin.cascade_preview import CascadePreviewQuery
from chem_vault.application.admin.cascade_delete import CascadeDeleteCommand
from chem_vault.domain.shared.cascade import CascadeNode

class CascadeNodeResponse(BaseModel):
    entity_type: str
    table: str
    display_label: str
    count: int
    samples: list[dict]
    truncated: bool
    action: str
    children: list["CascadeNodeResponse"] = []

    @classmethod
    def from_domain(cls, n: CascadeNode) -> "CascadeNodeResponse":
        return cls(
            entity_type=n.entity_type, table=n.table,
            display_label=n.display_label, count=n.count,
            samples=n.samples, truncated=n.truncated, action=n.action.value,
            children=[cls.from_domain(c) for c in n.children],
        )

CascadeNodeResponse.model_rebuild()


@router.post(
    "/{entity_type}/{entity_id}/cascade-preview",
    response_model=CascadeNodeResponse,
)
async def cascade_preview(
    entity_type: str, entity_id: uuid.UUID,
    auth: AuthDep, use_case: CascadePreviewDep,
) -> CascadeNodeResponse:
    res = await use_case(
        CascadePreviewQuery(
            workspace_id=auth.workspace_id,
            entity_type=entity_type, entity_id=entity_id,
        ),
        auth=auth,
    )
    if isinstance(res, Success):
        return CascadeNodeResponse.from_domain(res.unwrap())
    err = res.failure()
    if isinstance(err, AuthorizationError):
        raise HTTPException(403, str(err))
    if isinstance(err, NotFoundError):
        raise HTTPException(404, str(err))
    raise HTTPException(500, str(err))


class CascadeDeleteBody(BaseModel):
    typed_name: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


@router.delete(
    "/{entity_type}/{entity_id}/cascade",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cascade_delete(
    entity_type: str, entity_id: uuid.UUID,
    body: CascadeDeleteBody,
    auth: AuthDep, use_case: CascadeDeleteDep,
) -> None:
    res = await use_case(
        CascadeDeleteCommand(
            workspace_id=auth.workspace_id,
            entity_type=entity_type, entity_id=entity_id,
            typed_name=body.typed_name, reason=body.reason,
        ),
        auth=auth,
    )
    if isinstance(res, Success):
        return None
    err = res.failure()
    if isinstance(err, AuthorizationError):
        raise HTTPException(403, str(err))
    if isinstance(err, NotFoundError):
        raise HTTPException(404, str(err))
    if isinstance(err, ValidationError):
        raise HTTPException(422, str(err))
    raise HTTPException(500, str(err))
```

- [ ] **Step 5: Add API tests**

```python
# tests/api/test_admin_delete.py — append

@pytest.mark.asyncio
async def test_cascade_preview_protocol(
    client, admin_auth, protocol_factory, run_factory, plate_factory,
):
    p = await protocol_factory(name="MyProto")
    r = await run_factory(protocol_id=p.id, name="R1")
    await plate_factory(run_id=r.id, barcode="B1")

    resp = await client.post(
        f"/api/v1/admin/protocol/{p.id}/cascade-preview",
        headers=admin_auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_type"] == "protocol"
    assert body["count"] == 1
    runs = next(c for c in body["children"] if c["table"] == "runs")
    assert runs["count"] == 1


@pytest.mark.asyncio
async def test_cascade_delete_requires_typed_name(
    client, admin_auth, protocol_factory,
):
    p = await protocol_factory(name="MyProto")
    resp = await client.delete(
        f"/api/v1/admin/protocol/{p.id}/cascade",
        json={"typed_name": "WrongName", "reason": "test"},
        headers=admin_auth,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cascade_delete_succeeds(
    client, admin_auth, protocol_factory, run_factory,
):
    p = await protocol_factory(name="MyProto")
    await run_factory(protocol_id=p.id, name="R1")
    resp = await client.delete(
        f"/api/v1/admin/protocol/{p.id}/cascade",
        json={"typed_name": "MyProto", "reason": "obsolete"},
        headers=admin_auth,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_tier2_only_for_pilot_entities(client, admin_auth, vocabulary_factory):
    v = await vocabulary_factory(name="X")
    resp = await client.post(
        f"/api/v1/admin/vocabulary/{v.id}/cascade-preview",
        headers=admin_auth,
    )
    assert resp.status_code == 404  # entity_type not in TIER2 set
```

- [ ] **Step 6: Run + commit**

```bash
cd backend && uv run pytest tests/api/test_admin_delete.py tests/unit/admin tests/integration/cascade -v
git add backend/src/chem_vault/application/admin/cascade_preview.py backend/src/chem_vault/application/admin/cascade_delete.py backend/src/chem_vault/interface/routes/admin_delete.py backend/src/chem_vault/interface/dependencies.py backend/src/chem_vault/infrastructure/di/_admin.py backend/tests/api/test_admin_delete.py
git commit -m "feat(admin): Tier-2 cascade preview + force delete endpoints"
```

---

## Task 15: FK coverage CI test

**Files:**
- Create: `backend/tests/unit/cascade/test_fk_coverage.py`

The safety net: every FK in `Base.metadata` must be either (a) supported by Tier 1 (the inbound-FK introspection will surface it as a blocker), or (b) covered by a Tier-2 cascade rule. An explicit `IGNORED_FKS` allow-list handles legitimate exceptions.

- [ ] **Step 1: Write the coverage test**

```python
# tests/unit/cascade/test_fk_coverage.py
"""CI-enforced FK coverage check.

Asserts that every inbound FK referencing a Tier-1 or Tier-2 admin entity
is either picked up by Tier-1 introspection (which is automatic — it walks
all FKs) or has a registered CascadeRule (Tier-2). Listed in IGNORED_FKS
are FKs that legitimately should not be cascaded or surfaced (e.g., audit
self-references, system-managed link tables that are out of scope).

This test enforces: when a developer adds a new FK to the schema, they
either (a) accept the default Tier-1 RESTRICT behavior (no action needed),
or (b) declare a Tier-2 cascade rule, or (c) explicitly add it to IGNORED_FKS
with a justifying comment.
"""
from chem_vault.infrastructure.di.container import create_container  # noqa
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base
from chem_vault.domain.shared.cascade import all_rules


# (child_table, fk_column, parent_table) — explicitly ignored.
IGNORED_FKS: set[tuple[str, str, str]] = {
    # Audit refs by design are not real FKs (entity_id is plain UUID).
    # Listed here only if migrations ever introduce a real FK from audit_*.
}


def _collect_all_fks() -> set[tuple[str, str, str]]:
    """Yield (child_table, fk_column, parent_table) for every FK in metadata."""
    fks: set[tuple[str, str, str]] = set()
    for table in Base.metadata.tables.values():
        for col in table.columns:
            for fk in col.foreign_keys:
                parent = fk.target_fullname.split(".")[0]
                fks.add((table.name, col.name, parent))
    return fks


def _collect_tier2_rule_keys() -> set[tuple[str, str, str]]:
    return {
        (r.child_table, r.fk_column, r.parent_table) for r in all_rules()
    }


# Tier-1 admin-deletable parent tables — RESTRICT will surface their inbound FKs.
TIER1_PARENT_TABLES = {
    "controlled_vocabularies", "registration_forms", "protocol_forms",
    "salt_entries", "ontology_slot_definitions", "custom_field_definitions",
    "data_sources", "external_api_keys", "compound_flags",
    "molecule_relationships", "synthesis_routes", "molecules",
    "protocols", "runs", "plate_templates", "run_import_templates",
    "batches", "samples", "shipments", "synthesis_requests",
    "projects", "collections", "saved_searches",
}


def test_every_fk_is_categorized():
    create_container()  # forces all cascade.py imports
    all_fks = _collect_all_fks()
    tier2_keys = _collect_tier2_rule_keys()

    uncovered: list[tuple[str, str, str]] = []
    for fk in all_fks:
        child_table, fk_col, parent_table = fk
        if fk in IGNORED_FKS:
            continue
        if parent_table in TIER1_PARENT_TABLES:
            continue  # Tier-1 RESTRICT will handle it
        if fk in tier2_keys:
            continue  # Tier-2 rule covers it
        uncovered.append(fk)

    assert not uncovered, (
        "FKs not covered by Tier-1 RESTRICT or Tier-2 cascade rules:\n"
        + "\n".join(f"  {ct}.{c} -> {pt}" for ct, c, pt in uncovered)
        + "\n\nResolution: either register a CascadeRule, add the parent table "
          "to TIER1_PARENT_TABLES, or add to IGNORED_FKS with a justifying comment."
    )
```

- [ ] **Step 2: Run + iterate**

```bash
cd backend && uv run pytest tests/unit/cascade/test_fk_coverage.py -v
```

If it fails, the message lists missing FKs. For each: either add a Tier-2 rule (Task 11/12 patterns), expand TIER1_PARENT_TABLES, or add to IGNORED_FKS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/cascade/test_fk_coverage.py
git commit -m "test(cascade): CI FK-coverage gate"
```

---

## Task 16: Generate frontend SDK

**Files:**
- Run orval (existing config at `frontend/orval.config.ts`)
- Result: `frontend/src/shared/api/generated/` files updated

- [ ] **Step 1: Regenerate**

```bash
cd frontend && pnpm orval
```

- [ ] **Step 2: Verify the new admin endpoints are in the generated client**

```bash
grep -r "adminHardDelete\|cascadePreview\|cascadeDelete" frontend/src/shared/api/generated/ | head
```

Expected: matches found.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/api/generated/
git commit -m "chore(api): regenerate SDK with admin delete endpoints"
```

---

## Task 17: Frontend Tier-1 admin delete button + dialog

**Files:**
- Create: `frontend/src/shared/components/admin-delete-button.tsx`
- Create: `frontend/src/shared/hooks/use-admin-delete.ts`

- [ ] **Step 1: Hook**

```tsx
// frontend/src/shared/hooks/use-admin-delete.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { adminHardDelete } from "@/shared/api/generated/admin/admin";
import { toast } from "sonner";

export interface AdminDeleteOptions {
  entityType: string;
  entityId: string;
  reason: string;
}

export interface AdminDeleteBlocker {
  table: string;
  entity_type: string;
  fk_column: string;
  count: number;
  samples: { id: string; label: string | null }[];
  truncated: boolean;
}

export function useAdminDelete(opts?: { onSuccess?: () => void }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ entityType, entityId, reason }: AdminDeleteOptions) => {
      await adminHardDelete(entityType, entityId, { reason });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Deleted");
      opts?.onSuccess?.();
    },
    onError: (err: any) => {
      // Bubble up — UI extracts blocker payload from err.response?.data.detail.
      const detail = err?.response?.data?.detail;
      if (detail?.error === "delete_blocked_by_dependencies") return;
      toast.error(err?.message ?? "Failed to delete");
    },
  });
}
```

- [ ] **Step 2: Component**

```tsx
// frontend/src/shared/components/admin-delete-button.tsx
"use client";

import { useState } from "react";
import { Button, buttonVariants } from "@/shared/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog";
import { Textarea } from "@/shared/components/ui/textarea";
import { useAdminDelete, type AdminDeleteBlocker } from "@/shared/hooks/use-admin-delete";
import { Trash2 } from "lucide-react";

export interface AdminDeleteButtonProps {
  entityType: string;
  entityId: string;
  entityLabel: string;
  onDeleted?: () => void;
  triggerLabel?: string;
}

export function AdminDeleteButton({
  entityType, entityId, entityLabel, onDeleted, triggerLabel = "Admin: Delete",
}: AdminDeleteButtonProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [blockers, setBlockers] = useState<AdminDeleteBlocker[] | null>(null);
  const m = useAdminDelete({ onSuccess: () => { setOpen(false); onDeleted?.(); } });

  async function onConfirm() {
    setBlockers(null);
    try {
      await m.mutateAsync({ entityType, entityId, reason });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (detail?.error === "delete_blocked_by_dependencies") {
        setBlockers(detail.blockers);
      }
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <Trash2 className="mr-1 h-4 w-4" /> {triggerLabel}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {entityType}: {entityLabel}</AlertDialogTitle>
          <AlertDialogDescription>
            This is a hard delete. Audit-logged.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {blockers ? (
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-destructive">
              Cannot delete — dependencies exist:
            </p>
            <ul className="list-disc pl-5">
              {blockers.map((b) => (
                <li key={b.table}>
                  {b.count} {b.entity_type}
                  {b.count !== 1 ? "s" : ""}
                  {b.samples.length > 0 && (
                    <span className="text-muted-foreground">
                      : {b.samples.map((s) => s.label ?? s.id).join(", ")}
                      {b.truncated ? ", …" : ""}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs pt-2">
              Resolve these references first, then retry.
            </p>
          </div>
        ) : (
          <Textarea
            placeholder="Reason for deletion (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={m.isPending}>Close</AlertDialogCancel>
          {!blockers && (
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={(e) => { e.preventDefault(); onConfirm(); }}
              disabled={m.isPending || !reason.trim()}
            >
              {m.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/components/admin-delete-button.tsx frontend/src/shared/hooks/use-admin-delete.ts
git commit -m "feat(admin-ui): Tier-1 admin delete button with blocker rendering"
```

---

## Task 18: Frontend Tier-2 cascade dialog

**Files:**
- Create: `frontend/src/shared/components/cascade-delete-dialog.tsx`
- Create: `frontend/src/shared/hooks/use-cascade-preview.ts`
- Create: `frontend/src/shared/hooks/use-cascade-delete.ts`

- [ ] **Step 1: Hooks**

```tsx
// frontend/src/shared/hooks/use-cascade-preview.ts
"use client";
import { useQuery } from "@tanstack/react-query";
import { cascadePreview } from "@/shared/api/generated/admin/admin";

export function useCascadePreview(entityType: string, entityId: string, enabled = true) {
  return useQuery({
    queryKey: ["cascade-preview", entityType, entityId],
    queryFn: () => cascadePreview(entityType, entityId),
    enabled,
  });
}
```

```tsx
// frontend/src/shared/hooks/use-cascade-delete.ts
"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cascadeDelete } from "@/shared/api/generated/admin/admin";
import { toast } from "sonner";

export interface CascadeDeleteOptions {
  entityType: string; entityId: string;
  typedName: string; reason: string;
}

export function useCascadeDelete(opts?: { onSuccess?: () => void }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ entityType, entityId, typedName, reason }: CascadeDeleteOptions) => {
      await cascadeDelete(entityType, entityId, { typed_name: typedName, reason });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Deleted");
      opts?.onSuccess?.();
    },
    onError: (e: any) => toast.error(e?.message ?? "Failed"),
  });
}
```

- [ ] **Step 2: Dialog component**

```tsx
// frontend/src/shared/components/cascade-delete-dialog.tsx
"use client";

import { useState } from "react";
import { Button, buttonVariants } from "@/shared/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog";
import { Input } from "@/shared/components/ui/input";
import { Textarea } from "@/shared/components/ui/textarea";
import { useCascadePreview } from "@/shared/hooks/use-cascade-preview";
import { useCascadeDelete } from "@/shared/hooks/use-cascade-delete";
import { AlertTriangle } from "lucide-react";

export interface CascadeDeleteDialogProps {
  entityType: string;        // "protocol" | "run" | "molecule"
  entityId: string;
  entityLabel: string;
  onDeleted?: () => void;
}

interface PreviewNode {
  entity_type: string; table: string; display_label: string;
  count: number; samples: { id: string; label: string | null }[];
  truncated: boolean; action: string; children: PreviewNode[];
}

function NodeView({ node, depth = 0 }: { node: PreviewNode; depth?: number }) {
  const indent = depth * 16;
  const actionColor =
    node.action === "block" ? "text-destructive font-semibold"
    : node.action === "set_null" ? "text-amber-600"
    : node.action === "warn" ? "text-muted-foreground"
    : "";
  return (
    <div style={{ paddingLeft: indent }} className="text-sm">
      <span className={actionColor}>
        [{node.action}] {node.display_label}: {node.count}
      </span>
      {node.samples.length > 0 && node.samples[0]?.label && (
        <span className="text-muted-foreground ml-2 text-xs">
          ({node.samples.map(s => s.label).filter(Boolean).join(", ")}
          {node.truncated ? ", …" : ""})
        </span>
      )}
      {node.children.map((c, i) => (
        <NodeView key={`${c.table}-${i}`} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export function CascadeDeleteDialog({
  entityType, entityId, entityLabel, onDeleted,
}: CascadeDeleteDialogProps) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const preview = useCascadePreview(entityType, entityId, open);
  const m = useCascadeDelete({
    onSuccess: () => { setOpen(false); onDeleted?.(); },
  });

  const canSubmit = typed === entityLabel && reason.trim().length > 0;

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <AlertTriangle className="mr-1 h-4 w-4" />
          Force delete (cascade)
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>Force delete {entityType}: {entityLabel}</AlertDialogTitle>
          <AlertDialogDescription>
            Hard delete. All dependent rows will be removed or unlinked as shown.
            This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {preview.isLoading && <p>Computing impact…</p>}
        {preview.data && <NodeView node={preview.data as any} />}

        <div className="space-y-2 pt-2">
          <label className="text-sm font-medium">
            Type <code className="bg-muted px-1 rounded">{entityLabel}</code> to confirm:
          </label>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} />
          <Textarea
            placeholder="Reason for deletion (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={buttonVariants({ variant: "destructive" })}
            disabled={!canSubmit || m.isPending}
            onClick={(e) => {
              e.preventDefault();
              m.mutate({ entityType, entityId, typedName: typed, reason });
            }}
          >
            {m.isPending ? "Deleting…" : "Force delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/components/cascade-delete-dialog.tsx frontend/src/shared/hooks/use-cascade-preview.ts frontend/src/shared/hooks/use-cascade-delete.ts
git commit -m "feat(admin-ui): Tier-2 cascade preview + force-delete dialog"
```

---

## Task 19: Wire admin delete buttons into entity views

**Files:**
- Modify: per-entity detail and list pages — add `<AdminDeleteButton>` (Tier 1) for entities like Vocabulary, Form, Template, etc., and `<CascadeDeleteDialog>` (Tier 2) on Protocol/Run/Molecule detail pages.

Each insertion is a 4-line addition guarded by `auth.is_admin`. Examples:

- [ ] **Step 1: Wire Vocabulary list (example)**

```tsx
// frontend/src/features/workspace-config/vocabulary/components/vocabulary-row-actions.tsx
import { useAuth } from "@/shared/hooks/use-auth";
import { AdminDeleteButton } from "@/shared/components/admin-delete-button";
// ...
const { isAdmin } = useAuth();
{isAdmin && (
  <AdminDeleteButton
    entityType="vocabulary"
    entityId={vocab.id}
    entityLabel={vocab.name}
    onDeleted={() => qc.invalidateQueries({ queryKey: ["vocabularies"] })}
  />
)}
```

- [ ] **Step 2: Wire Protocol detail (Tier 2)**

```tsx
// frontend/src/features/screening-assay/protocol-detail/components/protocol-actions.tsx
import { useAuth } from "@/shared/hooks/use-auth";
import { CascadeDeleteDialog } from "@/shared/components/cascade-delete-dialog";
// ...
const { isAdmin } = useAuth();
{isAdmin && (
  <CascadeDeleteDialog
    entityType="protocol"
    entityId={protocol.id}
    entityLabel={protocol.name}
    onDeleted={() => router.push("/protocols")}
  />
)}
```

> **Important:** `entityLabel` MUST equal the value in the column listed at `infrastructure/cascade/label_fields.py:TABLE_LABELS[table].label_column`. The backend uses that same column to validate `typed_name`. So pass:
> - `protocol.name` for protocol
> - `run.name` for run
> - `molecule.registration_number` for molecule (NOT smiles or display name)
>
> Mismatch yields a 422 even when the user typed something that looked correct in their head.

Repeat for: Run detail, Molecule detail (Tier 2); plus Tier-1 entries on each Tier-1 entity's list/detail view.

- [ ] **Step 3: Manual smoke test**

Spin up dev environment:

```bash
docker compose -f docker-compose.dev.yml up -d
cd frontend && pnpm dev
```

As an admin user:
1. Delete a vocabulary with no references — expect 204 + toast.
2. Delete a vocabulary referenced by a custom field — expect blocker dialog.
3. On a Protocol with one Run: open "Force delete (cascade)" — expect tree showing Run/Plates/Wells. Type wrong name — submit disabled. Type right name + reason — expect success, redirect.

Document outcomes in commit message if anything surprises.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/
git commit -m "feat(admin-ui): wire admin/cascade delete into entity views"
```

---

## Task 20: Final verification

- [ ] **Step 1: Run the entire backend test suite**

```bash
cd backend && uv run pytest -x
```

Expected: PASS.

- [ ] **Step 2: Run the FK coverage gate explicitly**

```bash
cd backend && uv run pytest tests/unit/cascade/test_fk_coverage.py -v
```

Expected: PASS. If new uncovered FKs appear (because Task 8 / Task 11 missed something), add the rule and re-run.

- [ ] **Step 3: Frontend build + typecheck**

```bash
cd frontend && pnpm typecheck && pnpm build
```

Expected: PASS.

- [ ] **Step 4: End-to-end smoke**

Manually exercise: Tier 1 happy path, Tier 1 blocker path, Tier 2 preview, Tier 2 typed-name validation, Tier 2 successful cascade. Verify the audit operation appears in the audit view with operation_type=admin_hard_delete.

- [ ] **Step 5: Update implementation status doc**

```bash
# Append to docs/implementation-status.md a row for "Admin Hard Delete (Tier 1+2)" → DONE.
```

- [ ] **Step 6: Final commit**

```bash
git add docs/implementation-status.md
git commit -m "docs(impl-status): admin hard delete shipped (Tier 1+2)"
```

---

## Notes for the executing engineer

- Always run `uv run pytest` from `backend/`. Always run `pnpm` from `frontend/`.
- The CLAUDE.md says "Before writing any backend code, read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md`." Skim those before starting Task 4.
- If a repo's `find_by_id_in_workspace` doesn't exist on a particular entity, add it (don't add a different shape). Repository methods should be uniform across the codebase.
- Audit volume on big Tier-2 cascades is by-design (per the spec). Don't shortcut it. If a cascade snapshots 14k rows of Wells, that's 14k AuditEntries. Performance is acceptable for v1; revisit only if monitoring shows a real problem.
- The admin delete endpoints intentionally appear on entities that already have non-admin delete endpoints. The non-admin endpoints keep their existing state-restrictions (e.g., "only DRAFT protocols"); the admin endpoint bypasses those. Don't merge them.
