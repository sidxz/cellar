# Protocol Organization — Phase 1 (Keystone) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a scientist creates a protocol, surface structurally-similar existing protocols in real time and let them reroute to "log a run of an existing method" — preventing the run-as-protocol sprawl seen in the CDD audit, without ever blocking or dictating names.

**Architecture:** A pure-domain *Assay Fingerprint* (protocol_type + normalized readout schema) is stored as JSONB on `protocols` and recomputed on every save. A `find_similar` repository method does entity-resolution-style **blocking** (pg_trgm name similarity OR shared target) + **scoring** (weighted blend of target/readout Jaccard, type match, name similarity) over the small candidate set. A `FindSimilarProtocols` query use case (railway pattern, workspace-scoped) backs `POST /protocols/similar`. The frontend create dialog calls it debounced as the user types and renders a dismissible suggestion panel; a "Log a run" CTA reroutes to the existing `CreateRunDialog`.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Alembic / PostgreSQL 16 + `pg_trgm` (already installed) / dry-python `returns` / Lagom DI. Frontend: Next.js / React 19 / TanStack Query v5 / shadcn/ui / hand-written hooks calling `customInstance`. Tests: pytest (`uv run pytest`), vitest/playwright (`pnpm`).

## Global Constraints

- **Layering:** Domain depends on nothing; Application on Domain; Infrastructure on Domain+Application; Interface on all. Never invert.
- **Railway:** Every use case returns `Result[..., DomainError]` (`returns.result`), `async with self._uow`, and guards with `require_workspace_role(auth, "viewer")` + `require_same_workspace(auth, input.workspace_id)`.
- **Suggest, never block. Never enforce naming.** The API and UI only surface suggestions; the user can always proceed.
- **Fingerprint is authoritative-derived on save** — never hand-set; recomputed from the aggregate in the repository. Do NOT store `target_ids` in the fingerprint (targets live in `protocol_targets`; the similarity query joins them live to avoid drift).
- **Commits:** TDD, commit after each task. Always `git commit -m "…" -- <explicit paths>` (the working tree carries unrelated changes — never `git add -A`).
- **Tests:** backend `uv run pytest <path> -v` from `backend/`; frontend `pnpm test` / `pnpm exec playwright test` from `frontend/`. Backend uses `from tests.fakes.fake_auth import FakeAuth` (`FakeAuth(role="viewer", workspace_id=WS)`); integration tests use the `uow: AsyncUnitOfWork` fixture.
- **Generated types:** reuse where present; alias rather than redefine backend DTO shapes.

---

### Task 1: Domain — Assay Fingerprint + `ProtocolSimilarityMatch`

**Files:**
- Create: `backend/src/cellar/domain/screening_assay/protocol_fingerprint.py`
- Create: `backend/src/cellar/domain/screening_assay/protocol_similarity.py`
- Modify: `backend/src/cellar/domain/screening_assay/protocol.py` (add `fingerprint` to `Protocol.__init__`)
- Test: `backend/tests/unit/domain/screening_assay/test_protocol_fingerprint.py`

**Interfaces:**
- Produces: `compute_protocol_fingerprint(protocol: Protocol) -> dict` (keys: `v:int`, `protocol_type:str`, `readout_kinds:list[str]`, `readout_data_types:list[str]`); `ProtocolSimilarityMatch` frozen dataclass (fields: `protocol_id:UUID`, `name:str`, `protocol_type:str`, `status:str`, `score:float`, `is_run_candidate:bool`, `shared_target_ids:list[UUID]`, `shared_readout_kinds:list[str]`); `Protocol.fingerprint: dict | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/screening_assay/test_protocol_fingerprint.py
from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.protocol_fingerprint import compute_protocol_fingerprint


def _protocol(readout_names: list[str]) -> Protocol:
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=uuid.uuid4(),
        name="RNAP core IC50",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in readout_names
        ],
    )


def test_fingerprint_is_case_and_order_independent() -> None:
    a = compute_protocol_fingerprint(_protocol(["IC50", "Hill slope"]))
    b = compute_protocol_fingerprint(_protocol(["hill   slope", "ic50"]))
    assert a == b
    assert a["readout_kinds"] == ["hill slope", "ic50"]
    assert a["protocol_type"] == "biochemical"
    assert a["v"] == 1


def test_fingerprint_distinguishes_readout_schema() -> None:
    a = compute_protocol_fingerprint(_protocol(["IC50"]))
    b = compute_protocol_fingerprint(_protocol(["Tm"]))
    assert a["readout_kinds"] != b["readout_kinds"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_protocol_fingerprint.py -v`
Expected: FAIL — `ModuleNotFoundError: ...protocol_fingerprint`.

- [ ] **Step 3: Write the fingerprint module**

```python
# backend/src/cellar/domain/screening_assay/protocol_fingerprint.py
"""Pure structural fingerprint for a Protocol — the dedup/browse spine.

Derived solely from the aggregate's structured content (type + readout
schema). Targets are intentionally excluded — they live in protocol_targets
and the similarity query joins them live, avoiding a derived-data drift
surface. Recomputed on every save by the repository; never hand-set.
"""
from __future__ import annotations

from cellar.domain.screening_assay.protocol import Protocol

FINGERPRINT_VERSION = 1


def _normalize_readout_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def compute_protocol_fingerprint(protocol: Protocol) -> dict:
    readout_kinds = sorted(
        {_normalize_readout_name(rd.name) for rd in protocol.readout_definitions if rd.name.strip()}
    )
    readout_data_types = sorted({rd.data_type.value for rd in protocol.readout_definitions})
    return {
        "v": FINGERPRINT_VERSION,
        "protocol_type": protocol.protocol_type.value,
        "readout_kinds": readout_kinds,
        "readout_data_types": readout_data_types,
    }
```

- [ ] **Step 4: Add `fingerprint` to the Protocol aggregate**

In `backend/src/cellar/domain/screening_assay/protocol.py`, add a parameter to `Protocol.__init__` (place it right after `recommended_hit_criteria: list[HitCriterion] | None = None,` on line 320):

```python
        recommended_hit_criteria: list[HitCriterion] | None = None,
        fingerprint: dict | None = None,
```

And add the assignment right after `self.recommended_hit_criteria: ... = recommended_hit_criteria` (line 354):

```python
        self.recommended_hit_criteria: list[HitCriterion] | None = recommended_hit_criteria
        # Authoritative-derived structural signature — recomputed by the
        # repository on every save (see compute_protocol_fingerprint). Held
        # here only so a hydrated aggregate carries it for reads.
        self.fingerprint: dict | None = fingerprint
```

- [ ] **Step 5: Write the similarity VO**

```python
# backend/src/cellar/domain/screening_assay/protocol_similarity.py
"""Value object: a single protocol-similarity match (a read-model result)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolSimilarityMatch:
    protocol_id: uuid.UUID
    name: str
    protocol_type: str
    status: str
    score: float
    # True when this looks like a *run* of an existing method (the keystone
    # reroute), not a new method: strong readout-schema overlap AND a shared
    # target or a strong name match.
    is_run_candidate: bool
    shared_target_ids: list[uuid.UUID]
    shared_readout_kinds: list[str]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_protocol_fingerprint.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git -C backend/.. commit -m "feat(screening): protocol fingerprint + similarity VO (domain)" -- \
  backend/src/cellar/domain/screening_assay/protocol_fingerprint.py \
  backend/src/cellar/domain/screening_assay/protocol_similarity.py \
  backend/src/cellar/domain/screening_assay/protocol.py \
  backend/tests/unit/domain/screening_assay/test_protocol_fingerprint.py
```

---

### Task 2: Persistence — migration 059 + `ProtocolModel.fingerprint` column

**Files:**
- Create: `backend/alembic/versions/059_protocol_fingerprint.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py:198` (add column)
- Test: `backend/tests/unit/infrastructure/test_protocol_model_fingerprint_column.py`

**Interfaces:**
- Produces: `protocols.fingerprint` JSONB column; GIN trigram index `ix_protocols_name_trgm` on `protocols.name`; `ProtocolModel.fingerprint: Mapped[dict | None]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/test_protocol_model_fingerprint_column.py
from __future__ import annotations

from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import ProtocolModel


def test_protocol_model_has_fingerprint_column() -> None:
    assert "fingerprint" in ProtocolModel.__table__.columns
    assert ProtocolModel.__table__.columns["fingerprint"].nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_protocol_model_fingerprint_column.py -v`
Expected: FAIL — `AssertionError` (no `fingerprint` column).

- [ ] **Step 3: Add the column to the model**

In `models.py`, add after `recommended_hit_criteria: Mapped[list | None] = mapped_column(JSONB)` (line 198):

```python
    recommended_hit_criteria: Mapped[list | None] = mapped_column(JSONB)
    # Authoritative-derived structural signature (protocol_type + readout
    # schema). Powers similarity blocking/scoring; recomputed on every save.
    fingerprint: Mapped[dict | None] = mapped_column(JSONB)
```

- [ ] **Step 4: Confirm the down-revision id, then write the migration**

First open `backend/alembic/versions/058_sar_activity_projections.py` and read its `revision = "..."` value; use that exact string as `down_revision` below (it is almost certainly `"058_sar_activity_projections"`).

```python
# backend/alembic/versions/059_protocol_fingerprint.py
"""059 — protocol fingerprint column + trigram name index

Adds the structural Assay Fingerprint (JSONB) and a pg_trgm GIN index on
protocols.name to back similarity blocking. pg_trgm was installed in 047.

Revision ID: 059_protocol_fingerprint
Revises: 058_sar_activity_projections
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "059_protocol_fingerprint"
down_revision = "058_sar_activity_projections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column("protocols", sa.Column("fingerprint", JSONB(), nullable=True))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_protocols_name_trgm "
        "ON protocols USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_protocols_name_trgm")
    op.drop_column("protocols", "fingerprint")
```

- [ ] **Step 5: Apply the migration to the dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: applies `059_protocol_fingerprint` with no error.
Verify: `docker exec chem-vault2-postgres-1 psql -U cellar -d cellar -c "\d protocols" | grep -E "fingerprint|trgm"` shows the column and index.

- [ ] **Step 6: Run the model test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_protocol_model_fingerprint_column.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(screening): add protocols.fingerprint column + trgm name index (059)" -- \
  backend/alembic/versions/059_protocol_fingerprint.py \
  backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py \
  backend/tests/unit/infrastructure/test_protocol_model_fingerprint_column.py
```

---

### Task 3: Persistence — repository computes/reads the fingerprint

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py` (`_to_domain`, `_to_model`, `_update_model`)
- Test: `backend/tests/integration/test_protocol_fingerprint_persistence.py`

**Interfaces:**
- Consumes: `compute_protocol_fingerprint` (Task 1); `ProtocolModel.fingerprint` (Task 2).
- Produces: every saved protocol row has a fresh `fingerprint`; hydrated `Protocol.fingerprint` matches the DB.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_protocol_fingerprint_persistence.py
from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def test_fingerprint_is_written_and_round_trips(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    pid = uuid.uuid4()
    protocol = Protocol.create(
        workspace_id=ws,
        name="MDH Resazurin dose response",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="IC50", data_type=ReadoutDataType.NUMERIC),
            ReadoutDefinition(protocol_id=pid, name="Hill slope", data_type=ReadoutDataType.NUMERIC),
        ],
    )
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(protocol)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        reloaded = await repo.find_by_id_in_workspace(ws, protocol.id)
        assert reloaded is not None
        assert reloaded.fingerprint is not None
        assert reloaded.fingerprint["readout_kinds"] == ["hill slope", "ic50"]
        assert reloaded.fingerprint["protocol_type"] == "biochemical"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_protocol_fingerprint_persistence.py -v`
Expected: FAIL — `reloaded.fingerprint is None` (repo doesn't compute it yet).

- [ ] **Step 3: Wire the fingerprint in the repository**

In `protocol_repository.py`, add the import at the top (after the existing `from cellar.domain.screening_assay.protocol import ...` block):

```python
from cellar.domain.screening_assay.protocol_fingerprint import compute_protocol_fingerprint
```

In `_to_domain` (the `return Protocol(...)` near line 514), pass the stored fingerprint through:

```python
            is_locked=model.is_locked,
            locked_by=model.locked_by,
            lock_reason=model.lock_reason,
            locked_at=model.locked_at,
            fingerprint=model.fingerprint,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
```

In `_to_model` (the `model = ProtocolModel(...)` near line 572), set it from the aggregate:

```python
            is_locked=aggregate.is_locked,
            locked_by=aggregate.locked_by,
            lock_reason=aggregate.lock_reason,
            locked_at=aggregate.locked_at,
            fingerprint=compute_protocol_fingerprint(aggregate),
        )
```

In `_update_model` (after `model.locked_at = aggregate.locked_at` near line 628):

```python
        model.locked_at = aggregate.locked_at
        model.fingerprint = compute_protocol_fingerprint(aggregate)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/test_protocol_fingerprint_persistence.py -v`
Expected: PASS.

- [ ] **Step 5: Backfill existing rows**

Add a one-shot script and run it against the dev DB (re-saves recompute fingerprints; existing rows from before this change have `fingerprint IS NULL`).

```python
# backend/scripts/backfill_protocol_fingerprints.py
"""One-shot: compute fingerprints for protocols missing one. Idempotent."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from cellar.domain.screening_assay.protocol_fingerprint import compute_protocol_fingerprint
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import ProtocolModel
from cellar.infrastructure.persistence.sqlalchemy.session import async_session_maker
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)


async def main() -> None:
    uow = AsyncUnitOfWork(async_session_maker)
    async with uow:
        ids = (await uow.session.execute(
            select(ProtocolModel.id, ProtocolModel.workspace_id).where(ProtocolModel.fingerprint.is_(None))
        )).all()
    repo_uow = AsyncUnitOfWork(async_session_maker)
    async with repo_uow:
        repo = SQLAlchemyProtocolRepository(repo_uow)
        for pid, ws in ids:
            p = await repo.find_by_id_in_workspace(ws, pid)
            if p is not None:
                await repo.save(p)
        await repo_uow.commit()
    print(f"backfilled {len(ids)} protocols")


if __name__ == "__main__":
    asyncio.run(main())
```

Run: `cd backend && uv run python scripts/backfill_protocol_fingerprints.py`
Expected: prints `backfilled N protocols`. (If the `async_session_maker` import path differs, confirm it from `infrastructure/di/_core.py`; adjust the import.)

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(screening): compute protocol fingerprint on save + backfill" -- \
  backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py \
  backend/scripts/backfill_protocol_fingerprints.py \
  backend/tests/integration/test_protocol_fingerprint_persistence.py
```

---

### Task 4: Persistence — `find_similar` (blocking + scoring) + repository interface

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (add `find_similar` to `ProtocolRepository`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py` (implement `find_similar`)
- Test: `backend/tests/integration/test_protocol_find_similar.py`

**Interfaces:**
- Consumes: `ProtocolSimilarityMatch` (Task 1), `model.fingerprint` (Task 3), `protocol_targets` (existing), `pg_trgm` (`func.similarity`).
- Produces: `ProtocolRepository.find_similar(workspace_id, *, name, protocol_type, target_ids, readout_names, name_floor=0.3, limit=5) -> list[ProtocolSimilarityMatch]` (sorted by score desc).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_protocol_find_similar.py
from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _make(ws: uuid.UUID, name: str, readouts: list[str]) -> Protocol:
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws,
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in readouts
        ],
    )


async def test_find_similar_flags_run_candidate_and_excludes_unrelated(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    rnap = _make(ws, "RNAP core IC50", ["IC50", "Hill slope", "R squared"])
    unrelated = _make(ws, "Cell viability MTT", ["% viability"])
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(rnap)
        await repo.save(unrelated)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        matches = await repo.find_similar(
            ws,
            name="RNAP core IC50 GSK4329-31 before plates",
            protocol_type="biochemical",
            target_ids=[],
            readout_names=["IC50", "Hill slope", "R squared"],
        )

    names = [m.name for m in matches]
    assert "RNAP core IC50" in names
    assert "Cell viability MTT" not in names
    top = matches[0]
    assert top.name == "RNAP core IC50"
    assert top.is_run_candidate is True
    assert "ic50" in top.shared_readout_kinds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_protocol_find_similar.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'find_similar'`.

- [ ] **Step 3: Add the method to the domain repository protocol**

In `backend/src/cellar/domain/screening_assay/repository.py`, add this import near the top:

```python
from cellar.domain.screening_assay.protocol_similarity import ProtocolSimilarityMatch
```

And add the signature inside `class ProtocolRepository(Protocol):` (after `find_by_name`, around line 66):

```python
    async def find_similar(
        self,
        workspace_id: uuid.UUID,
        *,
        name: str,
        protocol_type: str | None,
        target_ids: list[uuid.UUID],
        readout_names: list[str],
        name_floor: float = 0.3,
        limit: int = 5,
    ) -> list[ProtocolSimilarityMatch]:
        """Find protocols similar to a draft signature, ordered by score desc.

        Blocking: pg_trgm name similarity > name_floor OR shares >=1 target.
        Scoring: weighted blend of target Jaccard, readout-kind Jaccard,
        type match, and name similarity. ``is_run_candidate`` flags strong
        readout overlap + (shared target OR strong name match)."""
        ...
```

- [ ] **Step 4: Implement `find_similar` in the SQLAlchemy repository**

In `protocol_repository.py`: extend the SQLAlchemy import on line 7 to include `or_`:

```python
from sqlalchemy import func, or_, select
```

Add the VO import near the other domain imports:

```python
from cellar.domain.screening_assay.protocol_similarity import ProtocolSimilarityMatch
```

Add this method to `SQLAlchemyProtocolRepository` (after `find_by_name`, around line 88):

```python
    @staticmethod
    def _norm_readout(name: str) -> str:
        return " ".join(name.strip().lower().split())

    async def find_similar(
        self,
        workspace_id: uuid.UUID,
        *,
        name: str,
        protocol_type: str | None,
        target_ids: list[uuid.UUID],
        readout_names: list[str],
        name_floor: float = 0.3,
        limit: int = 5,
    ) -> list[ProtocolSimilarityMatch]:
        draft_readouts = {self._norm_readout(n) for n in readout_names if n.strip()}
        draft_targets = set(target_ids)

        name_sim = func.similarity(ProtocolModel.name, name)
        blocking = [name_sim > name_floor]
        if draft_targets:
            blocking.append(
                ProtocolModel.id.in_(
                    select(protocol_targets.c.protocol_id).where(
                        protocol_targets.c.target_id.in_(draft_targets)
                    )
                )
            )
        stmt = (
            select(ProtocolModel, name_sim.label("name_sim"))
            .where(ProtocolModel.workspace_id == workspace_id, or_(*blocking))
            .limit(200)  # candidate-set safety cap
        )
        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return []

        candidate_ids = [m.id for m, _ in rows]
        tgt_rows = await self._session.execute(
            select(protocol_targets.c.protocol_id, protocol_targets.c.target_id).where(
                protocol_targets.c.protocol_id.in_(candidate_ids)
            )
        )
        targets_by_protocol: dict[uuid.UUID, set[uuid.UUID]] = {}
        for pid, tid in tgt_rows.all():
            targets_by_protocol.setdefault(pid, set()).add(tid)

        matches: list[ProtocolSimilarityMatch] = []
        for model, sim in rows:
            fp = model.fingerprint or {}
            cand_readouts = set(fp.get("readout_kinds", []))
            shared_readouts = draft_readouts & cand_readouts
            ro_union = draft_readouts | cand_readouts
            readout_jaccard = len(shared_readouts) / len(ro_union) if ro_union else 0.0

            cand_targets = targets_by_protocol.get(model.id, set())
            shared_targets = draft_targets & cand_targets
            tgt_union = draft_targets | cand_targets
            target_jaccard = len(shared_targets) / len(tgt_union) if tgt_union else 0.0

            type_match = 1.0 if protocol_type and fp.get("protocol_type") == protocol_type else 0.0
            name_score = float(sim)
            score = (
                0.45 * target_jaccard
                + 0.30 * readout_jaccard
                + 0.10 * type_match
                + 0.15 * name_score
            )
            is_run_candidate = readout_jaccard >= 0.5 and (bool(shared_targets) or name_score >= 0.45)
            matches.append(
                ProtocolSimilarityMatch(
                    protocol_id=model.id,
                    name=model.name,
                    protocol_type=model.protocol_type,
                    status=model.status,
                    score=round(score, 4),
                    is_run_candidate=is_run_candidate,
                    shared_target_ids=sorted(shared_targets),
                    shared_readout_kinds=sorted(shared_readouts),
                )
            )
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:limit]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/test_protocol_find_similar.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(screening): find_similar protocol blocking+scoring" -- \
  backend/src/cellar/domain/screening_assay/repository.py \
  backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py \
  backend/tests/integration/test_protocol_find_similar.py
```

---

### Task 5: Application — `FindSimilarProtocols` query use case

**Files:**
- Create: `backend/src/cellar/application/screening/find_similar_protocols.py`
- Test: `backend/tests/unit/application/screening/test_find_similar_protocols.py`

**Interfaces:**
- Consumes: `ProtocolRepository.find_similar` + `find_effective_targets_for_protocols` (Task 4 / existing); `ProtocolSimilarityMatch`; `TargetRef`.
- Produces: `FindSimilarProtocolsQuery(Query)` (fields: `workspace_id:UUID`, `name:str`, `protocol_type:str|None=None`, `target_ids:list[UUID]=[]`, `readout_names:list[str]=[]`, `limit:int=5`); `SimilarProtocol` frozen dataclass (`match: ProtocolSimilarityMatch`, `targets: list[TargetRef]`); `FindSimilarProtocols(uow, repo)` returning `Result[list[SimilarProtocol], DomainError]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/application/screening/test_find_similar_protocols.py
from __future__ import annotations

import uuid

import pytest
from returns.result import Success

from cellar.application.screening.find_similar_protocols import (
    FindSimilarProtocols,
    FindSimilarProtocolsQuery,
)
from cellar.domain.screening_assay.protocol_similarity import ProtocolSimilarityMatch
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import AuthorizationError
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()


class _FakeUoW:
    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeRepo:
    def __init__(self, matches: list[ProtocolSimilarityMatch], targets: dict) -> None:
        self._matches = matches
        self._targets = targets
        self.call: dict | None = None

    async def find_similar(self, workspace_id, *, name, protocol_type, target_ids, readout_names, name_floor=0.3, limit=5):
        self.call = {"name": name, "target_ids": list(target_ids), "readout_names": list(readout_names)}
        return self._matches

    async def find_effective_targets_for_protocols(self, workspace_id, protocol_ids):
        return {pid: self._targets.get(pid, []) for pid in protocol_ids}


@pytest.fixture
def match() -> ProtocolSimilarityMatch:
    return ProtocolSimilarityMatch(
        protocol_id=uuid.uuid4(), name="RNAP core IC50", protocol_type="biochemical",
        status="active", score=0.82, is_run_candidate=True,
        shared_target_ids=[], shared_readout_kinds=["ic50"],
    )


async def test_returns_matches_with_targets(match: ProtocolSimilarityMatch) -> None:
    tref = TargetRef(id=uuid.uuid4(), name="RNAP", target_type="protein")
    repo = _FakeRepo([match], {match.protocol_id: [tref]})
    uc = FindSimilarProtocols(_FakeUoW(), repo)
    result = await uc(
        FindSimilarProtocolsQuery(workspace_id=WS, name="RNAP core IC50 GSK", readout_names=["IC50"]),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert isinstance(result, Success)
    items = result.unwrap()
    assert len(items) == 1
    assert items[0].match.name == "RNAP core IC50"
    assert items[0].targets[0].name == "RNAP"


async def test_blank_name_short_circuits(match: ProtocolSimilarityMatch) -> None:
    repo = _FakeRepo([match], {})
    uc = FindSimilarProtocols(_FakeUoW(), repo)
    result = await uc(
        FindSimilarProtocolsQuery(workspace_id=WS, name="   "),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert result.unwrap() == []
    assert repo.call is None  # repo never queried


async def test_rejects_cross_workspace() -> None:
    repo = _FakeRepo([], {})
    uc = FindSimilarProtocols(_FakeUoW(), repo)
    with pytest.raises(AuthorizationError):
        await uc(
            FindSimilarProtocolsQuery(workspace_id=uuid.uuid4(), name="x"),
            auth=FakeAuth(role="viewer", workspace_id=WS),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_find_similar_protocols.py -v`
Expected: FAIL — `ModuleNotFoundError: ...find_similar_protocols`.

- [ ] **Step 3: Write the use case**

```python
# backend/src/cellar/application/screening/find_similar_protocols.py
"""FindSimilarProtocols — surface structurally-similar protocols for a draft.

A read-only query backing the create-time suggestion panel. Suggests; never
blocks. Short-circuits to [] on a blank name so the panel stays quiet until
the user has typed something.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol_similarity import ProtocolSimilarityMatch
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class FindSimilarProtocolsQuery(Query):
    workspace_id: uuid.UUID
    name: str
    protocol_type: str | None = None
    target_ids: list[uuid.UUID] = field(default_factory=list)
    readout_names: list[str] = field(default_factory=list)
    limit: int = 5


@dataclass(frozen=True)
class SimilarProtocol:
    match: ProtocolSimilarityMatch
    targets: list[TargetRef] = field(default_factory=list)


class FindSimilarProtocols:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: FindSimilarProtocolsQuery, auth: AuthContext | None = None
    ) -> Result[list[SimilarProtocol], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        if not input.name or not input.name.strip():
            return Success([])
        async with self._uow:
            matches = await self._repo.find_similar(
                input.workspace_id,
                name=input.name.strip(),
                protocol_type=input.protocol_type,
                target_ids=input.target_ids,
                readout_names=input.readout_names,
                limit=input.limit,
            )
            targets = await self._repo.find_effective_targets_for_protocols(
                input.workspace_id, [m.protocol_id for m in matches]
            )
            return Success(
                [SimilarProtocol(match=m, targets=targets.get(m.protocol_id, [])) for m in matches]
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_find_similar_protocols.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(screening): FindSimilarProtocols query use case" -- \
  backend/src/cellar/application/screening/find_similar_protocols.py \
  backend/tests/unit/application/screening/test_find_similar_protocols.py
```

---

### Task 6: Interface — `POST /protocols/similar` (route + dep + DI)

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (register `FindSimilarProtocols`)
- Modify: `backend/src/cellar/interface/dependencies/_screening.py` (add `FindSimilarProtocolsDep`)
- Modify: `backend/src/cellar/interface/dependencies/__init__.py` (export it)
- Modify: `backend/src/cellar/interface/routes/protocols.py` (route + request/response models)
- Test: `backend/tests/api/test_find_similar_protocols_route.py`

**Interfaces:**
- Consumes: `FindSimilarProtocols` (Task 5); `result_to_response`, `AuthDep`, `TargetRefResponse` (existing).
- Produces: `POST /api/v1/protocols/similar` → `list[SimilarProtocolResponse]`.

- [ ] **Step 1: Register in the DI container**

In `backend/src/cellar/infrastructure/di/_screening.py`, find where `ListProtocols` is registered (search `container.define(ListProtocols`). Add the import near the other screening use-case imports:

```python
from cellar.application.screening.find_similar_protocols import FindSimilarProtocols
```

And register it next to `ListProtocols` (mirror its factory — fresh UoW + repo):

```python
    def _find_similar_protocols(c: Container) -> FindSimilarProtocols:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FindSimilarProtocols(uow, SQLAlchemyProtocolRepository(uow))

    container.define(FindSimilarProtocols, _find_similar_protocols)
```

(`AsyncUnitOfWork`, `async_sessionmaker`, `SQLAlchemyProtocolRepository`, `Container` are already imported in this module — confirm and reuse; do not re-import.)

- [ ] **Step 2: Add the FastAPI dependency**

In `backend/src/cellar/interface/dependencies/_screening.py`, add the import (with the other `from cellar.application.screening...` imports):

```python
from cellar.application.screening.find_similar_protocols import FindSimilarProtocols
```

At the bottom of the file (where the other `*Dep = Annotated[...]` aliases live), add:

```python
FindSimilarProtocolsDep = Annotated[
    FindSimilarProtocols, Depends(_get_use_case(FindSimilarProtocols))
]
```

Then in `backend/src/cellar/interface/dependencies/__init__.py`, add `FindSimilarProtocolsDep` to both the `from ._screening import (...)` list and the `__all__` list (match the existing alphabetical-ish ordering used there).

- [ ] **Step 3: Write the failing API test**

```python
# backend/tests/api/test_find_similar_protocols_route.py
"""API test for POST /protocols/similar.

Mirror the client + auth fixtures used by the other protocol route tests in
tests/api/ (the TestClient app fixture + the editor/viewer auth-header
helper). Replace `client` / `auth_headers` below with that conftest's names
if they differ.
"""
from __future__ import annotations


def test_similar_returns_200_and_list(client, auth_headers) -> None:
    resp = client.post(
        "/api/v1/protocols/similar",
        json={"name": "RNAP core IC50", "readout_names": ["IC50"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_blank_name_returns_empty_list(client, auth_headers) -> None:
    resp = client.post(
        "/api/v1/protocols/similar",
        json={"name": "  "},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_find_similar_protocols_route.py -v`
Expected: FAIL — 404 (route not yet defined).

- [ ] **Step 5: Add the route + models**

In `backend/src/cellar/interface/routes/protocols.py`, add the import (with the other `from cellar.application.screening...` imports):

```python
from cellar.application.screening.find_similar_protocols import FindSimilarProtocolsQuery
```

Add `FindSimilarProtocolsDep` to the big `from cellar.interface.dependencies import (...)` block.

Add the request/response models near the other response models (after the `ReadoutDefinitionResponse` block is fine):

```python
class FindSimilarProtocolsRequest(BaseModel):
    name: str
    protocol_type: str | None = None
    target_ids: list[uuid.UUID] = []
    readout_names: list[str] = []
    limit: int = 5


class SimilarProtocolResponse(BaseModel):
    id: uuid.UUID
    name: str
    protocol_type: str
    status: str
    score: float
    is_run_candidate: bool
    shared_readout_kinds: list[str]
    targets: list[TargetRefResponse] = []
```

Add the route. **It MUST be declared before the `GET /protocols/{protocol_id}` route** (literal path vs path param at the same level — FastAPI matches in declaration order). Place it immediately after the `GET /protocols/summary` route:

```python
@router.post(
    "/protocols/similar",
    response_model=list[SimilarProtocolResponse],
    tags=["protocols"],
)
async def find_similar_protocols(
    body: FindSimilarProtocolsRequest,
    auth: AuthDep,
    uc: FindSimilarProtocolsDep,
) -> list[SimilarProtocolResponse]:
    """Suggest structurally-similar existing protocols for a draft. Never blocks."""
    results = result_to_response(
        await uc(
            FindSimilarProtocolsQuery(
                workspace_id=auth.workspace_id,
                name=body.name,
                protocol_type=body.protocol_type,
                target_ids=body.target_ids,
                readout_names=body.readout_names,
                limit=body.limit,
            ),
            auth=auth,
        )
    )
    return [
        SimilarProtocolResponse(
            id=r.match.protocol_id,
            name=r.match.name,
            protocol_type=r.match.protocol_type,
            status=r.match.status,
            score=r.match.score,
            is_run_candidate=r.match.is_run_candidate,
            shared_readout_kinds=r.match.shared_readout_kinds,
            targets=[TargetRefResponse.from_ref(t) for t in r.targets],
        )
        for r in results
    ]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_find_similar_protocols_route.py -v`
Expected: PASS. (If fixtures differ, fix the fixture names per the conftest in `tests/api/`.)

- [ ] **Step 7: Regenerate the OpenAPI types for the frontend**

Run (backend must be running on :8000): `cd frontend && pnpm generate:api`
Review the diff under `frontend/src/shared/lib/api/model/` (additive — the new request/response schemas). Commit it with this task.

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(screening): POST /protocols/similar route + DI wiring" -- \
  backend/src/cellar/infrastructure/di/_screening.py \
  backend/src/cellar/interface/dependencies/_screening.py \
  backend/src/cellar/interface/dependencies/__init__.py \
  backend/src/cellar/interface/routes/protocols.py \
  backend/tests/api/test_find_similar_protocols_route.py \
  frontend/src/shared/lib/api/model
```

---

### Task 7: Frontend — `useSimilarProtocols` hook

**Files:**
- Create: `frontend/src/features/screening-assay/hooks/use-similar-protocols.ts`
- Test: `frontend/src/features/screening-assay/hooks/use-similar-protocols.test.ts`

**Interfaces:**
- Consumes: `POST /protocols/similar` (Task 6); `customInstance`, `useDebounce`, `SEARCH_DEBOUNCE_MS`, `SEARCH_MIN_QUERY_LEN`.
- Produces: `useSimilarProtocols(draft: SimilarProtocolDraft)`; types `SimilarProtocol`, `SimilarProtocolDraft`.

- [ ] **Step 1: Write the hook**

```ts
// frontend/src/features/screening-assay/hooks/use-similar-protocols.ts
"use client";

import { useDebounce } from "@/shared/hooks/use-debounce";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { SEARCH_DEBOUNCE_MS, SEARCH_MIN_QUERY_LEN } from "@/shared/lib/timing";
import { useQuery } from "@tanstack/react-query";

export interface SimilarProtocolTarget {
  id: string;
  name: string;
  target_type: string;
}

export interface SimilarProtocol {
  id: string;
  name: string;
  protocol_type: string;
  status: string;
  score: number;
  is_run_candidate: boolean;
  shared_readout_kinds: string[];
  targets: SimilarProtocolTarget[];
}

export interface SimilarProtocolDraft {
  name: string;
  protocol_type?: string | null;
  target_ids?: string[];
  readout_names?: string[];
}

export function useSimilarProtocols(draft: SimilarProtocolDraft) {
  const debouncedName = useDebounce(draft.name ?? "", SEARCH_DEBOUNCE_MS);
  return useQuery({
    queryKey: [
      "protocols",
      "similar",
      debouncedName,
      draft.protocol_type ?? null,
      draft.target_ids ?? [],
      draft.readout_names ?? [],
    ],
    queryFn: () =>
      customInstance<SimilarProtocol[]>({
        url: `${API_V1}/protocols/similar`,
        method: "POST",
        data: {
          name: debouncedName,
          protocol_type: draft.protocol_type ?? null,
          target_ids: draft.target_ids ?? [],
          readout_names: draft.readout_names ?? [],
          limit: 5,
        },
      }),
    enabled: debouncedName.trim().length >= SEARCH_MIN_QUERY_LEN,
  });
}
```

- [ ] **Step 2: Write the test**

```ts
// frontend/src/features/screening-assay/hooks/use-similar-protocols.test.ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSimilarProtocols } from "./use-similar-protocols";

const post = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (cfg: unknown) => post(cfg),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useSimilarProtocols", () => {
  beforeEach(() => post.mockReset().mockResolvedValue([]));

  it("does not query when the name is too short", async () => {
    renderHook(() => useSimilarProtocols({ name: "a" }), { wrapper });
    await new Promise((r) => setTimeout(r, 350));
    expect(post).not.toHaveBeenCalled();
  });

  it("POSTs the draft once the name is long enough", async () => {
    renderHook(() => useSimilarProtocols({ name: "RNAP core IC50", readout_names: ["IC50"] }), {
      wrapper,
    });
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ url: "/api/v1/protocols/similar", method: "POST" }),
    );
  });
});
```

- [ ] **Step 3: Run the test**

Run: `cd frontend && pnpm test src/features/screening-assay/hooks/use-similar-protocols.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(screening): useSimilarProtocols hook" -- \
  frontend/src/features/screening-assay/hooks/use-similar-protocols.ts \
  frontend/src/features/screening-assay/hooks/use-similar-protocols.test.ts
```

---

### Task 8: Frontend — `SimilarProtocolsPanel` component

**Files:**
- Create: `frontend/src/features/screening-assay/components/similar-protocols-panel.tsx`
- Test: `frontend/src/features/screening-assay/components/similar-protocols-panel.test.tsx`

**Interfaces:**
- Consumes: `useSimilarProtocols`, `SimilarProtocol`, `SimilarProtocolDraft` (Task 7); shadcn `Card`, `Button`, `Badge`.
- Produces: `SimilarProtocolsPanel({ draft, onLogRun }: { draft: SimilarProtocolDraft; onLogRun: (protocolId: string) => void })`.

- [ ] **Step 1: Write the component**

```tsx
// frontend/src/features/screening-assay/components/similar-protocols-panel.tsx
"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { X } from "lucide-react";
import { useState } from "react";
import {
  type SimilarProtocol,
  type SimilarProtocolDraft,
  useSimilarProtocols,
} from "../hooks/use-similar-protocols";

interface Props {
  draft: SimilarProtocolDraft;
  onLogRun: (protocolId: string) => void;
}

export function SimilarProtocolsPanel({ draft, onLogRun }: Props) {
  const [dismissed, setDismissed] = useState(false);
  const { data } = useSimilarProtocols(draft);
  const matches: SimilarProtocol[] = data ?? [];
  if (dismissed || matches.length === 0) return null;

  const runCandidate = matches.find((m) => m.is_run_candidate);
  const others = matches.filter((m) => m !== runCandidate);

  return (
    <div className="rounded-md border border-amber-300/60 bg-amber-50/60 p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-amber-900">
          {runCandidate ? "This looks like a run of an existing method" : "Similar protocols exist"}
        </span>
        <button
          type="button"
          aria-label="Dismiss suggestions"
          onClick={() => setDismissed(true)}
          className="text-amber-700 hover:text-amber-900"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {runCandidate && (
        <div className="mb-2 rounded border bg-white p-2">
          <div className="flex items-center gap-2">
            <span className="font-medium">{runCandidate.name}</span>
            <Badge variant="secondary">{runCandidate.protocol_type}</Badge>
            {runCandidate.targets.map((t) => (
              <Badge key={t.id} variant="outline">
                {t.name}
              </Badge>
            ))}
          </div>
          <Button
            type="button"
            size="sm"
            className="mt-2"
            onClick={() => onLogRun(runCandidate.id)}
          >
            Log a run of this
          </Button>
        </div>
      )}

      {others.length > 0 && (
        <ul className="space-y-1">
          {others.map((m) => (
            <li key={m.id} className="flex items-center gap-2 text-muted-foreground">
              <span>{m.name}</span>
              <Badge variant="outline">{m.protocol_type}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write the test**

```tsx
// frontend/src/features/screening-assay/components/similar-protocols-panel.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SimilarProtocol } from "../hooks/use-similar-protocols";
import { SimilarProtocolsPanel } from "./similar-protocols-panel";

const match: SimilarProtocol = {
  id: "p1",
  name: "RNAP core IC50",
  protocol_type: "biochemical",
  status: "active",
  score: 0.82,
  is_run_candidate: true,
  shared_readout_kinds: ["ic50"],
  targets: [{ id: "t1", name: "RNAP", target_type: "protein" }],
};

const data = vi.fn<[], SimilarProtocol[]>(() => [match]);
vi.mock("../hooks/use-similar-protocols", async () => ({
  ...(await vi.importActual<object>("../hooks/use-similar-protocols")),
  useSimilarProtocols: () => ({ data: data() }),
}));

describe("SimilarProtocolsPanel", () => {
  it("fires onLogRun for a run candidate", () => {
    const onLogRun = vi.fn();
    render(<SimilarProtocolsPanel draft={{ name: "RNAP core IC50" }} onLogRun={onLogRun} />);
    fireEvent.click(screen.getByText("Log a run of this"));
    expect(onLogRun).toHaveBeenCalledWith("p1");
  });

  it("hides after dismiss", () => {
    render(<SimilarProtocolsPanel draft={{ name: "RNAP core IC50" }} onLogRun={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Dismiss suggestions"));
    expect(screen.queryByText("RNAP core IC50")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test**

Run: `cd frontend && pnpm test src/features/screening-assay/components/similar-protocols-panel.test.tsx`
Expected: PASS (2 tests). (If `@/shared/components/ui/badge` path differs, confirm the Badge import path used elsewhere in the feature and adjust.)

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(screening): SimilarProtocolsPanel component" -- \
  frontend/src/features/screening-assay/components/similar-protocols-panel.tsx \
  frontend/src/features/screening-assay/components/similar-protocols-panel.test.tsx
```

---

### Task 9: Frontend — integrate the panel + "Log a run" reroute

**Files:**
- Modify: `frontend/src/features/screening-assay/components/create-protocol-dialog.tsx`
- Modify: `frontend/src/features/screening-assay/components/screening-dashboard.tsx`
- Test (E2E): `frontend/tests/e2e/protocol-similar-suggestion.spec.ts`

**Interfaces:**
- Consumes: `SimilarProtocolsPanel` (Task 8); existing `CreateRunDialog({ protocolId, open, onOpenChange })`.
- Produces: `CreateProtocolDialog` gains an optional `onLogRun?: (protocolId: string) => void` prop; the dashboard wires it to open `CreateRunDialog`.

- [ ] **Step 1: Add the panel to the create dialog**

In `create-protocol-dialog.tsx`:

(a) Add the import (with the other component imports near line 62):

```tsx
import { SimilarProtocolsPanel } from "./similar-protocols-panel";
```

(b) Extend the props interface (`interface CreateProtocolDialogProps`, line 154):

```tsx
interface CreateProtocolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onLogRun?: (protocolId: string) => void;
  // ...keep any existing fields below unchanged
```

and destructure it in the component signature (line 161):

```tsx
export function CreateProtocolDialog({
  open,
  onOpenChange,
  onLogRun,
  // ...existing
}: CreateProtocolDialogProps) {
```

(c) The form already exposes `form.watch("name")` (line 302) and `readoutValues = form.watch("readouts")` (line 223). Just below the name `<Input ... {...form.register("name")} />` block (line 410), insert the panel:

```tsx
            <Input placeholder="e.g., EGFR Kinase IC50" {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-[11px] text-destructive">{form.formState.errors.name.message}</p>
            )}
            <SimilarProtocolsPanel
              draft={{
                name: form.watch("name") ?? "",
                protocol_type: form.watch("protocol_type") || null,
                target_ids: form.watch("target_ids") ?? [],
                readout_names: (form.watch("readouts") ?? [])
                  .map((r) => r.name)
                  .filter((n): n is string => Boolean(n)),
              }}
              onLogRun={(protocolId) => {
                onOpenChange(false);
                onLogRun?.(protocolId);
              }}
            />
```

- [ ] **Step 2: Wire the reroute in the dashboard**

In `screening-dashboard.tsx`:

(a) Add the import (with the other component imports near line 11):

```tsx
import { CreateRunDialog } from "./create-run-dialog";
```

(b) Add state (near line 19, with the other `useState` calls):

```tsx
  const [createRunForProtocol, setCreateRunForProtocol] = useState<string | null>(null);
```

(c) Pass `onLogRun` to the existing `CreateProtocolDialog` mount (line 76) and mount a `CreateRunDialog`:

```tsx
      <CreateProtocolDialog
        open={createProtocolOpen}
        onOpenChange={setCreateProtocolOpen}
        onLogRun={(protocolId) => setCreateRunForProtocol(protocolId)}
      />
      {createRunForProtocol && (
        <CreateRunDialog
          protocolId={createRunForProtocol}
          open={true}
          onOpenChange={(o) => {
            if (!o) setCreateRunForProtocol(null);
          }}
        />
      )}
```

- [ ] **Step 3: Typecheck + lint**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm lint`
Expected: no type errors; lint exit code 0. (If `CreateRunDialog` requires props beyond `protocolId/open/onOpenChange`, supply them per its signature — re-read `create-run-dialog.tsx:66` props and pass the required ones.)

- [ ] **Step 4: Write the E2E test**

```ts
// frontend/tests/e2e/protocol-similar-suggestion.spec.ts
import { expect, test } from "@playwright/test";

// Assumes an authenticated session + at least one existing protocol named
// like "RNAP core IC50". Mirror the auth/setup of the other e2e specs in
// frontend/tests/e2e/ (storageState / beforeEach login helper).
test("typing a near-duplicate name surfaces a suggestion and never blocks", async ({ page }) => {
  await page.goto("/assays");
  await page.getByRole("button", { name: "New Protocol" }).click();
  await page.getByPlaceholder("e.g., EGFR Kinase IC50").fill("RNAP core IC50 GSK4329-31 before");

  // Suggestion appears (above-threshold), and the create flow is NOT blocked.
  await expect(page.getByText(/existing method|Similar protocols exist/i)).toBeVisible();
  await expect(page.getByPlaceholder("e.g., EGFR Kinase IC50")).toBeEditable();
});
```

- [ ] **Step 5: Run the E2E test**

Run: `cd frontend && pnpm exec playwright test tests/e2e/protocol-similar-suggestion.spec.ts`
Expected: PASS. (If the e2e harness needs seeded data/auth, follow the setup used by the other specs in `frontend/tests/e2e/`.)

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(screening): surface similar protocols in create dialog + log-a-run reroute" -- \
  frontend/src/features/screening-assay/components/create-protocol-dialog.tsx \
  frontend/src/features/screening-assay/components/screening-dashboard.tsx \
  frontend/tests/e2e/protocol-similar-suggestion.spec.ts
```

---

## Final verification

- [ ] Backend: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_protocol_fingerprint.py tests/unit/infrastructure/test_protocol_model_fingerprint_column.py tests/integration/test_protocol_fingerprint_persistence.py tests/integration/test_protocol_find_similar.py tests/unit/application/screening/test_find_similar_protocols.py tests/api/test_find_similar_protocols_route.py -v` → all pass.
- [ ] Frontend: `cd frontend && pnpm test src/features/screening-assay && pnpm lint` → pass, lint exit 0.
- [ ] Manual smoke: start the app, open `/assays` → New Protocol, type a name matching an existing protocol → panel appears; click "Log a run of this" → create dialog closes and the run dialog opens for that protocol; click "Continue creating new anyway" path (just keep typing) → never blocked.

## Self-review (completed during authoring)

- **Spec coverage:** §4 fingerprint → Tasks 1-3; §5.1 search-first + keystone → Tasks 4-9; §5.2 log-a-run capture → Task 9 (reuses existing `CreateRunDialog`/`conditions` JSONB — no schema change, per spec §6.1). Out of Phase-1 scope per spec: facets/autocomplete (Phase 2), embeddings/hygiene/library (Phase 3), "canonical/steward" badges (spec §9 risk 3 — intentionally omitted), condition pre-fill parsing (spec §9 risk 5 — deferred; the reroute opens the run dialog and the scientist fills conditions).
- **Placeholders:** none — every code step is complete. The three "mirror the existing harness" notes (API-test fixtures, E2E auth, Badge import path) are pointers to repo-specific test infra, with full test bodies provided.
- **Type consistency:** `compute_protocol_fingerprint` / `ProtocolSimilarityMatch` / `find_similar` / `FindSimilarProtocolsQuery` / `SimilarProtocol` / `SimilarProtocolResponse` / `SimilarProtocol` (FE) field names verified consistent across domain → repo → use case → route → hook → component.

## Deferred to Phase 2 (separate plan)

Facets-without-forms: ontology-grounded facet chips (reuse `BioPortalClient` / `useOntologySearch`), autocomplete-at-entry for category + readout names, provenance-aware name suggestion, and the Phase-2 fingerprint facet slots (`organism`, `assay_format`, `detection`, `stage`).
