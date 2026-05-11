# Screen Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `Campaign` aggregate in the `research_organization` bounded context — an immutable, per-compound, multi-protocol result snapshot, with frozen-Collection emission and a stable DAIKON-facing JSON contract.

**Architecture:** New aggregate `Campaign` with owned entities `CampaignChannel`, `CampaignResult`, `CampaignMeasurement`. Lifecycle `draft → closed → superseded`. Snapshot rows are materialized at close (Option A — copy values, retain traceability FKs). `Collection` is extended with `is_frozen` + `derived_from_campaign_id` so closing a campaign can emit a frozen output Collection (the cascade arrow). Cross-aggregate write protection via `CampaignLockGuard` mirroring the existing `DataLockGuard` pattern. Frontend feature folder `screen-campaign/` with AG Grid pivot for the builder and read-only view.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / pytest / Alembic / Lagom DI / dry-python returns (Railway) / Next.js 16 / React 19 / TanStack Query v5 / AG Grid Community / orval (OpenAPI codegen) / Zod / RHF

**Spec:** `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`

---

## File Map

| Layer | File | Action |
|-------|------|--------|
| Domain (Phase 1) | `backend/src/chem_vault/domain/research_organization/collection.py` | Add `is_frozen` + `derived_from_campaign_id` + `add_*`/`remove_*` rejection when frozen |
| Domain (Phase 2) | `backend/src/chem_vault/domain/research_organization/enums.py` | Add `CampaignStatus`, `SelectionRule`, `ChannelSourceKind`, `ValueQualifier`, `HitCall`, `CampaignDecision`, `QualifierHandling` |
| Domain | `backend/src/chem_vault/domain/research_organization/compound_source.py` | NEW: `CompoundSource` discriminated VO (4 kinds) |
| Domain | `backend/src/chem_vault/domain/research_organization/campaign_channel.py` | NEW: `CampaignChannel` entity |
| Domain | `backend/src/chem_vault/domain/research_organization/campaign_measurement.py` | NEW: `CampaignMeasurement` entity |
| Domain | `backend/src/chem_vault/domain/research_organization/campaign_result.py` | NEW: `CampaignResult` entity |
| Domain | `backend/src/chem_vault/domain/research_organization/campaign.py` | NEW: `Campaign` aggregate root |
| Domain | `backend/src/chem_vault/domain/research_organization/events.py` | Extend with `Campaign*` events |
| Domain | `backend/src/chem_vault/domain/research_organization/campaign_lock_guard.py` | NEW: `CampaignLockGuard` + `CampaignLockChecker` port |
| Domain | `backend/src/chem_vault/domain/research_organization/repository.py` | Extend with `CampaignRepository` Protocol |
| Persistence (Phase 3) | `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/models.py` | Add `CampaignModel`, `CampaignChannelModel`, `CampaignResultModel`, `CampaignMeasurementModel`; modify `CollectionModel` |
| Persistence | `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py` | NEW: `SQLAlchemyCampaignRepository` |
| Persistence | `backend/alembic/versions/026_screen_campaign.py` | NEW migration |
| Resolver (Phase 4) | `backend/src/chem_vault/application/research_organization/channel_resolution.py` | NEW: `ChannelResolutionQuery` Protocol + `ChannelResolver` service |
| Resolver | `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/channel_resolution_query.py` | NEW: SQL impl |
| App (Phase 5) | `backend/src/chem_vault/application/research_organization/create_campaign.py` | NEW |
| App | `backend/src/chem_vault/application/research_organization/update_campaign.py` | NEW (name/desc/source re-seed) |
| App | `backend/src/chem_vault/application/research_organization/manage_campaign_channels.py` | NEW (add/remove/edit channel) |
| App | `backend/src/chem_vault/application/research_organization/manage_campaign_results.py` | NEW (add row, exclude row, set decision, override cell) |
| App | `backend/src/chem_vault/application/research_organization/refresh_campaign.py` | NEW (refresh from sources, recompute channel) |
| App | `backend/src/chem_vault/application/research_organization/close_campaign.py` | NEW |
| App | `backend/src/chem_vault/application/research_organization/supersede_campaign.py` | NEW |
| App | `backend/src/chem_vault/application/research_organization/get_published_campaign.py` | NEW |
| Interface (Phase 6) | `backend/src/chem_vault/interface/routes/campaigns.py` | NEW |
| Interface | `backend/src/chem_vault/interface/app.py` | Register router |
| Interface | `backend/src/chem_vault/infrastructure/di/container.py` | Wire repo + use cases |
| Interface | `backend/src/chem_vault/interface/dependencies.py` | Add `CampaignRepoDep`, use-case factories |
| Frontend (Phase 7) | `frontend/src/features/screen-campaign/types/index.ts` | NEW |
| Frontend | `frontend/src/features/screen-campaign/lib/api.ts` | NEW (orval-generated thin wrappers) |
| Frontend | `frontend/src/features/screen-campaign/components/campaign-list.tsx` | NEW |
| Frontend | `frontend/src/app/(dashboard)/projects/[projectId]/campaigns/page.tsx` | NEW route |
| Frontend (Phase 8) | `frontend/src/features/screen-campaign/components/campaign-builder/*` | NEW (grid + channel strip + decision panel + close dialog) |
| Frontend | `frontend/src/app/(dashboard)/projects/[projectId]/campaigns/[id]/page.tsx` | NEW route (builder + view) |
| Frontend (Phase 9) | `frontend/src/features/screen-campaign/components/campaign-view/*` | NEW (closed read-only) |
| Docs (Phase 10) | `docs/domain-model/05-research-organization.md` | Append Campaign aggregate section |
| Docs | `docs/implementation-status.md` | Add session entries |
| Docs | `CLAUDE.md` | (no change needed — bounded context list unchanged) |

---

## Phase 1 — Collection extensions (foundation, separable commit)

### Task 1.1: Add `is_frozen` and `derived_from_campaign_id` to `Collection` domain

**Files:**
- Modify: `backend/src/chem_vault/domain/research_organization/collection.py`
- Test: `backend/tests/unit/domain/research_organization/test_collection_frozen.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/domain/research_organization/test_collection_frozen.py`:

```python
import uuid

import pytest

from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.shared.errors import ValidationError


def test_collection_defaults_to_not_frozen():
    coll = Collection.create(
        workspace_id=uuid.uuid4(),
        name="Test",
        created_by=uuid.uuid4(),
    )
    assert coll.is_frozen is False
    assert coll.derived_from_campaign_id is None


def test_freeze_sets_flag_and_origin():
    campaign_id = uuid.uuid4()
    coll = Collection.create(
        workspace_id=uuid.uuid4(),
        name="Hits",
        created_by=uuid.uuid4(),
    )
    coll.freeze(derived_from_campaign_id=campaign_id)
    assert coll.is_frozen is True
    assert coll.derived_from_campaign_id == campaign_id


def test_freeze_is_idempotent_with_same_origin():
    campaign_id = uuid.uuid4()
    coll = Collection.create(
        workspace_id=uuid.uuid4(), name="X", created_by=uuid.uuid4()
    )
    coll.freeze(derived_from_campaign_id=campaign_id)
    coll.freeze(derived_from_campaign_id=campaign_id)  # no-op, no error
    assert coll.is_frozen is True


def test_freeze_rejects_different_origin_after_freeze():
    coll = Collection.create(
        workspace_id=uuid.uuid4(), name="X", created_by=uuid.uuid4()
    )
    coll.freeze(derived_from_campaign_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="already frozen"):
        coll.freeze(derived_from_campaign_id=uuid.uuid4())


def test_update_rejects_when_frozen():
    coll = Collection.create(
        workspace_id=uuid.uuid4(), name="X", created_by=uuid.uuid4()
    )
    coll.freeze(derived_from_campaign_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="frozen"):
        coll.update(name="renamed")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_collection_frozen.py -v
```

Expected: FAIL — `AttributeError: 'Collection' object has no attribute 'is_frozen'`

- [ ] **Step 3: Add the fields + `freeze()` and guard `update()`**

In `backend/src/chem_vault/domain/research_organization/collection.py`:

1. Extend `__init__` signature with `is_frozen: bool = False` and `derived_from_campaign_id: uuid.UUID | None = None`, assign as attributes (after `visibility`).
2. Add method:

```python
    def freeze(self, *, derived_from_campaign_id: uuid.UUID) -> None:
        """Mark the collection as frozen — origin campaign owns it forever.

        Idempotent when called with the same origin. Raises if already
        frozen with a different origin.
        """
        if self.is_frozen:
            if self.derived_from_campaign_id != derived_from_campaign_id:
                raise ValidationError(
                    "Collection is already frozen with a different origin"
                )
            return
        self.is_frozen = True
        self.derived_from_campaign_id = derived_from_campaign_id
        self.updated_at = datetime.now(UTC)
```

3. Add a guard at the top of `update(...)`:

```python
        if self.is_frozen:
            raise ValidationError("Cannot update a frozen collection")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_collection_frozen.py -v
```

Expected: PASS (all five tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/chem_vault/domain/research_organization/collection.py backend/tests/unit/domain/research_organization/test_collection_frozen.py
git commit -m "feat(domain): Collection gains is_frozen + derived_from_campaign_id"
```

---

### Task 1.2: Reject membership mutations on frozen collections

**Files:**
- Modify: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py`
- Test: `backend/tests/integration/research_organization/test_collection_frozen_membership.py`

- [ ] **Step 1: Write the failing integration test**

Create the test that creates a Collection, freezes it via `Collection.freeze()`, saves, and then asserts `add_molecules`/`remove_molecules` raise `CollectionFrozenError`.

```python
import uuid

import pytest

from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.shared.errors import ValidationError


@pytest.mark.asyncio
async def test_add_molecules_rejected_when_frozen(uow_factory, collection_repo):
    workspace_id = uuid.uuid4()
    async with uow_factory() as uow:
        coll = Collection.create(
            workspace_id=workspace_id, name="Hits", created_by=uuid.uuid4()
        )
        coll.freeze(derived_from_campaign_id=uuid.uuid4())
        await collection_repo.save(coll)
        await uow.commit()

    with pytest.raises(ValidationError, match="frozen"):
        await collection_repo.add_molecules(workspace_id, coll.id, [uuid.uuid4()])


@pytest.mark.asyncio
async def test_remove_molecules_rejected_when_frozen(uow_factory, collection_repo):
    # ... mirror above for remove_molecules
    ...
```

(Use existing fixtures from `backend/tests/integration/conftest.py`.)

- [ ] **Step 2: Run test to verify it fails**

Expected: tests are skipped/error because mutation paths don't check `is_frozen` yet.

- [ ] **Step 3: Implement the guard**

At the top of `add_molecules`, `remove_molecules`, and `replace_molecule` in `collection_repository.py`, load the `Collection` aggregate first and reject if `is_frozen`:

```python
        coll = await self.find_by_id_in_workspace(workspace_id, collection_id)
        if coll is None:
            raise NotFoundError(...)
        if coll.is_frozen:
            raise ValidationError(
                f"Collection {collection_id} is frozen and cannot be modified"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/integration/research_organization/test_collection_frozen_membership.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py backend/tests/integration/research_organization/test_collection_frozen_membership.py
git commit -m "feat(persistence): reject membership mutations on frozen Collections"
```

---

### Task 1.3: Alembic migration — add `is_frozen` + `derived_from_campaign_id` to `collection`

> ⚠️ **Migration, ORM column additions, and `_to_domain`/`_update_model` mapping updates MUST land in a single commit — splitting them creates a window where frozen Collections can be mutated.**

**Files:**
- Create: `backend/alembic/versions/026_collection_frozen.py` (separate from the larger 027 to keep blast radius small)
- Modify: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/models.py` — add the two columns to `CollectionModel`
- Modify: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py` — round-trip the new fields in `_to_domain` and `_update_model`

- [ ] **Step 1: Add the SA columns**

In `models.py`, on `CollectionModel`:

```python
    is_frozen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    derived_from_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
```

- [ ] **Step 1a: Update `_to_domain` in `SQLAlchemyCollectionRepository`**

In `collection_repository.py`, extend the `_to_domain` mapper so the new persisted fields rehydrate onto the aggregate:

```python
    return Collection(
        ...,
        is_frozen=model.is_frozen,
        derived_from_campaign_id=model.derived_from_campaign_id,
    )
```

Without this, the frozen guards in `add_molecules`/`remove_molecules` will always see `is_frozen=False` regardless of DB state — silently bypassing the lock.

- [ ] **Step 1b: Update `_update_model` in `SQLAlchemyCollectionRepository`**

Also in `collection_repository.py`, extend `_update_model` so aggregate changes are persisted back:

```python
    model.is_frozen = aggregate.is_frozen
    model.derived_from_campaign_id = aggregate.derived_from_campaign_id
```

Without this, calling `coll.freeze(...)` followed by `save()` will not persist the freeze.

- [ ] **Step 2: Generate migration scaffold**

```bash
cd backend && uv run alembic revision -m "collection frozen"
```

Rename the generated file to `026_collection_frozen.py`. Update `down_revision` chain.

- [ ] **Step 3: Fill in the migration body**

```python
def upgrade() -> None:
    op.add_column(
        "collection",
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "collection",
        sa.Column("derived_from_campaign_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_collection_derived_from_campaign_id",
        "collection",
        ["derived_from_campaign_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_derived_from_campaign_id", table_name="collection")
    op.drop_column("collection", "derived_from_campaign_id")
    op.drop_column("collection", "is_frozen")
```

- [ ] **Step 4: Apply migration locally**

```bash
cd backend && uv run alembic upgrade head
```

Expected: clean apply.

- [ ] **Step 5: Run repo integration tests**

```bash
cd backend && uv run pytest tests/integration/research_organization/ -v
```

Expected: PASS — including the frozen-guard test from Task 1.2 now exercises real DB.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/026_collection_frozen.py \
        backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/models.py \
        backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py
git commit -m "feat(db): collection.is_frozen + derived_from_campaign_id"
```

All three changes — migration, ORM column additions, and the `_to_domain`/`_update_model` mapping updates — MUST be in this single commit. Splitting creates a window where the frozen guards are silently bypassed.

---

## Phase 2 — Domain layer: Campaign aggregate

### Task 2.1: Domain enums

**Files:**
- Modify: `backend/src/chem_vault/domain/research_organization/enums.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_enums.py`

- [ ] **Step 1: Write the failing test**

```python
from chem_vault.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    CampaignDecision,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)


def test_campaign_status_values():
    assert CampaignStatus.DRAFT.value == "draft"
    assert CampaignStatus.CLOSED.value == "closed"
    assert CampaignStatus.SUPERSEDED.value == "superseded"


def test_selection_rule_members():
    assert {r.value for r in SelectionRule} == {
        "latest_approved_run",
        "mean_across_runs",
        "geometric_mean",
        "manual_pick",
    }


def test_value_qualifier_members():
    assert {q.value for q in ValueQualifier} == {"=", "<", ">", "nd", "excluded"}


def test_hit_call_members():
    assert {h.value for h in HitCall} == {"hit", "miss", "inconclusive"}


def test_decision_members():
    assert {d.value for d in CampaignDecision} == {"selected", "deferred", "rejected"}


def test_channel_source_kind_members():
    assert {k.value for k in ChannelSourceKind} == {"readout_data", "dose_response_curve"}


def test_qualifier_handling_members():
    assert {q.value for q in QualifierHandling} == {
        "include_qualified",
        "exclude_qualified",
        "treat_as_limit",
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign_enums.py -v
```

Expected: FAIL — ImportError.

- [ ] **Step 3: Add enums**

Append to `enums.py`:

```python
class CampaignStatus(StrEnum):
    DRAFT = "draft"
    CLOSED = "closed"
    SUPERSEDED = "superseded"


class SelectionRule(StrEnum):
    LATEST_APPROVED_RUN = "latest_approved_run"
    MEAN_ACROSS_RUNS = "mean_across_runs"
    GEOMETRIC_MEAN = "geometric_mean"
    MANUAL_PICK = "manual_pick"


class ChannelSourceKind(StrEnum):
    READOUT_DATA = "readout_data"
    DOSE_RESPONSE_CURVE = "dose_response_curve"


class ValueQualifier(StrEnum):
    EQ = "="
    LT = "<"
    GT = ">"
    ND = "nd"
    EXCLUDED = "excluded"


class HitCall(StrEnum):
    HIT = "hit"
    MISS = "miss"
    INCONCLUSIVE = "inconclusive"


class CampaignDecision(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class QualifierHandling(StrEnum):
    INCLUDE_QUALIFIED = "include_qualified"
    EXCLUDE_QUALIFIED = "exclude_qualified"
    TREAT_AS_LIMIT = "treat_as_limit"
```

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign_enums.py -v
git add backend/src/chem_vault/domain/research_organization/enums.py backend/tests/unit/domain/research_organization/test_campaign_enums.py
git commit -m "feat(domain): screen campaign enums"
```

---

### Task 2.2: `CompoundSource` discriminated value object

**Files:**
- Create: `backend/src/chem_vault/domain/research_organization/compound_source.py`
- Test: `backend/tests/unit/domain/research_organization/test_compound_source.py`

- [ ] **Step 1: Write failing tests**

```python
import uuid

import pytest

from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    CompoundSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import ValidationError


def test_explicit_list_round_trip():
    ids = [uuid.uuid4(), uuid.uuid4()]
    src = ExplicitListSource(molecule_ids=ids)
    data = src.to_dict()
    assert data["kind"] == "explicit_list"
    back = CompoundSource.from_dict(data)
    assert isinstance(back, ExplicitListSource)
    assert back.molecule_ids == ids


def test_collection_source_requires_collection_id():
    with pytest.raises(ValidationError):
        CollectionSource(collection_id=None)  # type: ignore[arg-type]


def test_saved_search_source_round_trip():
    sid = uuid.uuid4()
    src = SavedSearchSource(saved_search_id=sid)
    back = CompoundSource.from_dict(src.to_dict())
    assert isinstance(back, SavedSearchSource)
    assert back.saved_search_id == sid


def test_derived_from_campaign_filters_decisions():
    cid = uuid.uuid4()
    src = DerivedFromCampaignSource(
        campaign_id=cid, decision_filter=[CampaignDecision.SELECTED]
    )
    data = src.to_dict()
    assert data["decision_filter"] == ["selected"]
    back = CompoundSource.from_dict(data)
    assert isinstance(back, DerivedFromCampaignSource)
    assert back.campaign_id == cid
    assert back.decision_filter == [CampaignDecision.SELECTED]


def test_explicit_list_rejects_empty():
    with pytest.raises(ValidationError):
        ExplicitListSource(molecule_ids=[])


def test_from_dict_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        CompoundSource.from_dict({"kind": "nope"})
```

- [ ] **Step 2: Run, expect FAIL (ImportError)**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_compound_source.py -v
```

- [ ] **Step 3: Implement `compound_source.py`**

```python
"""CompoundSource — discriminated value object for campaign seeding."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class CompoundSource:
    kind: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CompoundSource":
        kind = data.get("kind")
        if kind == "explicit_list":
            return ExplicitListSource(
                molecule_ids=[uuid.UUID(s) for s in data["molecule_ids"]]
            )
        if kind == "collection":
            return CollectionSource(collection_id=uuid.UUID(data["collection_id"]))
        if kind == "saved_search":
            return SavedSearchSource(
                saved_search_id=uuid.UUID(data["saved_search_id"])
            )
        if kind == "derived_from_campaign":
            return DerivedFromCampaignSource(
                campaign_id=uuid.UUID(data["campaign_id"]),
                decision_filter=[
                    CampaignDecision(v) for v in data.get("decision_filter", [])
                ],
            )
        raise ValidationError(f"Unknown CompoundSource kind: {kind!r}")


@dataclass(frozen=True)
class ExplicitListSource(CompoundSource):
    kind: ClassVar[str] = "explicit_list"
    molecule_ids: list[uuid.UUID] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.molecule_ids:
            raise ValidationError("ExplicitListSource requires at least one molecule_id")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "molecule_ids": [str(m) for m in self.molecule_ids]}


@dataclass(frozen=True)
class CollectionSource(CompoundSource):
    kind: ClassVar[str] = "collection"
    collection_id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.collection_id is None:
            raise ValidationError("CollectionSource requires collection_id")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "collection_id": str(self.collection_id)}


@dataclass(frozen=True)
class SavedSearchSource(CompoundSource):
    kind: ClassVar[str] = "saved_search"
    saved_search_id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.saved_search_id is None:
            raise ValidationError("SavedSearchSource requires saved_search_id")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "saved_search_id": str(self.saved_search_id)}


@dataclass(frozen=True)
class DerivedFromCampaignSource(CompoundSource):
    kind: ClassVar[str] = "derived_from_campaign"
    campaign_id: uuid.UUID = None  # type: ignore[assignment]
    decision_filter: list[CampaignDecision] = field(
        default_factory=lambda: [CampaignDecision.SELECTED]
    )

    def __post_init__(self) -> None:
        if self.campaign_id is None:
            raise ValidationError("DerivedFromCampaignSource requires campaign_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "campaign_id": str(self.campaign_id),
            "decision_filter": [d.value for d in self.decision_filter],
        }
```

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_compound_source.py -v
git add backend/src/chem_vault/domain/research_organization/compound_source.py backend/tests/unit/domain/research_organization/test_compound_source.py
git commit -m "feat(domain): CompoundSource discriminated VO"
```

---

### Task 2.3: `CampaignChannel` entity

**Files:**
- Create: `backend/src/chem_vault/domain/research_organization/campaign_channel.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_channel.py`

- [ ] **Step 1: Write failing tests**

```python
import uuid

import pytest

from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.shared.errors import ValidationError


def test_channel_minimum_construction():
    ch = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    assert ch.label == "IC50"
    assert ch.qc_filter is None
    assert ch.hit_threshold is None


def test_channel_label_required():
    with pytest.raises(ValidationError):
        CampaignChannel(
            campaign_id=uuid.uuid4(),
            label="   ",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
        )


def test_channel_holds_hit_threshold():
    hc = HitCriterion(readout_name="IC50", operator="lt", value=1000.0)
    ch = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        hit_threshold=hc,
    )
    assert ch.hit_threshold == hc


def test_channel_qc_filter_jsonable():
    ch = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="x",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter={"min_z_prime": 0.5, "require_approved": True},
    )
    assert ch.qc_filter == {"min_z_prime": 0.5, "require_approved": True}
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign_channel.py -v
```

- [ ] **Step 3: Implement `campaign_channel.py`**

```python
"""CampaignChannel — owned entity defining one column in a campaign snapshot."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.shared.errors import ValidationError


@dataclass
class CampaignChannel:
    """Defines one measurement column resolved per compound at close."""

    campaign_id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: ChannelSourceKind
    selection_rule: SelectionRule
    qualifier_handling: QualifierHandling
    display_order: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterion | None = None

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValidationError("CampaignChannel.label must not be empty")
        self.label = self.label.strip()
        if self.display_order < 0:
            raise ValidationError("display_order must be ≥ 0")
```

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign_channel.py -v
git add backend/src/chem_vault/domain/research_organization/campaign_channel.py backend/tests/unit/domain/research_organization/test_campaign_channel.py
git commit -m "feat(domain): CampaignChannel entity"
```

---

### Task 2.4: `CampaignMeasurement` entity

**Files:**
- Create: `backend/src/chem_vault/domain/research_organization/campaign_measurement.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_measurement.py`

- [ ] **Step 1: Write failing tests**

```python
import uuid
from datetime import date

import pytest

from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.enums import HitCall, ValueQualifier
from chem_vault.domain.shared.errors import ValidationError


def test_minimum_measurement():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="EGFR Binding",
        protocol_version_snapshot=3,
    )
    assert m.value == 42.0
    assert m.hit_call is None
    assert m.is_manual_override is False


def test_nd_measurement_has_no_value():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.value is None


def test_eq_qualifier_requires_value():
    with pytest.raises(ValidationError, match="numeric value"):
        CampaignMeasurement(
            result_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            value=None,
            value_qualifier=ValueQualifier.EQ,
            unit="nM",
            protocol_name_snapshot="x",
            protocol_version_snapshot=1,
        )


def test_with_hit_call_and_source():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=2,
        hit_call=HitCall.HIT,
        source_run_id=uuid.uuid4(),
        source_curve_id=uuid.uuid4(),
        run_date_snapshot=date(2026, 5, 1),
    )
    assert m.hit_call == HitCall.HIT
    assert m.run_date_snapshot == date(2026, 5, 1)


def test_mark_override_flips_flag():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=10.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.is_manual_override is False
    m.mark_manual_override()
    assert m.is_manual_override is True
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
"""CampaignMeasurement — one frozen cell owned by a CampaignResult."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from chem_vault.domain.research_organization.enums import HitCall, ValueQualifier
from chem_vault.domain.shared.errors import ValidationError


@dataclass
class CampaignMeasurement:
    result_id: uuid.UUID
    channel_id: uuid.UUID
    value: float | None
    value_qualifier: ValueQualifier
    unit: str
    protocol_name_snapshot: str
    protocol_version_snapshot: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    hit_call: HitCall | None = None
    is_manual_override: bool = False
    source_run_id: uuid.UUID | None = None
    source_curve_id: uuid.UUID | None = None
    source_readout_id: uuid.UUID | None = None
    run_date_snapshot: date | None = None

    def __post_init__(self) -> None:
        numeric_qualifiers = {
            ValueQualifier.EQ,
            ValueQualifier.LT,
            ValueQualifier.GT,
        }
        if self.value_qualifier in numeric_qualifiers and self.value is None:
            raise ValidationError(
                f"qualifier {self.value_qualifier.value!r} requires a numeric value"
            )
        if self.value_qualifier in {ValueQualifier.ND, ValueQualifier.EXCLUDED}:
            self.value = None
        if not self.unit or not self.unit.strip():
            raise ValidationError("unit must not be empty")
        self.unit = self.unit.strip()

    def mark_manual_override(self) -> None:
        self.is_manual_override = True
```

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign_measurement.py -v
git add backend/src/chem_vault/domain/research_organization/campaign_measurement.py backend/tests/unit/domain/research_organization/test_campaign_measurement.py
git commit -m "feat(domain): CampaignMeasurement entity"
```

---

### Task 2.5: `CampaignResult` entity

**Files:**
- Create: `backend/src/chem_vault/domain/research_organization/campaign_result.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_result.py`

- [ ] **Step 1: Write failing tests**

```python
import uuid

import pytest

from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    ValueQualifier,
)
from chem_vault.domain.shared.errors import ValidationError


def test_default_decision_deferred():
    r = CampaignResult(
        campaign_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert r.decision == CampaignDecision.DEFERRED
    assert r.measurements == []


def test_add_measurement():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    m = CampaignMeasurement(
        result_id=r.id,
        channel_id=uuid.uuid4(),
        value=1.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    r.add_measurement(m)
    assert len(r.measurements) == 1


def test_set_decision_updates_field():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    r.set_decision(CampaignDecision.SELECTED, reason="Best in series")
    assert r.decision == CampaignDecision.SELECTED
    assert r.decision_reason == "Best in series"


def test_reject_measurement_for_wrong_result():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),  # wrong
        channel_id=uuid.uuid4(),
        value=1.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    with pytest.raises(ValidationError):
        r.add_measurement(m)
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
"""CampaignResult — one snapshot row per compound within a campaign."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import ValidationError


@dataclass
class CampaignResult:
    campaign_id: uuid.UUID
    molecule_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    representative_batch_id: uuid.UUID | None = None
    decision: CampaignDecision = CampaignDecision.DEFERRED
    decision_reason: str | None = None
    notes: str | None = None
    measurements: list[CampaignMeasurement] = field(default_factory=list)

    def add_measurement(self, m: CampaignMeasurement) -> None:
        if m.result_id != self.id:
            raise ValidationError(
                f"CampaignMeasurement.result_id ({m.result_id}) does not match "
                f"CampaignResult.id ({self.id})"
            )
        self.measurements.append(m)

    def remove_measurement_for_channel(self, channel_id: uuid.UUID) -> None:
        self.measurements = [m for m in self.measurements if m.channel_id != channel_id]

    def set_decision(self, decision: CampaignDecision, *, reason: str | None = None) -> None:
        self.decision = decision
        self.decision_reason = reason

    def find_measurement(self, channel_id: uuid.UUID) -> CampaignMeasurement | None:
        for m in self.measurements:
            if m.channel_id == channel_id:
                return m
        return None
```

- [ ] **Step 4: Verify pass + commit**

---

### Task 2.6: `Campaign` aggregate root

**Files:**
- Create: `backend/src/chem_vault/domain/research_organization/campaign.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign.py`

- [ ] **Step 1: Write failing tests** — minimum eight tests covering: create, add_channel, remove_channel, add_result, close_pre_conditions (≥1 result), close transitions, supersede, can't-edit-when-closed. (Use the patterns from `test_collection_frozen.py` and Run aggregate tests.)

Key invariants under test:
- `Campaign.create()` registers a `CampaignCreated` event.
- `add_channel()` rejects after `close()`.
- `close()` requires ≥ 1 `CampaignResult`, transitions to `CLOSED`, sets `closed_at`/`closed_by`/`signature_id`/`source_protocols`, emits `CampaignClosed`.
- `supersede(new_campaign_id)` requires status `CLOSED`, sets `superseded_by_campaign_id`, transitions to `SUPERSEDED`, emits `CampaignSuperseded`.
- All mutating methods on a closed/superseded campaign raise `ValidationError`.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `campaign.py`**

```python
"""Campaign aggregate root — research_organization context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import CompoundSource
from chem_vault.domain.research_organization.enums import CampaignStatus
from chem_vault.domain.research_organization.events import (
    CampaignClosed,
    CampaignCreated,
    CampaignSuperseded,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError


class Campaign(AggregateRoot):
    """A curated, immutable per-compound result snapshot.

    Owned entities: channels, results (and measurements via results).
    Lifecycle: draft → closed → superseded.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str | None = None,
        status: CampaignStatus = CampaignStatus.DRAFT,
        compound_source: CompoundSource,
        publishes_collection: bool = True,
        source_protocols: list[dict[str, Any]] | None = None,
        closed_at: datetime | None = None,
        closed_by: uuid.UUID | None = None,
        signature_id: uuid.UUID | None = None,
        supersedes_campaign_id: uuid.UUID | None = None,
        superseded_by_campaign_id: uuid.UUID | None = None,
        published_collection_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
        channels: list[CampaignChannel] | None = None,
        results: list[CampaignResult] | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Campaign.name must not be empty")
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.name = name.strip()
        self.description = description
        self.status = status
        self.compound_source = compound_source
        self.publishes_collection = publishes_collection
        self.source_protocols = source_protocols or []
        self.closed_at = closed_at
        self.closed_by = closed_by
        self.signature_id = signature_id
        self.supersedes_campaign_id = supersedes_campaign_id
        self.superseded_by_campaign_id = superseded_by_campaign_id
        self.published_collection_id = published_collection_id
        self.created_by = created_by
        self.channels: list[CampaignChannel] = channels or []
        self.results: list[CampaignResult] = results or []

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str | None,
        compound_source: CompoundSource,
        publishes_collection: bool,
        created_by: uuid.UUID,
        supersedes_campaign_id: uuid.UUID | None = None,
    ) -> "Campaign":
        c = cls(
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            description=description,
            compound_source=compound_source,
            publishes_collection=publishes_collection,
            supersedes_campaign_id=supersedes_campaign_id,
            created_by=created_by,
        )
        c.register_event(
            CampaignCreated(
                aggregate_id=c.id,
                aggregate_type="Campaign",
                workspace_id=workspace_id,
                project_id=project_id,
                name=c.name,
            )
        )
        return c

    # ------- mutation guards -------

    def _ensure_draft(self, action: str) -> None:
        if self.status != CampaignStatus.DRAFT:
            raise ValidationError(
                f"Cannot {action}: campaign is {self.status.value}"
            )

    # ------- channels -------

    def add_channel(self, channel: CampaignChannel) -> None:
        self._ensure_draft("add channel")
        if channel.campaign_id != self.id:
            raise ValidationError("channel.campaign_id mismatch")
        if any(c.id == channel.id for c in self.channels):
            raise ValidationError(f"Channel {channel.id} already on campaign")
        self.channels.append(channel)
        self.updated_at = datetime.now(UTC)

    def remove_channel(self, channel_id: uuid.UUID) -> None:
        self._ensure_draft("remove channel")
        self.channels = [c for c in self.channels if c.id != channel_id]
        for r in self.results:
            r.remove_measurement_for_channel(channel_id)
        self.updated_at = datetime.now(UTC)

    # ------- results -------

    def add_result(self, result: CampaignResult) -> None:
        self._ensure_draft("add result")
        if result.campaign_id != self.id:
            raise ValidationError("result.campaign_id mismatch")
        if any(r.molecule_id == result.molecule_id for r in self.results):
            raise ValidationError(
                f"Campaign already contains molecule {result.molecule_id}"
            )
        self.results.append(result)
        self.updated_at = datetime.now(UTC)

    def remove_result_by_molecule(self, molecule_id: uuid.UUID) -> None:
        self._ensure_draft("remove result")
        self.results = [r for r in self.results if r.molecule_id != molecule_id]
        self.updated_at = datetime.now(UTC)

    def reseed_results(self, results: list[CampaignResult]) -> None:
        self._ensure_draft("re-seed")
        for r in results:
            if r.campaign_id != self.id:
                raise ValidationError("result.campaign_id mismatch")
        self.results = list(results)
        self.updated_at = datetime.now(UTC)

    # ------- close / supersede -------

    def close(
        self,
        *,
        closed_by: uuid.UUID,
        signature_id: uuid.UUID,
        source_protocols: list[dict[str, Any]],
    ) -> None:
        self._ensure_draft("close")
        if not self.results:
            raise ValidationError("Cannot close campaign with no results")
        if not self.channels:
            raise ValidationError("Cannot close campaign with no channels")
        self.status = CampaignStatus.CLOSED
        self.closed_at = datetime.now(UTC)
        self.closed_by = closed_by
        self.signature_id = signature_id
        self.source_protocols = source_protocols
        self.updated_at = self.closed_at
        self.register_event(
            CampaignClosed(
                aggregate_id=self.id,
                aggregate_type="Campaign",
                workspace_id=self.workspace_id,
                closed_by=closed_by,
                signature_id=signature_id,
            )
        )

    def set_published_collection(self, collection_id: uuid.UUID) -> None:
        if self.status != CampaignStatus.CLOSED:
            raise ValidationError("Published collection can only be set on closed campaigns")
        self.published_collection_id = collection_id

    def mark_superseded_by(self, new_campaign_id: uuid.UUID) -> None:
        if self.status != CampaignStatus.CLOSED:
            raise ValidationError(
                f"Only closed campaigns can be superseded, status is {self.status.value}"
            )
        self.status = CampaignStatus.SUPERSEDED
        self.superseded_by_campaign_id = new_campaign_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CampaignSuperseded(
                aggregate_id=self.id,
                aggregate_type="Campaign",
                workspace_id=self.workspace_id,
                superseded_by_campaign_id=new_campaign_id,
            )
        )
```

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign.py -v
git add backend/src/chem_vault/domain/research_organization/campaign.py backend/tests/unit/domain/research_organization/test_campaign.py
git commit -m "feat(domain): Campaign aggregate root"
```

---

### Task 2.7: Domain events

**Files:**
- Modify: `backend/src/chem_vault/domain/research_organization/events.py`

Add:

```python
@dataclass(frozen=True)
class CampaignCreated(DomainEvent):
    project_id: uuid.UUID = field(default=None)  # type: ignore[assignment]
    workspace_id: uuid.UUID = field(default=None)  # type: ignore[assignment]
    name: str = ""


@dataclass(frozen=True)
class CampaignClosed(DomainEvent):
    workspace_id: uuid.UUID = field(default=None)  # type: ignore[assignment]
    closed_by: uuid.UUID = field(default=None)  # type: ignore[assignment]
    signature_id: uuid.UUID = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class CampaignSuperseded(DomainEvent):
    workspace_id: uuid.UUID = field(default=None)  # type: ignore[assignment]
    superseded_by_campaign_id: uuid.UUID = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class CampaignPublishedCollectionCreated(DomainEvent):
    workspace_id: uuid.UUID = field(default=None)  # type: ignore[assignment]
    collection_id: uuid.UUID = field(default=None)  # type: ignore[assignment]
```

Match the existing event class style (mirror `CollectionCreated`). Commit alongside Task 2.6 if possible:

```bash
git add backend/src/chem_vault/domain/research_organization/events.py
git commit -m "feat(domain): Campaign domain events"
```

---

### Task 2.8: `CampaignLockGuard`

**Files:**
- Create: `backend/src/chem_vault/domain/research_organization/campaign_lock_guard.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_lock_guard.py`

- [ ] **Step 1: Write failing tests** — mirror `test_data_lock_guard.py`. Use a fake `CampaignLockChecker` returning True/False.

- [ ] **Step 2: Implement** (copy `DataLockGuard` structure, swap "Run" for "Campaign"):

```python
"""CampaignLockGuard — prevents writes to closed/superseded campaigns."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from chem_vault.domain.shared.errors import DataLockedError


@runtime_checkable
class CampaignLockChecker(Protocol):
    async def is_locked(self, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> bool: ...


class CampaignLockGuard:
    def __init__(self, lock_checker: CampaignLockChecker) -> None:
        self._checker = lock_checker

    async def guard_write(self, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> None:
        if await self._checker.is_locked(workspace_id, campaign_id):
            raise DataLockedError(
                f"Campaign '{campaign_id}' is closed or superseded — modifications not allowed"
            )
```

- [ ] **Step 3: Verify pass + commit**

---

### Task 2.9: `CampaignRepository` Protocol

**Files:**
- Modify: `backend/src/chem_vault/domain/research_organization/repository.py`

Append:

```python
@runtime_checkable
class CampaignRepository(Protocol):
    async def find_by_id(self, id: uuid.UUID) -> Campaign | None: ...
    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Campaign | None: ...
    async def save(self, aggregate: Campaign) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
    async def find_by_project(
        self, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[Campaign]: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[Campaign]: ...
    async def is_locked(
        self, workspace_id: uuid.UUID, campaign_id: uuid.UUID
    ) -> bool: ...
    # paginated results read for large campaigns
    async def find_results_paginated(
        self,
        workspace_id: uuid.UUID,
        campaign_id: uuid.UUID,
        *,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> tuple[list[CampaignResult], str | None]: ...
```

Don't forget the new `Campaign`, `CampaignResult` imports.

Commit:

```bash
git add backend/src/chem_vault/domain/research_organization/repository.py
git commit -m "feat(domain): CampaignRepository protocol"
```

---

## Phase 3 — Persistence (SA models, migration, repository)

### Task 3.1: SQLAlchemy models for campaign tables

**Files:**
- Modify: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/models.py`

Add four ORM models:

```python
class CampaignModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "campaign"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    compound_source: Mapped[dict] = mapped_column(JSONB, nullable=False)
    publishes_collection: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source_protocols: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    signature_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    supersedes_campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    superseded_by_campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    published_collection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    channels: Mapped[list["CampaignChannelModel"]] = relationship(
        "CampaignChannelModel",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CampaignChannelModel.display_order",
    )
    results: Mapped[list["CampaignResultModel"]] = relationship(
        "CampaignResultModel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_campaign_workspace_project", "workspace_id", "project_id"),
    )


class CampaignChannelModel(Base, EntityModelMixin):
    __tablename__ = "campaign_channel"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    protocol_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    readout_definition_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_rule: Mapped[str] = mapped_column(String(32), nullable=False)
    qualifier_handling: Mapped[str] = mapped_column(String(32), nullable=False)
    qc_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hit_threshold: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CampaignResultModel(Base, EntityModelMixin):
    __tablename__ = "campaign_result"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    molecule_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    representative_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="deferred")
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    measurements: Mapped[list["CampaignMeasurementModel"]] = relationship(
        "CampaignMeasurementModel",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("uq_campaign_result_molecule", "campaign_id", "molecule_id", unique=True),
    )


class CampaignMeasurementModel(Base, EntityModelMixin):
    __tablename__ = "campaign_measurement"

    result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign_result.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("campaign_channel.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_qualifier: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    hit_call: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    source_curve_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source_readout_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    protocol_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    protocol_version_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    run_date_snapshot: Mapped[Date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("uq_campaign_measurement_result_channel", "result_id", "channel_id", unique=True),
    )
```

(Imports: `JSONB`, `Float`, `Integer`, `Boolean`, `Text`, `Date`, `ForeignKey`, `Index`, `Uuid`, `text`, `mapped_column`, `Mapped`, `relationship` — from the existing model module's imports.)

Commit later, with the migration.

---

### Task 3.2: Alembic migration `027_screen_campaign`

**Files:**
- Create: `backend/alembic/versions/027_screen_campaign.py`

- [ ] **Step 1: Generate scaffold + rename**

```bash
cd backend && uv run alembic revision -m "screen campaign"
mv backend/alembic/versions/<generated>_screen_campaign.py backend/alembic/versions/027_screen_campaign.py
```

Set `revision = "027_screen_campaign"`, `down_revision = "026_collection_frozen"`.

- [ ] **Step 2: Write `upgrade()` / `downgrade()`**

Create tables: `campaign`, `campaign_channel`, `campaign_result`, `campaign_measurement` — column-for-column matching Task 3.1, plus the defense-in-depth PG trigger:

```python
def upgrade() -> None:
    op.create_table(
        "campaign",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("compound_source", postgresql.JSONB(), nullable=False),
        sa.Column("publishes_collection", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_protocols", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("signature_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("supersedes_campaign_id", sa.Uuid(as_uuid=True), nullable=True, index=True),
        sa.Column("superseded_by_campaign_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("published_collection_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_campaign_workspace_project", "campaign", ["workspace_id", "project_id"])

    op.create_table(
        "campaign_channel",
        # ... mirror CampaignChannelModel
    )
    op.create_table(
        "campaign_result",
        # ... mirror CampaignResultModel — include UNIQUE on (campaign_id, molecule_id)
    )
    op.create_table(
        "campaign_measurement",
        # ... mirror CampaignMeasurementModel — include UNIQUE on (result_id, channel_id)
    )

    # Defense-in-depth: PG triggers preventing writes when campaign is locked
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_locked_campaign_write() RETURNS trigger AS $$
        DECLARE
            cstat text;
        BEGIN
            IF TG_TABLE_NAME = 'campaign_result' THEN
                SELECT status INTO cstat FROM campaign WHERE id = COALESCE(NEW.campaign_id, OLD.campaign_id);
            ELSIF TG_TABLE_NAME = 'campaign_measurement' THEN
                SELECT c.status INTO cstat
                  FROM campaign_result r
                  JOIN campaign c ON c.id = r.campaign_id
                 WHERE r.id = COALESCE(NEW.result_id, OLD.result_id);
            END IF;
            IF cstat IN ('closed', 'superseded') THEN
                RAISE EXCEPTION 'Campaign is % — writes blocked', cstat USING ERRCODE = 'check_violation';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
    """)

    for tbl in ("campaign_result", "campaign_measurement"):
        op.execute(f"""
            CREATE TRIGGER {tbl}_reject_locked
            BEFORE INSERT OR UPDATE OR DELETE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION reject_locked_campaign_write();
        """)


def downgrade() -> None:
    for tbl in ("campaign_measurement", "campaign_result"):
        op.execute(f"DROP TRIGGER IF EXISTS {tbl}_reject_locked ON {tbl}")
    op.execute("DROP FUNCTION IF EXISTS reject_locked_campaign_write")
    op.drop_table("campaign_measurement")
    op.drop_table("campaign_result")
    op.drop_table("campaign_channel")
    op.drop_table("campaign")
```

- [ ] **Step 3: Apply locally + run a smoke test**

```bash
cd backend && uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: clean up-and-down.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/027_screen_campaign.py backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/models.py
git commit -m "feat(db): screen campaign tables + lock trigger"
```

---

### Task 3.3: `SQLAlchemyCampaignRepository`

**Files:**
- Create: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py`
- Test: `backend/tests/integration/research_organization/test_campaign_repository.py`

- [ ] **Step 1: Write failing integration tests** covering: save+load round-trip with channels + results + measurements, optimistic concurrency conflict (`version` mismatch), `is_locked` returns True for closed campaigns, deleting cascades children, `find_by_project` returns ordered list.

```python
@pytest.mark.asyncio
async def test_save_and_load_roundtrip(uow_factory, campaign_repo, sample_campaign):
    async with uow_factory() as uow:
        await campaign_repo.save(sample_campaign)
        await uow.commit()
    reloaded = await campaign_repo.find_by_id(sample_campaign.id)
    assert reloaded is not None
    assert reloaded.name == sample_campaign.name
    assert len(reloaded.channels) == len(sample_campaign.channels)
    assert len(reloaded.results) == len(sample_campaign.results)


@pytest.mark.asyncio
async def test_optimistic_concurrency(uow_factory, campaign_repo, sample_campaign):
    async with uow_factory() as uow:
        await campaign_repo.save(sample_campaign)
        await uow.commit()
    a = await campaign_repo.find_by_id(sample_campaign.id)
    b = await campaign_repo.find_by_id(sample_campaign.id)
    a.name = "renamed-a"
    async with uow_factory() as uow:
        await campaign_repo.save(a)
        await uow.commit()
    b.name = "renamed-b"
    with pytest.raises(ConcurrencyConflictError):
        async with uow_factory() as uow:
            await campaign_repo.save(b)
            await uow.commit()


@pytest.mark.asyncio
async def test_is_locked_returns_true_for_closed(uow_factory, campaign_repo, closed_campaign):
    locked = await campaign_repo.is_locked(closed_campaign.workspace_id, closed_campaign.id)
    assert locked is True
```

- [ ] **Step 2: Implement the repository**

Follow `SQLAlchemyCollectionRepository` shape: subclass `SQLAlchemyRepository[Campaign, CampaignModel]`, implement `_to_domain`, `_to_model`, `_update_model`. Children (channels/results/measurements) are handled via in-place list reconciliation (build a dict by id, update in place, add new, delete missing) — match how the existing aggregates with owned children (e.g., `Protocol` + `ReadoutDefinition`) do it. Reference: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py`.

Add `is_locked` and `find_results_paginated`:

```python
    async def is_locked(self, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> bool:
        stmt = select(CampaignModel.status).where(
            CampaignModel.id == campaign_id,
            CampaignModel.workspace_id == workspace_id,
        )
        async with self._session_factory() as session:
            status = await session.scalar(stmt)
        return status in ("closed", "superseded")
```

- [ ] **Step 3: Run tests, verify pass, commit**

```bash
cd backend && uv run pytest tests/integration/research_organization/test_campaign_repository.py -v
git add backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py backend/tests/integration/research_organization/test_campaign_repository.py
git commit -m "feat(persistence): SQLAlchemyCampaignRepository"
```

---

## Phase 4 — Channel resolution engine

### Task 4.1: `ChannelResolutionQuery` Protocol + `ChannelResolver`

**Files:**
- Create: `backend/src/chem_vault/application/research_organization/channel_resolution.py`
- Test: `backend/tests/unit/application/research_organization/test_channel_resolver.py`

The Protocol is the port; the resolver is the pure domain-service-style aggregator that turns a candidate list into a `CampaignMeasurement`.

- [ ] **Step 1: Write unit tests using a fake query**

```python
import uuid

import pytest

from chem_vault.application.research_organization.channel_resolution import (
    ChannelResolutionQuery,
    ChannelResolver,
    ResolvedCandidate,
)
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion


class FakeQuery:
    def __init__(self, candidates):
        self._c = candidates

    async def fetch_candidates(self, *, workspace_id, channel, molecule_id):
        return self._c


def _make_channel(rule, threshold=None, qc=None) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=rule,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter=qc,
        hit_threshold=threshold,
    )


@pytest.mark.asyncio
async def test_latest_approved_run_picks_highest_run_date():
    ch = _make_channel(SelectionRule.LATEST_APPROVED_RUN)
    candidates = [
        ResolvedCandidate(value=10.0, qualifier=ValueQualifier.EQ, unit="nM",
                          run_id=uuid.uuid4(), run_date=date(2026, 5, 1),
                          run_approved=True, z_prime=0.7,
                          protocol_name="X", protocol_version=1,
                          curve_id=uuid.uuid4(), readout_id=None),
        ResolvedCandidate(value=20.0, qualifier=ValueQualifier.EQ, unit="nM",
                          run_id=uuid.uuid4(), run_date=date(2026, 4, 1),
                          run_approved=True, z_prime=0.7,
                          protocol_name="X", protocol_version=1,
                          curve_id=uuid.uuid4(), readout_id=None),
    ]
    resolver = ChannelResolver(FakeQuery(candidates))
    m = await resolver.resolve(workspace_id=uuid.uuid4(), channel=ch,
                                result_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    assert m.value == 10.0  # the May date


@pytest.mark.asyncio
async def test_mean_across_runs_averages_values():
    ch = _make_channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        ResolvedCandidate(value=10.0, qualifier=ValueQualifier.EQ, unit="nM",
                          run_id=uuid.uuid4(), run_date=None, run_approved=True,
                          z_prime=0.7, protocol_name="X", protocol_version=1,
                          curve_id=None, readout_id=uuid.uuid4()),
        ResolvedCandidate(value=20.0, qualifier=ValueQualifier.EQ, unit="nM",
                          run_id=uuid.uuid4(), run_date=None, run_approved=True,
                          z_prime=0.7, protocol_name="X", protocol_version=1,
                          curve_id=None, readout_id=uuid.uuid4()),
    ]
    resolver = ChannelResolver(FakeQuery(candidates))
    m = await resolver.resolve(workspace_id=uuid.uuid4(), channel=ch,
                                result_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    assert m.value == 15.0


@pytest.mark.asyncio
async def test_no_candidates_yields_nd_qualifier():
    ch = _make_channel(SelectionRule.LATEST_APPROVED_RUN)
    resolver = ChannelResolver(FakeQuery([]))
    m = await resolver.resolve(workspace_id=uuid.uuid4(), channel=ch,
                                result_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    assert m.hit_call is None


@pytest.mark.asyncio
async def test_hit_threshold_computes_hit_call():
    ch = _make_channel(
        SelectionRule.LATEST_APPROVED_RUN,
        threshold=HitCriterion(readout_name="IC50", operator="lt", value=1000.0),
    )
    candidates = [
        ResolvedCandidate(value=42.0, qualifier=ValueQualifier.EQ, unit="nM",
                          run_id=uuid.uuid4(), run_date=date(2026, 5, 1),
                          run_approved=True, z_prime=0.7,
                          protocol_name="X", protocol_version=1,
                          curve_id=uuid.uuid4(), readout_id=None),
    ]
    resolver = ChannelResolver(FakeQuery(candidates))
    m = await resolver.resolve(workspace_id=uuid.uuid4(), channel=ch,
                                result_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    assert m.hit_call == HitCall.HIT


@pytest.mark.asyncio
async def test_qc_filter_drops_low_z_prime():
    ch = _make_channel(
        SelectionRule.LATEST_APPROVED_RUN,
        qc={"min_z_prime": 0.5, "require_approved": True},
    )
    candidates = [
        ResolvedCandidate(value=99.0, qualifier=ValueQualifier.EQ, unit="nM",
                          run_id=uuid.uuid4(), run_date=date(2026, 5, 1),
                          run_approved=True, z_prime=0.3,  # failing
                          protocol_name="X", protocol_version=1,
                          curve_id=uuid.uuid4(), readout_id=None),
    ]
    resolver = ChannelResolver(FakeQuery(candidates))
    m = await resolver.resolve(workspace_id=uuid.uuid4(), channel=ch,
                                result_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    assert m.value_qualifier == ValueQualifier.ND
```

Plus an analogous geometric_mean test and a qualifier_handling=exclude_qualified test.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `channel_resolution.py`**

```python
"""Channel resolution — turns source candidates into a CampaignMeasurement."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.enums import (
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion


@dataclass(frozen=True)
class ResolvedCandidate:
    value: float
    qualifier: ValueQualifier
    unit: str
    run_id: uuid.UUID
    run_date: date | None
    run_approved: bool
    z_prime: float | None
    protocol_name: str
    protocol_version: int
    curve_id: uuid.UUID | None
    readout_id: uuid.UUID | None


@runtime_checkable
class ChannelResolutionQuery(Protocol):
    async def fetch_candidates(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
    ) -> list[ResolvedCandidate]: ...


def _passes_qc(c: ResolvedCandidate, qc: dict | None) -> bool:
    if not qc:
        return True
    if qc.get("require_approved", False) and not c.run_approved:
        return False
    min_z = qc.get("min_z_prime")
    if min_z is not None and (c.z_prime is None or c.z_prime < min_z):
        return False
    return True


def _drop_qualified(c: ResolvedCandidate) -> bool:
    return c.qualifier in {ValueQualifier.LT, ValueQualifier.GT}


def _compute_hit_call(value: float | None, threshold: HitCriterion | None) -> HitCall | None:
    if value is None or threshold is None:
        return None
    op = threshold.operator
    target = threshold.value
    if isinstance(target, list):
        return None  # 'in' operator: not applicable to numeric cell
    if op == "lt":
        return HitCall.HIT if value < target else HitCall.MISS
    if op == "lte":
        return HitCall.HIT if value <= target else HitCall.MISS
    if op == "gt":
        return HitCall.HIT if value > target else HitCall.MISS
    if op == "gte":
        return HitCall.HIT if value >= target else HitCall.MISS
    return None


class ChannelResolver:
    def __init__(self, query: ChannelResolutionQuery) -> None:
        self._q = query

    async def resolve(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        result_id: uuid.UUID,
        molecule_id: uuid.UUID,
    ) -> CampaignMeasurement:
        candidates = await self._q.fetch_candidates(
            workspace_id=workspace_id, channel=channel, molecule_id=molecule_id
        )
        # Apply QC filter
        candidates = [c for c in candidates if _passes_qc(c, channel.qc_filter)]
        # Apply qualifier handling
        if channel.qualifier_handling == QualifierHandling.EXCLUDE_QUALIFIED:
            candidates = [c for c in candidates if not _drop_qualified(c)]
        # If empty → ND
        if not candidates:
            return CampaignMeasurement(
                result_id=result_id,
                channel_id=channel.id,
                value=None,
                value_qualifier=ValueQualifier.ND,
                unit=self._unit_fallback(channel, candidates),
                protocol_name_snapshot="",
                protocol_version_snapshot=0,
                hit_call=None,
            )

        unit = candidates[0].unit
        if channel.selection_rule == SelectionRule.LATEST_APPROVED_RUN:
            pick = max(candidates, key=lambda c: c.run_date or date.min)
            value, qualifier = pick.value, pick.qualifier
            source_run, curve, readout = pick.run_id, pick.curve_id, pick.readout_id
            pname, pver, rdate = pick.protocol_name, pick.protocol_version, pick.run_date
        elif channel.selection_rule == SelectionRule.MEAN_ACROSS_RUNS:
            vals = [c.value for c in candidates]
            value = sum(vals) / len(vals)
            qualifier = ValueQualifier.EQ
            source_run = curve = readout = None
            pname = candidates[0].protocol_name
            pver = candidates[0].protocol_version
            rdate = None
        elif channel.selection_rule == SelectionRule.GEOMETRIC_MEAN:
            vals = [c.value for c in candidates if c.value > 0]
            value = math.exp(sum(math.log(v) for v in vals) / len(vals))
            qualifier = ValueQualifier.EQ
            source_run = curve = readout = None
            pname = candidates[0].protocol_name
            pver = candidates[0].protocol_version
            rdate = None
        else:  # MANUAL_PICK — left as ND until user picks
            return CampaignMeasurement(
                result_id=result_id,
                channel_id=channel.id,
                value=None,
                value_qualifier=ValueQualifier.ND,
                unit=unit,
                protocol_name_snapshot=candidates[0].protocol_name,
                protocol_version_snapshot=candidates[0].protocol_version,
                hit_call=None,
            )

        return CampaignMeasurement(
            result_id=result_id,
            channel_id=channel.id,
            value=value,
            value_qualifier=qualifier,
            unit=unit,
            hit_call=_compute_hit_call(value, channel.hit_threshold),
            source_run_id=source_run,
            source_curve_id=curve,
            source_readout_id=readout,
            protocol_name_snapshot=pname,
            protocol_version_snapshot=pver,
            run_date_snapshot=rdate,
        )

    @staticmethod
    def _unit_fallback(channel: CampaignChannel, candidates: list[ResolvedCandidate]) -> str:
        if candidates:
            return candidates[0].unit
        return ""  # ND cells with no candidates carry empty unit, set by caller from readout def
```

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/unit/application/research_organization/test_channel_resolver.py -v
git add backend/src/chem_vault/application/research_organization/channel_resolution.py backend/tests/unit/application/research_organization/test_channel_resolver.py
git commit -m "feat(application): channel resolution service"
```

---

### Task 4.2: SQL implementation of `ChannelResolutionQuery`

**Files:**
- Create: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/channel_resolution_query.py`
- Test: `backend/tests/integration/research_organization/test_channel_resolution_query.py`

- [ ] **Step 1: Integration test** — seed a real `Run` (approved), `ReadoutData` row, `DoseResponseCurve` row, and assert the query returns the expected `ResolvedCandidate` list with QC metrics from the run.

- [ ] **Step 2: Implement**

```python
class SQLAlchemyChannelResolutionQuery:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def fetch_candidates(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
    ) -> list[ResolvedCandidate]:
        if channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
            stmt = (
                select(
                    DoseResponseCurveModel,
                    RunModel.run_date,
                    RunModel.status,
                    RunModel.qc_metrics,
                    ProtocolModel.name,
                    ProtocolModel.version,
                )
                .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
                .join(ProtocolModel, DoseResponseCurveModel.protocol_id == ProtocolModel.id)
                .where(
                    DoseResponseCurveModel.workspace_id == workspace_id,
                    DoseResponseCurveModel.molecule_id == molecule_id,
                    DoseResponseCurveModel.protocol_id == channel.protocol_id,
                )
            )
        else:
            stmt = (
                select(
                    ReadoutDataModel,
                    RunModel.run_date,
                    RunModel.status,
                    RunModel.qc_metrics,
                    ProtocolModel.name,
                    ProtocolModel.version,
                )
                .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
                .join(ProtocolModel, RunModel.protocol_id == ProtocolModel.id)
                .where(
                    ReadoutDataModel.workspace_id == workspace_id,
                    ReadoutDataModel.molecule_id == molecule_id,
                    ReadoutDataModel.readout_definition_id == channel.readout_definition_id,
                )
            )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()

        results: list[ResolvedCandidate] = []
        for row in rows:
            # ... build ResolvedCandidate, extracting z_prime from qc_metrics jsonb
            ...
        return results
```

- [ ] **Step 3: Verify + commit**

```bash
cd backend && uv run pytest tests/integration/research_organization/test_channel_resolution_query.py -v
git add backend/src/chem_vault/infrastructure/persistence/sqlalchemy/research_organization/channel_resolution_query.py backend/tests/integration/research_organization/test_channel_resolution_query.py
git commit -m "feat(persistence): SQL impl of channel resolution query"
```

---

## Phase 5 — Application use cases

For each use case below, follow the existing pattern (`Command` frozen dataclass → `UseCase` Protocol → concrete class returning `Result[T, DomainError]`, depends on `UnitOfWork` + repo + Sentinel auth context). Reference: `backend/src/chem_vault/application/research_organization/create_collection.py`.

Each use-case task structure is identical and shortened here. Per task:
1. Write failing unit test (`tests/unit/application/research_organization/test_<usecase>.py`) using `FakeAuth` + `FakeUnitOfWork` + an in-memory `CampaignRepository`.
2. Run, expect FAIL.
3. Implement.
4. Run, expect PASS.
5. Commit.

### Task 5.1: `CreateCampaign` (with compound source seeding)

Wires:
- `CampaignRepository`, `CollectionRepository` (to read membership for `CollectionSource`), `SavedSearchRepository` + `ExecuteSavedSearch`, sibling `Campaign` lookup for `DerivedFromCampaignSource`.
- Resolves compound_source → list of molecule_ids → builds `CampaignResult` per molecule (no measurements yet).
- Requires `require_editor()`.

Command:

```python
@dataclass(frozen=True)
class CreateCampaignCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    compound_source: CompoundSource
    publishes_collection: bool
    created_by: uuid.UUID
    supersedes_campaign_id: uuid.UUID | None
```

Returns `Result[Campaign, DomainError]`.

Commit: `feat(application): create campaign use case`.

---

### Task 5.2: `ManageCampaignChannels` — add / update / remove

Three commands:

```python
@dataclass(frozen=True)
class AddCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: ChannelSourceKind
    selection_rule: SelectionRule
    qualifier_handling: QualifierHandling
    qc_filter: dict | None
    hit_threshold: HitCriterion | None  # if None, attempt carry-forward from protocol
    display_order: int

@dataclass(frozen=True)
class UpdateCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    channel_id: uuid.UUID
    # nullable sentinels for partial updates
    label: str | None
    selection_rule: SelectionRule | None
    qc_filter: dict | object  # sentinel UNSET for "don't change"
    hit_threshold: HitCriterion | None | object

@dataclass(frozen=True)
class RemoveCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    channel_id: uuid.UUID
```

Add-channel logic:
1. `_ensure_draft` via aggregate.
2. If `hit_threshold is None`: read Protocol → ReadoutDefinition for `(protocol_id, readout_definition_id)`; if it carries a HitCriterion, attach it as the suggested threshold. (Carry-forward.)
3. Append channel; for every existing `CampaignResult` resolve a measurement via `ChannelResolver`.

Update-channel logic: if `selection_rule`, `qc_filter`, or `hit_threshold` changed, re-resolve measurements **only** where `is_manual_override == False`.

Remove-channel logic: aggregate handles it (drops measurements for that channel).

Three commits: `feat(application): add campaign channel`, `update`, `remove`.

---

### Task 5.3: `ReseedCampaign`

Destructive: resolves new `compound_source` to molecule_ids → builds new `CampaignResult` list → calls `campaign.reseed_results(...)` → for each existing channel, resolve measurements. Returns updated campaign.

Command:

```python
@dataclass(frozen=True)
class ReseedCampaignCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    new_source: CompoundSource
```

Commit: `feat(application): reseed campaign`.

---

### Task 5.4: `ManageCampaignResults` — set decision, override cell, add/remove row

Four commands; each is a small use case. Override-cell calls `result.find_measurement(channel_id)`, replaces the value, calls `m.mark_manual_override()`. Add-row builds a `CampaignResult`, resolves measurements for every existing channel.

Commit: `feat(application): manage campaign results`.

---

### Task 5.5: `RefreshFromSources` and `RecomputeChannel`

`RefreshFromSources(campaign_id)` — re-resolves every cell with `is_manual_override == False`, leaves overrides alone.

`RecomputeChannel(campaign_id, channel_id)` — same but scoped to one channel.

Commit: `feat(application): refresh campaign from sources`.

---

### Task 5.6: `CloseCampaign`

> **NOTE:** When calling `collection_repo.add_molecules` immediately after `collection_repo.save(new_collection)`, ensure the session has flushed (the existing `_session()` context manager already flushes on commit; if you're inside one UoW, no extra step needed — but verify). Otherwise the SELECT inside the frozen-guard may not see the just-saved row and will raise `NotFoundError`.

**Files:**
- Create: `backend/src/chem_vault/application/research_organization/close_campaign.py`
- Test: `backend/tests/integration/application/research_organization/test_close_campaign.py`

- [ ] Write integration test: closes a draft campaign with 1 channel + 2 results + measurements; asserts `status == CLOSED`, `source_protocols` materialized, `published_collection_id` set, derived `Collection` created with `is_frozen=True`, `decision == "selected"` molecules present, no `decision == "rejected"` molecules in the membership; verify `CampaignClosed` event dispatched.

- [ ] Implement:

```python
class CloseCampaign:
    def __init__(self, uow, campaign_repo, collection_repo, protocol_repo,
                 signature_service, auth_guards, dispatcher) -> None:
        ...

    async def __call__(self, cmd: CloseCampaignCommand) -> Result[Campaign, DomainError]:
        async with self._uow as uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(...)
            if campaign is None:
                return Failure(NotFoundError(...))
            # 1. Pre-conditions enforced by Campaign.close (≥1 result, channels exist)
            # 2. Capture e-signature
            sig = await self._signature_service.capture(...)
            # 3. Re-resolve cells with is_manual_override = False
            #    (using resolver injected here)
            # 4. Materialize source_protocols snapshot
            distinct = {ch.protocol_id for ch in campaign.channels}
            protos = await self._protocol_repo.find_by_ids(list(distinct))
            source_protocols = [{
                "id": str(p.id),
                "name": p.name,
                "version": p.version,
                "target_id": str(p.target_id) if p.target_id else None,
                "target_name": ...,
            } for p in protos]
            # 5. Close
            campaign.close(closed_by=cmd.user_id, signature_id=sig.id,
                           source_protocols=source_protocols)
            # 6. Optionally publish frozen Collection
            if campaign.publishes_collection:
                selected_mol_ids = [r.molecule_id for r in campaign.results
                                    if r.decision == CampaignDecision.SELECTED]
                coll = Collection.create(
                    workspace_id=campaign.workspace_id,
                    name=f"Hits — {campaign.name}",
                    description=f"Frozen output of campaign {campaign.id}",
                    project_id=campaign.project_id,
                    created_by=cmd.user_id,
                )
                coll.freeze(derived_from_campaign_id=campaign.id)
                await self._collection_repo.save(coll)
                await self._collection_repo.add_molecules(
                    campaign.workspace_id, coll.id, selected_mol_ids
                )
                campaign.set_published_collection(coll.id)
                campaign.register_event(CampaignPublishedCollectionCreated(
                    aggregate_id=campaign.id,
                    aggregate_type="Campaign",
                    workspace_id=campaign.workspace_id,
                    collection_id=coll.id,
                ))
            await self._campaign_repo.save(campaign)
            events = await uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
```

Commit: `feat(application): close campaign + publish frozen collection`.

---

### Task 5.7: `SupersedeCampaign`

Wraps two campaigns in one UoW: looks up old, ensures status CLOSED, calls `old.mark_superseded_by(new_id)`. New campaign was already created via `CreateCampaign` with `supersedes_campaign_id` set.

Commit: `feat(application): supersede campaign`.

---

### Task 5.8: `GetPublishedCampaign`

Query (not command). Loads campaign + project + creator + sig + channels + results + measurements; serializes to the exact JSON shape in spec §6. Returns paginated result envelope when `len(results) > page_size`.

Commit: `feat(application): published campaign query`.

---

## Phase 6 — API routes

### Task 6.1: `interface/routes/campaigns.py`

**Files:**
- Create: `backend/src/chem_vault/interface/routes/campaigns.py`
- Modify: `backend/src/chem_vault/interface/app.py` (register router)
- Modify: `backend/src/chem_vault/interface/dependencies.py` (add `CampaignRepoDep` + use-case factories)
- Modify: `backend/src/chem_vault/infrastructure/di/container.py` (wire `CampaignRepository`, `ChannelResolver`, `CampaignLockGuard`)
- Test: `backend/tests/api/test_campaigns_api.py`

Endpoints:

```
POST   /api/v1/campaigns                                  → CreateCampaign
GET    /api/v1/campaigns?project_id=&workspace          → list
GET    /api/v1/campaigns/{id}                             → full draft view
PATCH  /api/v1/campaigns/{id}                             → name/desc/source
POST   /api/v1/campaigns/{id}/reseed                      → ReseedCampaign
POST   /api/v1/campaigns/{id}/channels                    → AddCampaignChannel
PATCH  /api/v1/campaigns/{id}/channels/{channel_id}       → UpdateCampaignChannel
DELETE /api/v1/campaigns/{id}/channels/{channel_id}       → RemoveCampaignChannel
PATCH  /api/v1/campaigns/{id}/results/{result_id}         → set decision
PATCH  /api/v1/campaigns/{id}/results/{result_id}/cells/{channel_id}  → override cell
POST   /api/v1/campaigns/{id}/results                     → add row by molecule_id
DELETE /api/v1/campaigns/{id}/results/{result_id}         → exclude row
POST   /api/v1/campaigns/{id}/refresh                     → RefreshFromSources
POST   /api/v1/campaigns/{id}/close                       → CloseCampaign
POST   /api/v1/campaigns/{id}/supersede                   → SupersedeCampaign
GET    /api/v1/campaigns/{id}/published                   → GetPublishedCampaign (DAIKON contract)
```

- [ ] **Step 1: API integration tests** — at minimum:
  - Auth required (401 without token).
  - Create draft → response is 201, returns campaign DTO with channels=[] and results based on source.
  - Add channel → 200, returns updated channel + recomputed measurement count.
  - Close empty campaign → 422 (no results).
  - Close valid campaign → 200, status=closed, published_collection_id set.
  - PATCH after close → 423 (`DataLockedError` → Locked).
  - GET /published returns spec-compliant shape (use a small JSON schema fixture).

- [ ] **Step 2: Pydantic request/response models** — mirror `interface/routes/collections.py`. `CampaignResponse.from_domain(campaign)` builds the DTO.

- [ ] **Step 3: Container wiring**

In `container.py`:

```python
    container[CampaignRepository] = lambda c: SQLAlchemyCampaignRepository(
        session_factory=c[async_sessionmaker[AsyncSession]],
        unit_of_work=c[AsyncUnitOfWork],
    )
    container[ChannelResolutionQuery] = lambda c: SQLAlchemyChannelResolutionQuery(
        session_factory=c[async_sessionmaker[AsyncSession]],
    )
    container[ChannelResolver] = lambda c: ChannelResolver(c[ChannelResolutionQuery])
    container[CampaignLockGuard] = lambda c: CampaignLockGuard(c[CampaignRepository])
    # Use cases: CreateCampaign, AddCampaignChannel, ..., CloseCampaign, GetPublishedCampaign
```

`CampaignRepository` satisfies `CampaignLockChecker` because it has `is_locked` — structural subtyping handles it.

- [ ] **Step 4: Verify pass + commit**

```bash
cd backend && uv run pytest tests/api/test_campaigns_api.py -v
git add backend/src/chem_vault/interface/routes/campaigns.py backend/src/chem_vault/interface/app.py backend/src/chem_vault/interface/dependencies.py backend/src/chem_vault/infrastructure/di/container.py backend/tests/api/test_campaigns_api.py
git commit -m "feat(api): screen campaign endpoints"
```

---

### Task 6.2: DAIKON published JSON contract test

**Files:**
- Create: `backend/tests/api/test_campaign_published_contract.py`
- Create: `backend/tests/api/fixtures/daikon_contract.schema.json` — JSON Schema (Draft 7) capturing the spec §6 shape

- [ ] **Step 1: Author the JSON Schema** — covers top-level fields + `results[].measurements[]` schema.

- [ ] **Step 2: Test**

```python
import json

import jsonschema
import pytest


@pytest.mark.asyncio
async def test_published_endpoint_matches_daikon_schema(client, closed_campaign, schema):
    resp = await client.get(f"/api/v1/campaigns/{closed_campaign.id}/published")
    assert resp.status_code == 200
    jsonschema.validate(resp.json(), schema)
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_campaign_published_contract.py backend/tests/api/fixtures/daikon_contract.schema.json
git commit -m "test(api): DAIKON published-contract schema validation"
```

---

## Phase 7 — Frontend foundation

### Task 7.1: Regenerate orval types

**Files:**
- Modify: `frontend/src/shared/lib/api/generated/` (auto-generated)
- Modify: `frontend/orval.config.ts` (if any patterns excluded)

- [ ] Run from `frontend/`:

```bash
pnpm orval
```

Confirm new `campaigns` API client is generated (paginated `published` endpoint represented). Commit the diff:

```bash
git add frontend/src/shared/lib/api/generated/
git commit -m "chore(api): regenerate orval client for campaigns"
```

---

### Task 7.2: Feature folder scaffold

**Files:**
- Create: `frontend/src/features/screen-campaign/types/index.ts`
- Create: `frontend/src/features/screen-campaign/lib/api.ts`
- Create: `frontend/src/features/screen-campaign/lib/hooks.ts` (TanStack Query wrappers)

Re-export orval-generated types into a feature-local namespace, keep view models small.

```typescript
export type {
  Campaign,
  CampaignChannel,
  CampaignResult,
  CampaignMeasurement,
  CampaignStatus,
  SelectionRule,
  ChannelSourceKind,
  CampaignDecision,
  HitCall,
  ValueQualifier,
} from "@/shared/lib/api/generated";

export type ChannelEditDraft = Partial<CampaignChannel> & { isNew?: boolean };
```

Commit: `feat(fe): screen-campaign feature scaffold`.

---

### Task 7.3: Campaign list page (per project)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-list.tsx`
- Create: `frontend/src/app/(dashboard)/projects/[projectId]/campaigns/page.tsx`

- [ ] Use TanStack `useQuery` against `GET /api/v1/campaigns?project_id=...`.
- [ ] Table columns: name (link), status (chip), channels count, results count, closed_at, supersedes/superseded-by chips.
- [ ] Empty state with "Create campaign" CTA → opens a dialog at `<CreateCampaignDialog />` (covered in Phase 8 task 8.1).
- [ ] Add `data-testid="campaign-list"` and per-row testid for Playwright.

Component shell:

```tsx
"use client";

import Link from "next/link";
import { useCampaignsByProject } from "@/features/screen-campaign/lib/hooks";

export function CampaignList({ projectId }: { projectId: string }) {
  const { data, isLoading } = useCampaignsByProject(projectId);
  if (isLoading) return <Skeleton />;
  if (!data?.length) return <EmptyState ... />;
  return (
    <Table data-testid="campaign-list">
      {data.map((c) => (
        <Row key={c.id}>
          <Link href={`/projects/${projectId}/campaigns/${c.id}`}>{c.name}</Link>
          <StatusChip status={c.status} />
          <span>{c.channelCount}</span>
          <span>{c.resultCount}</span>
          ...
        </Row>
      ))}
    </Table>
  );
}
```

Commit: `feat(fe): campaign list page`.

---

## Phase 8 — Frontend builder UI

### Task 8.1: Create-campaign dialog

**Files:**
- Create: `frontend/src/features/screen-campaign/components/create-campaign-dialog.tsx`

- [ ] RHF + Zod for: name, description, `publishesCollection` toggle, compound source picker (Tabs: Explicit list / Collection picker / Saved Search picker / "From hits of campaign…" picker).
- [ ] On submit: `POST /api/v1/campaigns` → navigate to `/projects/{projectId}/campaigns/{newId}`.
- [ ] Confirm with the back-end fixture in `test_campaigns_api.py` that the source-shape DTO matches what FE submits.

Commit: `feat(fe): create-campaign dialog`.

---

### Task 8.2: Campaign builder page shell

**Files:**
- Create: `frontend/src/app/(dashboard)/projects/[projectId]/campaigns/[id]/page.tsx`
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/index.tsx`

Builder is rendered when `campaign.status === "draft"`. Otherwise route renders `<CampaignView />` (Phase 9).

Layout: 3-pane grid using Tailwind CSS Grid:
- Header (sticky): name, description (inline edit), status chip, "Close & sign" button, "Refresh from sources" button.
- Left column (300px): compound list with search + add/remove.
- Center: channel strip + AG Grid pivot.
- Right (300px): per-row decision panel (shown on row selection).

Commit: `feat(fe): campaign builder shell`.

---

### Task 8.3: Channel strip + configure popover

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/channel-strip.tsx`
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/channel-configure-popover.tsx`

- [ ] Horizontal flex strip of channel chips with `+` to add.
- [ ] "Add channel" opens popover: protocol picker (search by name), readout picker (after protocol selected), `source_kind` radio, `selection_rule` select, `qc_filter` toggles (`require_approved`, `min_z_prime` slider), `qualifier_handling` select.
- [ ] If protocol has a `HitCriterion` for the chosen readout, pre-fill `hit_threshold` and surface a checkbox "Use protocol's hit criterion" (default checked).
- [ ] On save → `POST /api/v1/campaigns/{id}/channels` and invalidate campaign query.

Commit: `feat(fe): channel strip and configure popover`.

---

### Task 8.4: AG Grid pivot view

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/results-grid.tsx`

- [ ] Define columns: pinned-left `molecule` (renders structure thumbnail + reg id), then one column per channel (cell value + qualifier + hit_call chip + manual-override marker), then `decision` pinned-right.
- [ ] Cell renderer: `<MeasurementCell value qualifier hitCall isManualOverride onOverride={...} />`.
- [ ] Cell editor: opens a popover with auto-resolved value (read-only), and a button "Override" → modal with manual value entry + qualifier select + free text reason.
- [ ] Row click → focus right decision panel.
- [ ] Use `useMemo` for columnDefs based on `campaign.channels`.

Commit: `feat(fe): AG Grid results pivot`.

---

### Task 8.5: Decision panel + per-row actions

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/decision-panel.tsx`

Right pane shows the focused row's molecule, all measurements (read-only), decision radio (`selected`/`deferred`/`rejected`), decision_reason textarea, notes. PATCH on change (debounced).

Commit: `feat(fe): per-row decision panel`.

---

### Task 8.6: Compound-list pane

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/compound-list.tsx`

- [ ] Searchable list (already in `campaign.results`).
- [ ] "Add compound" button → `MoleculePicker` (existing component from `features/chemical-registration`) → `POST /api/v1/campaigns/{id}/results`.
- [ ] "Remove" per row → `DELETE /api/v1/campaigns/{id}/results/{id}` with confirm dialog.
- [ ] "Re-seed from source" toolbar button → modal that lets the user pick a new `CompoundSource` → confirm + warn it's destructive → `POST /api/v1/campaigns/{id}/reseed`.

Commit: `feat(fe): compound list pane`.

---

### Task 8.7: Close & sign dialog

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-builder/close-sign-dialog.tsx`

- [ ] Confirms close pre-conditions client-side (≥ 1 result, ≥ 1 channel).
- [ ] Summary: # compounds, # selected/deferred/rejected, # channels, source protocols.
- [ ] Toggle: "Publish derived Collection" (mirrors `publishesCollection`, can override at close).
- [ ] E-signature step: re-auth via Sentinel (use existing `useReauthenticate()` hook).
- [ ] POST `/api/v1/campaigns/{id}/close` → on success, full-page reload to the view route.

Commit: `feat(fe): close & sign dialog`.

---

## Phase 9 — Frontend closed view + supersession

### Task 9.1: Read-only campaign view

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-view/index.tsx`

Same AG Grid as builder but read-only (no cell editors). Header shows:
- closed_at + closed_by + signature link.
- Source protocols list (rendered from `campaign.source_protocols`).
- Published Collection link.
- "Supersede" action.
- "Download JSON" → `GET /api/v1/campaigns/{id}/published`.

Commit: `feat(fe): closed campaign view`.

---

### Task 9.2: Supersede flow

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-view/supersede-dialog.tsx`

Two-step: (1) "Create new campaign superseding this one" — opens `CreateCampaignDialog` with `supersedesCampaignId` pre-filled. (2) Once the new campaign is closed, the old campaign auto-flips to `superseded`. Show a banner on the old campaign with link to the new.

Commit: `feat(fe): supersede flow`.

---

### Task 9.3: Playwright happy path

**Files:**
- Create: `frontend/tests/e2e/screen-campaign.spec.ts`

- [ ] Test: create draft, add channel, add compound, see measurement materialize, set decision=selected, close+sign, navigate to closed view, supersede, navigate to new draft. (Hits real backend in CI.)

Commit: `test(fe): screen-campaign happy path e2e`.

---

## Phase 10 — Documentation

### Task 10.1: Add Campaign aggregate to research-organization domain model

**Files:**
- Modify: `docs/domain-model/05-research-organization.md`

Append a new "Campaign" aggregate section after `ELNEntry`. Include: aggregate root + owned entities (Channel, Result, Measurement), invariants, state transitions, domain events, repository interface — mirroring the existing aggregate sections in that file.

Force-add (docs/ is gitignored):

```bash
git add -f docs/domain-model/05-research-organization.md
git commit -m "docs(domain): Campaign aggregate in research-organization context"
```

---

### Task 10.2: Update implementation-status.md

**Files:**
- Modify: `docs/implementation-status.md`

Add session entries for each phase (S33 Campaign domain, S34 Campaign persistence + resolver, S35 Campaign API, S36 Campaign FE — or whatever numbering follows current). Mark gates.

Commit: `docs: track screen campaign in implementation-status`.

---

### Task 10.3: Spec back-link

**Files:**
- Modify: `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`

Add a back-link at top:

```
**Plan:** `docs/superpowers/plans/2026-05-10-screen-campaign.md`
```

Commit alongside Task 10.1.

---

## Self-Review Notes

- **Spec coverage:**
  - §2 aggregate model — Phase 2 + 3.
  - §3 lifecycle — Phase 2 (state machine in aggregate) + Phase 5 (close/supersede services).
  - §4 build-phase mechanics — Phase 4 (resolver) + Phase 5 use cases (refresh, add-channel cascade).
  - §5 close + immutability — Phase 5.6 + Phase 3.2 (trigger).
  - §6 DAIKON contract — Phase 5.8 + Phase 6.2 (schema test).
  - §7 UI — Phases 7, 8, 9.
  - §8 persistence — Phase 3.
  - §9 testing — TDD layered throughout.
- **Placeholders:** none — every code step has full code or an exact pattern reference to `*_repository.py`.
- **Type consistency:** `CampaignChannel`, `CampaignResult`, `CampaignMeasurement`, `Campaign`, `CompoundSource`, `ChannelResolver`, `CampaignLockGuard`, `CampaignRepository`, `CampaignStatus`, `SelectionRule`, `HitCall`, `CampaignDecision`, `ValueQualifier`, `ChannelSourceKind`, `QualifierHandling` — all referenced by the same name across phases.
- **Cross-context guard:** Collection extensions land first (Phase 1) so Phase 5.6 can freeze them. Trigger lives in 027; collection columns live in 026.
