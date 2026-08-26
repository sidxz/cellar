# S8 — PlateGroup Metadata + Legacy-Parity Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plate groups carry the metadata the legacy plate tracker showed on its tree cards (state, storage location, initial volume/concentration, compound count, scientist), the tree derives each group's plate format from its plates, and the Plate Groups page renders a vertical, legacy-style card tree (one root at a time, state-colored circles, type-colored card headers, legend, Details / Request-loan actions).

**Architecture:** Six optional fields are added to the `PlateGroup` aggregate → ORM → migration 067 → commands/DTOs, with `plate_format` derived per node from an `array_agg(DISTINCT format)` query (never stored). The frontend regenerates its orval types, extends the group dialog/side panel, and rewrites `plate-group-tree.tsx` around react-d3-tree 3.x `renderCustomNodeElement` with a `<foreignObject>` card; root selection lives in the dashboard header with a per-org `localStorage` memory.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / pytest (testcontainers) · Next.js 16 / React 19 / react-d3-tree ^3.6 / shadcn-ui / TanStack Query / vitest / biome · orval.

**Spec:** `docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md` §5 (PlateGroup metadata) and §6 (Tree). Backlog closed by this plan: `docs/backlog/plate-groups-tree-viewport-overflow-baseline.md`.

## Global Constraints

- Backend commands run from `backend/` with `uv run …`; any `pytest` touching `tests/api` or `tests/integration` needs `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`. Frontend commands run from `frontend/` with `/Users/sidx/Library/pnpm/pnpm` (bare `pnpm` is broken on this machine).
- Layer rules (CLAUDE.md): Domain imports nothing; Application never imports Infrastructure/Interface.
- Lint gates scoped to touched files: `uv run ruff check <files>` / `/Users/sidx/Library/pnpm/pnpm biome check <files>` exit 0; never `--fix`/`--write` repo-wide (repo-wide gates are red on `main` for pre-existing reasons).
- Pre-existing test failures (do not fix, do not count): the 11 listed in `docs/backlog/preexisting-test-lint-failures-main.md` (`test_molecules.py` ×3, `require_same_workspace` integration ×6, `test_pdf_renderer`, `test_fk_coverage`).
- **Numeric convention (deviation from spec §5's `Numeric(10,2)`):** the inventory context stores measurements as `float` / SQLAlchemy `Float` everywhere (`batches.amount_value`, `samples.concentration_value`); the two new measurements follow that: `initial_volume_ul: float | None`, `initial_concentration_mm: float | None`, DB `Float`. Record in the S8 sync note.
- Field limits (spec §5): `state` ≤ 50 chars, `scientist` ≤ 200 chars, volume/concentration/compound_count ≥ 0. Empty/whitespace strings normalize to `None` (same as `group_type`).
- `plate_format` on a tree node is derived: no member plates → `null`; one distinct format → that format's value string (e.g. `"96"`, `"384"`); more than one → `"mixed"`.
- Legacy colors (spec §6): states solubilized `#7AB648`, dry `#99D2F2`; types vendor `#FFBD50`, screening `#8F7EB5`, master_twin `#C3D9E4`, hit_collection `#E27D60`; keys compared lower-cased; unknown types fall back to the existing djb2 hash palette; `retired`/unset states are neutral (`CHART_COLORS.neutral` = `#707372`).
- Commits: explicit pathspec (`git add` new files first); every message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu`. Branch: `feat/plate-tracker-revamp`.
- Orval: generated types are never hand-rolled; regenerate with the backend on `:8000` (`make dev-be` from the repo root — it is already running with `--reload` during this session; confirm with `curl -s localhost:8000/openapi.json | head -c 100`).

---

### Task 1: Six metadata fields on `PlateGroup` — domain, ORM, migration 067

**Files:**
- Modify: `backend/src/cellar/domain/inventory/plate_group.py` (validators, `__init__`, `create`, `update`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py:211-232` (`PlateGroupModel`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py:96-129` (`_to_domain`, `_to_model`, `_update_model`)
- Create: `backend/alembic/versions/067_plate_group_metadata.py`
- Test: `backend/tests/unit/test_plate_group.py`

**Interfaces:**
- Produces: `PlateGroup.__init__/create(..., state: str | None = None, storage_location_id: uuid.UUID | None = None, initial_volume_ul: float | None = None, initial_concentration_mm: float | None = None, compound_count: int | None = None, scientist: str | None = None)`; `PlateGroup.update(*, name=None, group_type=..., description=..., state=..., storage_location_id=..., initial_volume_ul=..., initial_concentration_mm=..., compound_count=..., scientist=...)` (`...` sentinel = leave unchanged, `None` = clear). Module constants `MAX_STATE_LEN = 50`, `MAX_SCIENTIST_LEN = 200`.

- [ ] **Step 1: Write the failing unit tests**

Append to `backend/tests/unit/test_plate_group.py`:

```python
class TestMetadataFields:
    def test_create_with_all_metadata(self) -> None:
        loc = uuid.uuid4()
        g = _group(
            state=" Solubilized ",
            storage_location_id=loc,
            initial_volume_ul=55.0,
            initial_concentration_mm=10.0,
            compound_count=17606,
            scientist="  Jane Doe ",
        )
        assert g.state == "Solubilized"
        assert g.storage_location_id == loc
        assert g.initial_volume_ul == 55.0
        assert g.initial_concentration_mm == 10.0
        assert g.compound_count == 17606
        assert g.scientist == "Jane Doe"

    def test_metadata_defaults_to_none(self) -> None:
        g = _group()
        assert g.state is None
        assert g.storage_location_id is None
        assert g.initial_volume_ul is None
        assert g.initial_concentration_mm is None
        assert g.compound_count is None
        assert g.scientist is None

    def test_blank_state_and_scientist_normalize_to_none(self) -> None:
        g = _group(state="   ", scientist="")
        assert g.state is None
        assert g.scientist is None

    @pytest.mark.parametrize(
        "field, value",
        [
            ("initial_volume_ul", -0.5),
            ("initial_concentration_mm", -1.0),
            ("compound_count", -1),
        ],
    )
    def test_negative_measurements_rejected(self, field: str, value: float) -> None:
        with pytest.raises(ValidationError):
            _group(**{field: value})

    def test_state_and_scientist_length_limits(self) -> None:
        with pytest.raises(ValidationError):
            _group(state="x" * 51)
        with pytest.raises(ValidationError):
            _group(scientist="x" * 201)

    def test_update_sentinel_leaves_untouched_and_none_clears(self) -> None:
        g = _group(state="Dry", scientist="Jane Doe", compound_count=3)
        g.update(state="Retired")
        assert g.state == "Retired"
        assert g.scientist == "Jane Doe"  # untouched (sentinel)
        assert g.compound_count == 3
        g.update(scientist=None, compound_count=None)
        assert g.scientist is None
        assert g.compound_count is None
        assert g.state == "Retired"
        events = g.collect_events()
        assert isinstance(events[-1], PlateGroupUpdated)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_plate_group.py -q -k TestMetadataFields`
Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'state'`.

- [ ] **Step 3: Domain**

In `backend/src/cellar/domain/inventory/plate_group.py`, after `MAX_GROUP_TYPE_LEN = 100` add:

```python
MAX_STATE_LEN = 50
MAX_SCIENTIST_LEN = 200


def _validated_text(value: str | None, *, max_len: int, label: str) -> str | None:
    """Strip; empty → None; enforce a max length (same stance as group_type)."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters")
    return cleaned


def _non_negative(value: float | int | None, *, label: str) -> float | int | None:
    if value is not None and (isinstance(value, bool) or value < 0):
        raise ValidationError(f"{label} must be >= 0")
    return value
```

Extend `__init__` (keyword-only params after `description`):

```python
        state: str | None = None,
        storage_location_id: uuid.UUID | None = None,
        initial_volume_ul: float | None = None,
        initial_concentration_mm: float | None = None,
        compound_count: int | None = None,
        scientist: str | None = None,
```
and the body:
```python
        self.state = _validated_text(state, max_len=MAX_STATE_LEN, label="state")
        self.storage_location_id = storage_location_id
        self.initial_volume_ul = _non_negative(initial_volume_ul, label="initial_volume_ul")
        self.initial_concentration_mm = _non_negative(
            initial_concentration_mm, label="initial_concentration_mm"
        )
        self.compound_count = _non_negative(compound_count, label="compound_count")
        self.scientist = _validated_text(scientist, max_len=MAX_SCIENTIST_LEN, label="scientist")
```

Extend `create(...)` with the same six keyword params (all default `None`) and pass them through to `cls(...)`. Extend `update` — signature and body:

```python
    def update(
        self,
        *,
        name: str | None = None,
        group_type: str | None = ...,  # type: ignore[assignment]
        description: str | None = ...,  # type: ignore[assignment]
        state: str | None = ...,  # type: ignore[assignment]
        storage_location_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        initial_volume_ul: float | None = ...,  # type: ignore[assignment]
        initial_concentration_mm: float | None = ...,  # type: ignore[assignment]
        compound_count: int | None = ...,  # type: ignore[assignment]
        scientist: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Uses sentinel ``...`` for optional nullable fields."""
        if name is not None:
            self.name = _validated_name(name)
        if group_type is not ...:
            self.group_type = _validated_group_type(group_type)
        if description is not ...:
            self.description = description
        if state is not ...:
            self.state = _validated_text(state, max_len=MAX_STATE_LEN, label="state")
        if storage_location_id is not ...:
            self.storage_location_id = storage_location_id
        if initial_volume_ul is not ...:
            self.initial_volume_ul = _non_negative(initial_volume_ul, label="initial_volume_ul")
        if initial_concentration_mm is not ...:
            self.initial_concentration_mm = _non_negative(
                initial_concentration_mm, label="initial_concentration_mm"
            )
        if compound_count is not ...:
            self.compound_count = _non_negative(compound_count, label="compound_count")
        if scientist is not ...:
            self.scientist = _validated_text(
                scientist, max_len=MAX_SCIENTIST_LEN, label="scientist"
            )
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateGroupUpdated(
                aggregate_id=self.id,
                aggregate_type="PlateGroup",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )
```

Update the module docstring's Decisions list with one line: `- Legacy-set metadata (state, location, initial vol/conc, compound count, scientist) lives on the group as optional fields (spec 2026-08-25 §5); ``plate_format`` is derived from member plates, never stored.`

- [ ] **Step 4: ORM model + repository mapping**

`models.py` `PlateGroupModel` — after `description` add (import `Float` and `Integer` from `sqlalchemy` if not already imported at the top of the module):

```python
    state: Mapped[str | None] = mapped_column(String(50))
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("storage_locations.id", ondelete="SET NULL")
    )
    initial_volume_ul: Mapped[float | None] = mapped_column(Float)
    initial_concentration_mm: Mapped[float | None] = mapped_column(Float)
    compound_count: Mapped[int | None] = mapped_column(Integer)
    scientist: Mapped[str | None] = mapped_column(String(200))
```

`plate_group_repository.py`: add the six fields to `_to_domain` (`state=model.state, storage_location_id=model.storage_location_id, initial_volume_ul=model.initial_volume_ul, initial_concentration_mm=model.initial_concentration_mm, compound_count=model.compound_count, scientist=model.scientist`), to `_to_model` (same, from `aggregate.`), and to `_update_model` (`model.state = aggregate.state` … six assignments).

- [ ] **Step 5: Migration 067**

Create `backend/alembic/versions/067_plate_group_metadata.py`:

```python
"""067 — plate_groups metadata columns (spec 2026-08-25 §5)

Legacy-set metadata on the group: state, storage location, initial
volume/concentration, compound count, scientist. All nullable; measurements
are Float per the inventory convention (not Numeric).

Revision ID: 067_plate_group_metadata
Revises: 066_drop_plates_private
"""

import sqlalchemy as sa
from alembic import op

revision = "067_plate_group_metadata"
down_revision = "066_drop_plates_private"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plate_groups", sa.Column("state", sa.String(50), nullable=True))
    op.add_column("plate_groups", sa.Column("storage_location_id", sa.Uuid(), nullable=True))
    op.add_column("plate_groups", sa.Column("initial_volume_ul", sa.Float(), nullable=True))
    op.add_column(
        "plate_groups", sa.Column("initial_concentration_mm", sa.Float(), nullable=True)
    )
    op.add_column("plate_groups", sa.Column("compound_count", sa.Integer(), nullable=True))
    op.add_column("plate_groups", sa.Column("scientist", sa.String(200), nullable=True))
    op.create_foreign_key(
        "fk_plate_groups_storage_location",
        "plate_groups",
        "storage_locations",
        ["storage_location_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_plate_groups_storage_location", "plate_groups", type_="foreignkey")
    for col in (
        "scientist",
        "compound_count",
        "initial_concentration_mm",
        "initial_volume_ul",
        "storage_location_id",
        "state",
    ):
        op.drop_column("plate_groups", col)
```

- [ ] **Step 6: Run + lint**

Run: `cd backend && uv run pytest tests/unit/test_plate_group.py tests/unit/test_plate_group_tree.py -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/inventory/test_plate_group_repository.py tests/api/test_plate_groups.py -q && uv run alembic heads && uv run ruff check src/cellar/domain/inventory/plate_group.py src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py alembic/versions/067_plate_group_metadata.py tests/unit/test_plate_group.py`
Expected: all PASS; `alembic heads` prints exactly `067_plate_group_metadata (head)`; ruff clean. (`test_plate_group_repository.py` fails on main only when the Docker socket env is missing — with `DOCKER_HOST` set it must be green.)

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/067_plate_group_metadata.py
git commit -m "feat(inventory): PlateGroup metadata — state, storage location, initial vol/conc, compound count, scientist (migration 067)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/alembic/versions/067_plate_group_metadata.py backend/src/cellar/domain/inventory/plate_group.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py backend/tests/unit/test_plate_group.py
```

---

### Task 2: Commands, DTOs, derived `plate_format`, `created_at` on tree nodes

**Files:**
- Modify: `backend/src/cellar/application/inventory/plate_groups.py:48-66` (commands), `:106-134` (`GroupTreeNode`, `build_tree`), `:222-232` (`CreatePlateGroup` → `PlateGroup.create`), `:283-289` (`UpdatePlateGroup` kwargs), `:433-441` (`GetGroupTree`)
- Modify: `backend/src/cellar/domain/inventory/repository.py` (`PlateGroupRepository` protocol: add `plate_formats_by_group`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py` (new query)
- Modify: `backend/src/cellar/interface/routes/plate_groups.py:37-121` (DTOs/bodies), `:139-147` (create), `:166-174` (update)
- Test: `backend/tests/unit/test_plate_group_tree.py`, `backend/tests/api/test_plate_groups.py`

**Interfaces:**
- Consumes: Task 1's `PlateGroup.create/update` keyword fields.
- Produces: `derive_format(formats: list[str]) -> str | None` (pure, in `application/inventory/plate_groups.py`); `build_tree(groups, counts, formats: dict[uuid.UUID, list[str]] | None = None)`; `GroupTreeNode.plate_format: str | None`; repo `plate_formats_by_group(workspace_id, owner_org_id=None) -> dict[uuid.UUID, list[str]]`; API bodies `CreatePlateGroupBody`/`UpdatePlateGroupBody` with the six fields; responses `PlateGroupResponse`/`GroupTreeNodeResponse` with the six fields + `created_at: datetime`; `GroupTreeNodeResponse.plate_format: str | None`.

- [ ] **Step 1: Failing unit tests for the pure helpers**

Append to `backend/tests/unit/test_plate_group_tree.py`:

```python
from cellar.application.inventory.plate_groups import derive_format


def test_derive_format_none_single_mixed() -> None:
    assert derive_format([]) is None
    assert derive_format(["96"]) == "96"
    assert derive_format(["384", "384"]) == "384"
    assert derive_format(["96", "384"]) == "mixed"


def test_build_tree_carries_plate_format_and_metadata() -> None:
    root = _g("Root")
    a = _g("A", parent=root.id)
    nodes = build_tree([root, a], {a.id: 2}, {a.id: ["96", "384"], root.id: ["96"]})
    assert nodes[0].plate_format == "96"
    assert nodes[0].children[0].plate_format == "mixed"


def test_build_tree_formats_default_to_none() -> None:
    root = _g("Root")
    assert build_tree([root], {})[0].plate_format is None
```

Run: `uv run pytest tests/unit/test_plate_group_tree.py -q`
Expected: FAIL — `ImportError: cannot import name 'derive_format'`.

- [ ] **Step 2: Application changes**

`plate_groups.py`:

```python
@dataclass(frozen=True, kw_only=True)
class CreatePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    name: str
    created_by: uuid.UUID
    owner_org_id: uuid.UUID | None = None
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None
    state: str | None = None
    storage_location_id: uuid.UUID | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    name: str | None = None
    group_type: str | None | object = UNSET
    description: str | None | object = UNSET
    state: str | None | object = UNSET
    storage_location_id: uuid.UUID | None | object = UNSET
    initial_volume_ul: float | None | object = UNSET
    initial_concentration_mm: float | None | object = UNSET
    compound_count: int | None | object = UNSET
    scientist: str | None | object = UNSET
```

```python
MIXED_FORMAT = "mixed"


def derive_format(formats: list[str]) -> str | None:
    """Group-level plate format derived from member plates (spec §5): none →
    None, one distinct value → it, several → "mixed"."""
    distinct = sorted(set(formats))
    if not distinct:
        return None
    return distinct[0] if len(distinct) == 1 else MIXED_FORMAT


@dataclass
class GroupTreeNode:
    group: PlateGroup
    plate_count: int
    plate_format: str | None = None
    children: list[GroupTreeNode] = field(default_factory=list)


def build_tree(
    groups: list[PlateGroup],
    counts: dict[uuid.UUID, int],
    formats: dict[uuid.UUID, list[str]] | None = None,
) -> list[GroupTreeNode]:
    """Assemble nested nodes from a flat fetch. A node whose parent isn't in
    the fetched set is promoted to root (defensive — never crash the page)."""
    fmts = formats or {}
    nodes = {
        g.id: GroupTreeNode(
            group=g,
            plate_count=counts.get(g.id, 0),
            plate_format=derive_format(fmts.get(g.id, [])),
        )
        for g in groups
    }
    # ... rest of the existing body unchanged ...
```

`CreatePlateGroup.__call__`: pass the six new command fields into `PlateGroup.create(...)` (`state=input.state, storage_location_id=input.storage_location_id, initial_volume_ul=input.initial_volume_ul, initial_concentration_mm=input.initial_concentration_mm, compound_count=input.compound_count, scientist=input.scientist`).

`UpdatePlateGroup.__call__`: extend the kwargs block —

```python
            kwargs: dict = {}
            if input.name is not None:
                kwargs["name"] = input.name
            for key in (
                "group_type",
                "description",
                "state",
                "storage_location_id",
                "initial_volume_ul",
                "initial_concentration_mm",
                "compound_count",
                "scientist",
            ):
                value = getattr(input, key)
                if value is not UNSET:
                    kwargs[key] = value
            group.update(**kwargs)
```

`GetGroupTree.__call__`: after `counts = …` add `formats = await self._repo.plate_formats_by_group(input.workspace_id, owner_org_id=org_id)` and return `build_tree(groups, counts, formats)`.

- [ ] **Step 3: Repository query + protocol**

`domain/inventory/repository.py` `PlateGroupRepository` protocol: add
```python
    async def plate_formats_by_group(
        self, workspace_id: uuid.UUID, owner_org_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, list[str]]: ...
```
`plate_group_repository.py`, below `count_plates_by_group`:

```python
    async def plate_formats_by_group(
        self, workspace_id: uuid.UUID, owner_org_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, list[str]]:
        """Distinct plate formats per group — the tree derives "96"/"384"/"mixed"."""
        stmt = (
            select(
                RegisteredPlateModel.group_id,
                func.array_agg(func.distinct(RegisteredPlateModel.format)),
            )
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.group_id.is_not(None),
            )
            .group_by(RegisteredPlateModel.group_id)
        )
        if owner_org_id is not None:
            stmt = stmt.where(RegisteredPlateModel.owner_org_id == owner_org_id)
        result = await self._session.execute(stmt)
        return {row[0]: [str(f) for f in row[1]] for row in result.all()}
```
(`RegisteredPlateModel.format` is the plate format column — confirm its attribute name with `grep -n "format" models.py` inside `RegisteredPlateModel`; if the column stores the enum value string `"96"`, `str(f)` is a no-op.)

Any in-memory fake of `PlateGroupRepository` in `backend/tests` (grep `class .*PlateGroupRepo`) gets a `plate_formats_by_group` returning `{}`.

- [ ] **Step 4: Routes**

`PlateGroupResponse` and `GroupTreeNodeResponse` gain, after `description`:
```python
    state: str | None = None
    storage_location_id: uuid.UUID | None = None
    initial_volume_ul: float | None = None
    initial_concentration_mm: float | None = None
    compound_count: int | None = None
    scientist: str | None = None
    created_at: datetime
```
(`from datetime import datetime`), populated in `from_domain` / `from_node` from `g.<field>` / `n.group.<field>` and `created_at=g.created_at` / `n.group.created_at`. `GroupTreeNodeResponse` additionally gains `plate_format: str | None = None` ← `n.plate_format`.

`CreatePlateGroupBody` gains the six fields (all `| None = None`); `UpdatePlateGroupBody` gains the six (all `| None = None`, still `extra: "forbid"`). Create handler passes them through to the command; update handler extends the `provided` mapping:

```python
    command = UpdatePlateGroupCommand(
        workspace_id=auth.workspace_id,
        group_id=group_id,
        name=body.name if "name" in provided else None,
        group_type=body.group_type if "group_type" in provided else UNSET,
        description=body.description if "description" in provided else UNSET,
        state=body.state if "state" in provided else UNSET,
        storage_location_id=body.storage_location_id if "storage_location_id" in provided else UNSET,
        initial_volume_ul=body.initial_volume_ul if "initial_volume_ul" in provided else UNSET,
        initial_concentration_mm=(
            body.initial_concentration_mm if "initial_concentration_mm" in provided else UNSET
        ),
        compound_count=body.compound_count if "compound_count" in provided else UNSET,
        scientist=body.scientist if "scientist" in provided else UNSET,
    )
```

- [ ] **Step 5: API tests**

Append to `backend/tests/api/test_plate_groups.py` (helpers `_mk_group(client, name, **overrides)` and `_mk_plate(client, barcode, **overrides)` exist; `_mk_plate` accepts `format` via overrides if its body builder passes `**overrides` through — check, and if not, add `format=overrides.pop("format", "96")` there):

```python
class TestMetadata:
    async def test_create_round_trips_metadata_into_tree(self, client: AsyncClient) -> None:
        g = await _mk_group(
            client,
            f"Meta-{uuid.uuid4().hex[:6]}",
            state="Solubilized",
            initial_volume_ul=55.0,
            initial_concentration_mm=10.0,
            compound_count=17606,
            scientist="Jane Doe",
        )
        assert g["state"] == "Solubilized"
        assert g["compound_count"] == 17606
        assert g["created_at"]
        tree = (await client.get("/api/v1/plate-groups/tree")).json()
        node = next(r for r in tree["roots"] if r["id"] == g["id"])
        assert node["scientist"] == "Jane Doe"
        assert node["initial_volume_ul"] == 55.0
        assert node["plate_format"] is None

    async def test_patch_partial_keeps_others_and_null_clears(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"Meta-{uuid.uuid4().hex[:6]}", state="Dry", scientist="Jane")
        resp = await client.patch(f"/api/v1/plate-groups/{g['id']}", json={"state": "Retired"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "Retired"
        assert resp.json()["scientist"] == "Jane"
        resp = await client.patch(f"/api/v1/plate-groups/{g['id']}", json={"scientist": None})
        assert resp.status_code == 200, resp.text
        assert resp.json()["scientist"] is None
        assert resp.json()["state"] == "Retired"

    async def test_negative_measurement_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/plate-groups",
            json={"name": f"Bad-{uuid.uuid4().hex[:6]}", "initial_volume_ul": -1},
        )
        assert resp.status_code == 422, resp.text

    async def test_tree_plate_format_single_and_mixed(self, client: AsyncClient) -> None:
        single = await _mk_group(client, f"Single-{uuid.uuid4().hex[:6]}")
        mixed = await _mk_group(client, f"Mixed-{uuid.uuid4().hex[:6]}")
        p1 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", format="96")
        p2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", format="96")
        p3 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", format="384")
        for gid, ids in ((single["id"], [p1["id"]]), (mixed["id"], [p2["id"], p3["id"]])):
            r = await client.post(f"/api/v1/plate-groups/{gid}/plates", json={"plate_ids": ids})
            assert r.status_code == 200, r.text
        tree = (await client.get("/api/v1/plate-groups/tree")).json()
        by_id = {r["id"]: r for r in tree["roots"]}
        assert by_id[single["id"]]["plate_format"] == "96"
        assert by_id[mixed["id"]]["plate_format"] == "mixed"
```

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit/test_plate_group_tree.py tests/api/test_plate_groups.py tests/api/test_plate_loans.py tests/api/test_plate_insights.py -q && uv run ruff check src/cellar/application/inventory/plate_groups.py src/cellar/domain/inventory/repository.py src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py src/cellar/interface/routes/plate_groups.py tests/unit/test_plate_group_tree.py tests/api/test_plate_groups.py`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(inventory): group metadata through commands/API; tree nodes carry derived plate_format and created_at

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/application/inventory/plate_groups.py backend/src/cellar/domain/inventory/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py backend/src/cellar/interface/routes/plate_groups.py backend/tests/unit/test_plate_group_tree.py backend/tests/api/test_plate_groups.py
```
(add any test fake file you touched to the pathspec.)

---

### Task 3: Seed the `plate_group_state` vocabulary in the legacy migration script

**Files:**
- Modify: `backend/scripts/migrate_legacy_plate_tracker.py:453, 500-520` (generalize `seed_group_type_vocab`)
- Test: the script's existing unit test module (find it with `grep -rln migrate_legacy_plate_tracker backend/tests`) — add one test if it already tests `seed_group_type_vocab`; otherwise skip the test and say so.

**Interfaces:**
- Produces: `seed_vocab(*, cv_repo, workspace_id, actor_id, name: str, values: list[str]) -> None`; `seed_group_type_vocab` becomes a thin wrapper; new call seeds `"plate_group_state"` from `sorted({s.set_state for s in legacy.sets if s.set_state})` right after the type vocab in `run_migration`.

- [ ] **Step 1: Refactor**

Replace the body of `seed_group_type_vocab` with a generic helper and two call sites:

```python
_GROUP_TYPE_VOCAB = "plate_group_type"
_GROUP_STATE_VOCAB = "plate_group_state"


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
```
(keep whatever the original function did after the `changed` loop — read it first; the snippet above mirrors lines 500-520.) `LegacySet` already carries `set_state` (it is read by the `SELECT … set_state …` at line ~255); if the dataclass lacks the attribute, add it.

- [ ] **Step 2: Test + lint**

Run: `uv run pytest $(grep -rln migrate_legacy_plate_tracker tests | tr '\n' ' ') -q && uv run ruff check scripts/migrate_legacy_plate_tracker.py`
Expected: existing script tests PASS (28 at last count), ruff clean.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(scripts): legacy migration seeds the plate_group_state vocabulary alongside plate_group_type

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/scripts/migrate_legacy_plate_tracker.py
```
(plus the test file if you added a test.)

---

### Task 4: Frontend — regenerated types, group dialog + side panel with the six fields

**Files:**
- Modify (regen): `frontend/src/shared/lib/api/model/*` (`groupTreeNodeResponse*.ts`, `plateGroupResponse*.ts`, `createPlateGroupBody*.ts`, `updatePlateGroupBody*.ts` + new per-field helper types + `index.ts`)
- Modify: `frontend/src/features/inventory/components/plate-group-dialog.tsx`
- Modify: `frontend/src/features/inventory/components/plate-group-details.tsx`
- Test: `frontend/src/features/inventory/components/plate-group-dialog.test.tsx`, `frontend/src/features/inventory/components/plate-group-details.test.tsx`

**Interfaces:**
- Consumes: Task 2's API fields (`state`, `storage_location_id`, `initial_volume_ul`, `initial_concentration_mm`, `compound_count`, `scientist`, `created_at`, `plate_format`).
- Produces: `DEFAULT_GROUP_STATES = ["Dry", "Solubilized", "Retired"]` exported from `plate-group-dialog.tsx`; `PlateGroupDetails` renders a "Details" definition list (used unchanged by Task 5's dashboard).

- [ ] **Step 1: Regenerate types**

With the backend on `:8000` (it reloads automatically), from `frontend/`: `/Users/sidx/Library/pnpm/pnpm generate:api`. Inspect `git diff --stat src/shared/lib/api/model/` — expected: the four group DTO/body files gain the fields, new helper type files appear (e.g. `groupTreeNodeResponseState.ts`), `index.ts` gains their exports. Revert unrelated churn (`git checkout -- <file>`) only if a diff is not additive.

- [ ] **Step 2: Failing tests**

`plate-group-dialog.test.tsx` — extend `setup`'s mock so `opts.url.includes("/storage-locations")` resolves `[{ id: "loc-1", name: "Room 1148 / Freezer 4", type: "freezer", parent_id: null }]` and `/vocabularies` resolves `[]`, then add:

```tsx
  it("create sends the metadata fields", async () => {
    setup({ orgId: "org1", parentGroupId: null, group: null });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "SAC1" } });
    fireEvent.change(screen.getByLabelText("Scientist"), { target: { value: "Jane Doe" } });
    fireEvent.change(screen.getByLabelText("Initial volume (µL)"), { target: { value: "55" } });
    fireEvent.change(screen.getByLabelText("Initial concentration (mM)"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Compound count"), { target: { value: "17606" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      const call = mocked.mock.calls.find(([o]) => (o as { method: string }).method === "POST");
      expect(call).toBeTruthy();
      const data = (call?.[0] as { data: Record<string, unknown> }).data;
      expect(data).toMatchObject({
        name: "SAC1",
        scientist: "Jane Doe",
        initial_volume_ul: 55,
        initial_concentration_mm: 10,
        compound_count: 17606,
        state: null,
        storage_location_id: null,
      });
    });
  });
```

`plate-group-details.test.tsx` — extend the `node` fixture with `state: "Solubilized", storage_location_id: "loc-1", initial_volume_ul: 55, initial_concentration_mm: 10, compound_count: 17606, scientist: "Jane Doe", plate_format: "96", created_at: "2026-08-25T10:00:00Z"`, make the mock answer `/storage-locations` with `[{ id: "loc-1", name: "Room 1148 / Freezer 4" }]`, and add:

```tsx
  it("renders the metadata rows", async () => {
    setup();
    expect(await screen.findByText("Room 1148 / Freezer 4")).toBeInTheDocument();
    expect(screen.getByText("Solubilized")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("55 µL · 10 mM")).toBeInTheDocument();
    expect(screen.getByText("17,606")).toBeInTheDocument();
    expect(screen.getByText("96-well")).toBeInTheDocument();
  });
```

Run: `/Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory/components/plate-group-dialog.test.tsx src/features/inventory/components/plate-group-details.test.tsx`
Expected: the two new tests FAIL (labels/rows missing).

- [ ] **Step 3: Dialog**

In `plate-group-dialog.tsx`:
- `export const DEFAULT_GROUP_STATES = ["Dry", "Solubilized", "Retired"];`
- imports: `useStorageLocations` from `../hooks/use-storage-locations`.
- state: `const [state, setState] = useState<string>(NONE); const [locationId, setLocationId] = useState<string>(NONE); const [volume, setVolume] = useState(""); const [concentration, setConcentration] = useState(""); const [compoundCount, setCompoundCount] = useState(""); const [scientist, setScientist] = useState("");`
- `const vocabStates = useVocabularyTerms("plate_group_state"); const groupStates = vocabStates.length > 0 ? vocabStates : DEFAULT_GROUP_STATES; const { data: storageLocations } = useStorageLocations();`
- reset effect: `setState(group?.state ?? NONE); setLocationId(group?.storage_location_id ?? NONE); setVolume(group?.initial_volume_ul != null ? String(group.initial_volume_ul) : ""); setConcentration(group?.initial_concentration_mm != null ? String(group.initial_concentration_mm) : ""); setCompoundCount(group?.compound_count != null ? String(group.compound_count) : ""); setScientist(group?.scientist ?? "");`
- `handleSave` builds `const meta = { state: state === NONE ? null : state, storage_location_id: locationId === NONE ? null : locationId, initial_volume_ul: volume.trim() ? Number(volume) : null, initial_concentration_mm: concentration.trim() ? Number(concentration) : null, compound_count: compoundCount.trim() ? Number(compoundCount) : null, scientist: scientist.trim() ? scientist.trim() : null };` and spreads `...meta` into both the update and create payloads.
- Fields, after Type: **State** `<Select>` (`id="group-state"`, `aria-label="Group state"`, `None` + `groupStates`), **Storage location** `<Select>` (`id="group-location"`, `aria-label="Storage location"`, `None` + one item per `storageLocations` with `l.name`), a two-column grid with **Initial volume (µL)** and **Initial concentration (mM)** (`<Input type="number" min={0} step="any">`), **Compound count** (`<Input type="number" min={0} step={1}>`), **Scientist** (`<Input maxLength={200}>`). Every `<Label htmlFor>` text must match the test's `getByLabelText` strings exactly.
- Disable Save while any numeric input is negative (`Number(x) < 0`).

- [ ] **Step 4: Side panel**

In `plate-group-details.tsx` add `const { data: locations } = useStorageLocations(); const locationName = node.storage_location_id ? (locations?.find((l) => l.id === node.storage_location_id)?.name ?? "…") : null;` and, between the header block and the action buttons, a definition list rendered only for present values:

```tsx
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm" data-testid="group-metadata">
        {node.state ? (<><dt className="text-muted-foreground">State</dt><dd>{node.state}</dd></>) : null}
        {node.plate_format ? (<><dt className="text-muted-foreground">Format</dt><dd>{node.plate_format === "mixed" ? "mixed" : `${node.plate_format}-well`}</dd></>) : null}
        {locationName ? (<><dt className="text-muted-foreground">Location</dt><dd>{locationName}</dd></>) : null}
        {node.scientist ? (<><dt className="text-muted-foreground">Scientist</dt><dd>{node.scientist}</dd></>) : null}
        {node.initial_volume_ul != null || node.initial_concentration_mm != null ? (
          <><dt className="text-muted-foreground">Initial</dt><dd>{formatInitial(node.initial_volume_ul, node.initial_concentration_mm)}</dd></>
        ) : null}
        {node.compound_count != null ? (<><dt className="text-muted-foreground">Compounds</dt><dd>{node.compound_count.toLocaleString("en-US")}</dd></>) : null}
        <dt className="text-muted-foreground">Created</dt><dd>{formatDate(node.created_at)}</dd>
      </dl>
```
with a module-level helper
```ts
export function formatInitial(volumeUl: number | null | undefined, concentrationMm: number | null | undefined): string {
  const parts: string[] = [];
  if (volumeUl != null) parts.push(`${volumeUl} µL`);
  if (concentrationMm != null) parts.push(`${concentrationMm} mM`);
  return parts.join(" · ");
}
```
(`formatDate` from `@/shared/lib/format-date` — the repo's date-only-safe helper; check its export name with `grep -n "export function" src/shared/lib/format-date.ts`.)

- [ ] **Step 5: Type-check, lint, test**

Run from `frontend/`: `/Users/sidx/Library/pnpm/pnpm tsc --noEmit && /Users/sidx/Library/pnpm/pnpm biome check src/features/inventory/components/plate-group-dialog.tsx src/features/inventory/components/plate-group-dialog.test.tsx src/features/inventory/components/plate-group-details.tsx src/features/inventory/components/plate-group-details.test.tsx; echo "biome exit=$?" && /Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory`
Expected: tsc clean, `biome exit=0`, tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shared/lib/api/model
git commit -m "feat(frontend): plate group dialog and side panel carry state, location, initial vol/conc, compound count, scientist; regenerated types

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- frontend/src/shared/lib/api/model frontend/src/features/inventory/components/plate-group-dialog.tsx frontend/src/features/inventory/components/plate-group-dialog.test.tsx frontend/src/features/inventory/components/plate-group-details.tsx frontend/src/features/inventory/components/plate-group-details.test.tsx
```

---

### Task 5: Frontend — the legacy-parity tree (vertical cards, root selector, legend, viewport fix, Request loan from a card)

**Files:**
- Modify: `frontend/src/features/inventory/components/plate-group-tree-utils.ts` (whole file)
- Modify: `frontend/src/features/inventory/components/plate-group-tree-utils.test.ts`
- Modify: `frontend/src/features/inventory/components/plate-group-tree.tsx` (whole file)
- Modify: `frontend/src/features/inventory/components/plate-group-dashboard.tsx` (root selector, dialog wiring, request-loan dialog)
- Modify: `frontend/src/features/inventory/components/request-loan-dialog.tsx:70-100` (`initialGroupId` prop)
- Create: `frontend/src/features/inventory/components/plate-group-card.tsx` (the foreignObject card body — keeps the tree file focused)

**Interfaces:**
- Consumes: `PlateGroupNode` (with Task 4's fields), `RequestLoanDialog` (Task 6/S7 shape: `{open, onOpenChange, orgId}`), `useStorageLocations`.
- Produces: utils `stateColor(state: string | null | undefined): string`, `groupTypeColor(type)` (fixed legacy map first, hash fallback), `legendEntries(roots) → { states: LegendEntry[]; types: LegendEntry[] }`, `formatLabel(fmt: string | null | undefined): string | null`, constants `TYPE_COLORS`, `STATE_COLORS`, `ROOT_STORAGE_KEY(orgId) = \`plate-groups.root.${orgId}\``; component `PlateGroupTreeView({ root, selectedId, onSelect, onRequestLoan })`; `RequestLoanDialogProps.initialGroupId?: string`.

- [ ] **Step 1: Failing util tests**

Replace the `groupTypeColor` and `legendEntries` describes in `plate-group-tree-utils.test.ts` with:

```ts
describe("groupTypeColor", () => {
  it("uses the legacy palette for the four known types, case-insensitively", () => {
    expect(groupTypeColor("vendor")).toBe("#FFBD50");
    expect(groupTypeColor("VENDOR")).toBe("#FFBD50");
    expect(groupTypeColor("screening")).toBe("#8F7EB5");
    expect(groupTypeColor("master_twin")).toBe("#C3D9E4");
    expect(groupTypeColor("hit_collection")).toBe("#E27D60");
  });
  it("is stable and distinct for unknown types", () => {
    expect(groupTypeColor("custom")).toBe(groupTypeColor("custom"));
    expect(groupTypeColor("custom")).not.toBe(groupTypeColor("other"));
  });
  it("returns the neutral color for an untyped (empty) group", () => {
    expect(groupTypeColor("")).toBe("#707372");
  });
});

describe("stateColor", () => {
  it("maps legacy states and falls back to neutral", () => {
    expect(stateColor("Solubilized")).toBe("#7AB648");
    expect(stateColor("dry")).toBe("#99D2F2");
    expect(stateColor("Retired")).toBe("#707372");
    expect(stateColor(null)).toBe("#707372");
  });
});

describe("formatLabel", () => {
  it("renders well counts and mixed", () => {
    expect(formatLabel("96")).toBe("96-well");
    expect(formatLabel("mixed")).toBe("mixed formats");
    expect(formatLabel(null)).toBeNull();
  });
});

describe("legendEntries", () => {
  it("lists distinct states and types present, dedupes, and appends unset/untyped", () => {
    const roots = [
      node({ id: "1", group_type: "vendor", state: "Solubilized" }),
      node({ id: "2", group_type: "vendor", state: "Dry", children: [node({ id: "2a", group_type: "screening", state: null })] }),
    ];
    const { states, types } = legendEntries(roots);
    expect(types.map((t) => t.label)).toEqual(["vendor", "screening"]);
    expect(states.map((s) => s.label)).toEqual(["Solubilized", "Dry", "unset"]);
    expect(types.find((t) => t.label === "vendor")?.color).toBe("#FFBD50");
  });
  it("omits unset when every group has a state and untyped when every group is typed", () => {
    const { states, types } = legendEntries([node({ id: "1", group_type: "vendor", state: "Dry" })]);
    expect(states.some((s) => s.label === "unset")).toBe(false);
    expect(types.some((t) => t.label === "untyped")).toBe(false);
  });
});
```
(update the imports to `formatLabel, groupTypeColor, legendEntries, stateColor, truncateLabel, MAX_NODE_LABEL`; the `node()` helper stays.)

Run: `/Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory/components/plate-group-tree-utils.test.ts`
Expected: FAIL (`stateColor`/`formatLabel` not exported; legend shape).

- [ ] **Step 2: Utils**

Replace `plate-group-tree-utils.ts` with:

```ts
import { CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import type { PlateGroupNode } from "../hooks/use-plate-groups";

export const MAX_NODE_LABEL = 28;

/** Legacy plate-tracker palette (spec 2026-08-25 §6); keys are lower-cased. */
export const TYPE_COLORS: Record<string, string> = {
  vendor: "#FFBD50",
  screening: "#8F7EB5",
  master_twin: "#C3D9E4",
  hit_collection: "#E27D60",
};
export const STATE_COLORS: Record<string, string> = {
  solubilized: "#7AB648",
  dry: "#99D2F2",
};

export const ROOT_STORAGE_KEY = (orgId: string) => `plate-groups.root.${orgId}`;

export interface LegendEntry {
  label: string;
  color: string;
}

/** Fixed legacy color for the four known types; deterministic hash → palette for
 * anything else; neutral for untyped. */
export function groupTypeColor(groupType: string | null | undefined): string {
  if (!groupType) return CHART_COLORS.neutral;
  const fixed = TYPE_COLORS[groupType.toLowerCase()];
  if (fixed) return fixed;
  let hash = 5381;
  for (let i = 0; i < groupType.length; i++) {
    hash = (hash * 33) ^ groupType.charCodeAt(i);
  }
  return GROUP_PALETTE[Math.abs(hash) % GROUP_PALETTE.length];
}

/** Circle fill by state: solubilized green, dry blue, anything else neutral. */
export function stateColor(state: string | null | undefined): string {
  if (!state) return CHART_COLORS.neutral;
  return STATE_COLORS[state.toLowerCase()] ?? CHART_COLORS.neutral;
}

export function formatLabel(fmt: string | null | undefined): string | null {
  if (!fmt) return null;
  return fmt === "mixed" ? "mixed formats" : `${fmt}-well`;
}

export function truncateLabel(name: string, max: number = MAX_NODE_LABEL): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

/** Distinct states and types present in the tree (depth-first, first-seen order)
 * with "unset"/"untyped" appended when any node lacks one. */
export function legendEntries(roots: PlateGroupNode[]): {
  states: LegendEntry[];
  types: LegendEntry[];
} {
  const seenStates = new Set<string>();
  const seenTypes = new Set<string>();
  const states: LegendEntry[] = [];
  const types: LegendEntry[] = [];
  let hasUnset = false;
  let hasUntyped = false;
  const walk = (n: PlateGroupNode) => {
    const state = n.state ?? "";
    if (!state) hasUnset = true;
    else if (!seenStates.has(state.toLowerCase())) {
      seenStates.add(state.toLowerCase());
      states.push({ label: state, color: stateColor(state) });
    }
    const type = n.group_type ?? "";
    if (!type) hasUntyped = true;
    else if (!seenTypes.has(type.toLowerCase())) {
      seenTypes.add(type.toLowerCase());
      types.push({ label: type, color: groupTypeColor(type) });
    }
    for (const c of n.children ?? []) walk(c);
  };
  for (const r of roots) walk(r);
  if (hasUnset) states.push({ label: "unset", color: CHART_COLORS.neutral });
  if (hasUntyped) types.push({ label: "untyped", color: CHART_COLORS.neutral });
  return { states, types };
}
```

Run the utils test again — Expected: PASS.

- [ ] **Step 3: The card component**

Create `frontend/src/features/inventory/components/plate-group-card.tsx`:

```tsx
"use client";

import { formatDate } from "@/shared/lib/format-date";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { formatInitial } from "./plate-group-details";
import { formatLabel, groupTypeColor } from "./plate-group-tree-utils";

export const CARD_WIDTH = 270;
export const CARD_HEIGHT = 210;

export interface PlateGroupCardProps {
  node: PlateGroupNode;
  locationName: string | null;
  selected: boolean;
  onSelect: () => void;
  onRequestLoan: () => void;
}

/** The HTML body of a tree node — rendered inside an SVG <foreignObject>. */
export function PlateGroupCard({ node, locationName, selected, onSelect, onRequestLoan }: PlateGroupCardProps) {
  const headerBg = groupTypeColor(node.group_type);
  const rows: string[] = [];
  const fmt = formatLabel(node.plate_format);
  if (fmt || node.scientist) rows.push([fmt, node.scientist].filter(Boolean).join(" · "));
  if (locationName) rows.push(locationName);
  if (node.initial_volume_ul != null || node.initial_concentration_mm != null) {
    rows.push(`Initial: ${formatInitial(node.initial_volume_ul, node.initial_concentration_mm)}`);
  }
  if (node.compound_count != null) rows.push(`${node.compound_count.toLocaleString("en-US")} compounds`);
  rows.push(`${node.plate_count} plate${node.plate_count === 1 ? "" : "s"}`);
  rows.push(`created ${formatDate(node.created_at)}`);

  return (
    <div
      title={node.description ?? node.name}
      className={`flex h-full flex-col overflow-hidden rounded-md border bg-card text-card-foreground shadow-sm ${selected ? "ring-2 ring-primary" : ""}`}
      data-testid={`group-card-${node.id}`}
    >
      <button
        type="button"
        onClick={onSelect}
        className="truncate px-2 py-1 text-left text-sm font-semibold text-neutral-900"
        style={{ background: headerBg }}
      >
        {node.name}
        {node.group_type ? <span className="ml-2 text-xs font-normal opacity-80">{node.group_type}</span> : null}
      </button>
      <ul className="flex-1 space-y-0.5 px-2 py-1 text-xs text-muted-foreground">
        {rows.map((r) => (
          <li key={r} className="truncate">{r}</li>
        ))}
      </ul>
      <div className="flex gap-3 border-t px-2 py-1 text-xs">
        <button type="button" className="text-primary hover:underline" onClick={onSelect}>
          Details
        </button>
        {node.plate_count > 0 ? (
          <button type="button" className="text-primary hover:underline" onClick={onRequestLoan}>
            Request loan
          </button>
        ) : null}
      </div>
    </div>
  );
}
```
(`formatInitial` is exported by Task 4's `plate-group-details.tsx`; the header text color is fixed dark because the four legacy header colors are light in both themes.)

- [ ] **Step 4: The tree view**

Replace `plate-group-tree.tsx` with:

```tsx
"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CustomNodeElementProps, RawNodeDatum } from "react-d3-tree";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { CARD_HEIGHT, CARD_WIDTH, PlateGroupCard } from "./plate-group-card";
import { legendEntries, stateColor } from "./plate-group-tree-utils";

// react-d3-tree touches window/d3 at module scope — client-only.
const Tree = dynamic(() => import("react-d3-tree"), { ssr: false });

export interface PlateGroupTreeViewProps {
  /** The one root group shown at a time (legacy: one library per view). */
  root: PlateGroupNode;
  selectedId: string | null;
  onSelect: (node: PlateGroupNode) => void;
  onRequestLoan: (node: PlateGroupNode) => void;
}

interface GroupDatum extends RawNodeDatum {
  attributes: { id: string };
  children?: GroupDatum[];
}

const NODE_SIZE = { x: 320, y: 260 };
const CIRCLE_R = 25;
const ROOT_R = 30;

function toDatum(node: PlateGroupNode): GroupDatum {
  return { name: node.name, attributes: { id: node.id }, children: (node.children ?? []).map(toDatum) };
}

function indexNodes(root: PlateGroupNode): Map<string, PlateGroupNode> {
  const map = new Map<string, PlateGroupNode>();
  const walk = (n: PlateGroupNode) => {
    map.set(n.id, n);
    (n.children ?? []).forEach(walk);
  };
  walk(root);
  return map;
}

export function PlateGroupTreeView({ root, selectedId, onSelect, onRequestLoan }: PlateGroupTreeViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [translate, setTranslate] = useState({ x: 400, y: 60 });
  const { data: locations } = useStorageLocations();
  const locationName = (id: string | null | undefined) =>
    id ? (locations?.find((l) => l.id === id)?.name ?? null) : null;

  // Memoize on the root: react-d3-tree resets expand/collapse whenever `data`
  // changes identity, so selection re-renders must not rebuild it.
  const nodesById = useMemo(() => indexNodes(root), [root]);
  const data = useMemo<GroupDatum>(() => toDatum(root), [root]);
  const legend = useMemo(() => legendEntries([root]), [root]);

  useEffect(() => {
    const el = containerRef.current;
    if (el && el.clientWidth > 0) setTranslate({ x: el.clientWidth / 2, y: 60 });
  }, []);

  const renderNode = ({ nodeDatum, toggleNode, hierarchyPointNode }: CustomNodeElementProps) => {
    const id = (nodeDatum.attributes as unknown as GroupDatum["attributes"]).id;
    const node = nodesById.get(id);
    if (!node) return <g />;
    const isRoot = hierarchyPointNode.depth === 0;
    const r = isRoot ? ROOT_R : CIRCLE_R;
    return (
      <g>
        <circle
          r={r}
          style={{ fill: stateColor(node.state) }}
          className={id === selectedId ? "stroke-primary" : "stroke-border"}
          strokeWidth={id === selectedId ? 3 : 1}
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            toggleNode();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              toggleNode();
            }
          }}
          data-testid={`tree-toggle-${id}`}
        />
        <foreignObject x={r + 6} y={-CARD_HEIGHT / 2} width={CARD_WIDTH} height={CARD_HEIGHT}>
          <PlateGroupCard
            node={node}
            locationName={locationName(node.storage_location_id)}
            selected={id === selectedId}
            onSelect={() => onSelect(node)}
            onRequestLoan={() => onRequestLoan(node)}
          />
        </foreignObject>
      </g>
    );
  };

  return (
    // Chrome above this box measures ~260px at 1600×900 (top nav + PageHeader +
    // tabs) — 16.25rem, not the old 12rem, per docs/backlog/plate-groups-tree-viewport-overflow-baseline.md.
    <div className="flex h-[calc(100vh-16.25rem)] min-h-[480px] flex-col gap-2">
      {legend.states.length + legend.types.length > 0 ? (
        <div className="flex shrink-0 flex-wrap gap-x-6 gap-y-1" data-testid="plate-group-tree-legend">
          <LegendRow title="State" entries={legend.states} />
          <LegendRow title="Type" entries={legend.types} />
        </div>
      ) : null}
      <div ref={containerRef} className="min-h-0 w-full flex-1 rounded-md border bg-card" data-testid="plate-group-tree">
        <Tree
          data={data}
          orientation="vertical"
          pathFunc="elbow"
          translate={translate}
          initialDepth={5}
          zoom={0.7}
          scaleExtent={{ min: 0.1, max: 1.5 }}
          collapsible
          zoomable
          nodeSize={NODE_SIZE}
          renderCustomNodeElement={renderNode}
        />
      </div>
    </div>
  );
}

function LegendRow({ title, entries }: { title: string; entries: { label: string; color: string }[] }) {
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <span className="font-medium">{title}</span>
      {entries.map((e) => (
        <span key={e.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: e.color }} />
          {e.label}
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Dashboard — root selector, request-loan dialog**

In `plate-group-dashboard.tsx`:
- imports: `ROOT_STORAGE_KEY` from `./plate-group-tree-utils`, `RequestLoanDialog` from `./request-loan-dialog`.
- state: `const [rootId, setRootId] = useState<string | null>(null); const [loanGroup, setLoanGroup] = useState<PlateGroupNode | null>(null);`
- after the tree query, derive `const roots = tree?.roots ?? [];` and an effect that (re)selects the root when the org or the tree changes:

```tsx
  useEffect(() => {
    if (!orgId || roots.length === 0) return;
    if (rootId && roots.some((r) => r.id === rootId)) return;
    let remembered: string | null = null;
    try {
      remembered = window.localStorage.getItem(ROOT_STORAGE_KEY(orgId));
    } catch {
      remembered = null;
    }
    const next = roots.find((r) => r.id === remembered)?.id ?? roots[0].id;
    setRootId(next);
  }, [orgId, roots, rootId]);

  const selectRoot = (id: string) => {
    setRootId(id);
    setSelected(null);
    try {
      if (orgId) window.localStorage.setItem(ROOT_STORAGE_KEY(orgId), id);
    } catch {
      /* storage unavailable — selection is per-session only */
    }
  };
  const rootNode = roots.find((r) => r.id === rootId) ?? null;
```
- reset `rootId` to `null` inside the org `<Select>`'s `onValueChange` (next to `setSelected(null)`).
- in the `<PageHeader>`, before the admin-only org select, render the root selector when `roots.length > 0`:

```tsx
        <Select value={rootId ?? ""} onValueChange={selectRoot}>
          <SelectTrigger className="w-64" aria-label="Root group" data-testid="root-group-select">
            <SelectValue placeholder="Root group" />
          </SelectTrigger>
          <SelectContent>
            {roots.map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {r.name} ({r.plate_count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
```
- replace `<PlateGroupTreeView tree={tree} …/>` with `{rootNode ? <PlateGroupTreeView root={rootNode} selectedId={selectedNode?.id ?? null} onSelect={setSelected} onRequestLoan={(n) => setLoanGroup(n)} /> : null}`.
- mount `<RequestLoanDialog open={loanGroup !== null} onOpenChange={(o) => { if (!o) setLoanGroup(null); }} orgId={orgId ?? undefined} initialGroupId={loanGroup?.id} />` next to the other dialogs.

`request-loan-dialog.tsx`: add `initialGroupId?: string` to `RequestLoanDialogProps`, destructure it, and in the reset effect use `setGroupId(initialGroupId ?? "")` (add `initialGroupId` to the effect deps).

- [ ] **Step 6: Type-check, lint, test, and a real-browser check**

Run from `frontend/`: `/Users/sidx/Library/pnpm/pnpm tsc --noEmit && /Users/sidx/Library/pnpm/pnpm biome check src/features/inventory/components/plate-group-tree-utils.ts src/features/inventory/components/plate-group-tree-utils.test.ts src/features/inventory/components/plate-group-tree.tsx src/features/inventory/components/plate-group-card.tsx src/features/inventory/components/plate-group-dashboard.tsx src/features/inventory/components/request-loan-dialog.tsx; echo "biome exit=$?" && /Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory`
Expected: tsc clean, `biome exit=0`, tests PASS.

Then, with the dev servers running (`make dev-be` is up; frontend on `:3000`), open `http://localhost:3000/inventory/plate-groups` and confirm: a root selector appears, the tree is vertical with elbow links, circles are state-colored, cards show the metadata rows, the legend has State and Type rows, clicking a circle collapses/expands, "Details" opens the side panel, "Request loan" opens the loan dialog with the group preselected, and the page does not need extra scroll at a 1600×900 window (measure `document.documentElement.scrollHeight - window.innerHeight` ≤ 0 in the console). Note anything off in your report rather than papering over it.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/inventory/components/plate-group-card.tsx
git commit -m "feat(frontend): legacy-parity plate group tree — vertical elbow layout, state-colored circles, type-colored metadata cards, root selector, legend, Request loan from a card

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- frontend/src/features/inventory/components/plate-group-card.tsx frontend/src/features/inventory/components/plate-group-tree-utils.ts frontend/src/features/inventory/components/plate-group-tree-utils.test.ts frontend/src/features/inventory/components/plate-group-tree.tsx frontend/src/features/inventory/components/plate-group-dashboard.tsx frontend/src/features/inventory/components/request-loan-dialog.tsx
```

---

### Task 6: Suites, spec sync note, backlog close-out (controller, inline)

- [ ] **Step 1:** `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest -q` → green except the 11 pre-existing; `cd frontend && /Users/sidx/Library/pnpm/pnpm vitest run` → green.
- [ ] **Step 2:** Append an "S8 sync note" to the spec (Float-not-Numeric deviation; viewport fix = recalibrated `16.25rem` constant rather than a flex slot; root selector lives in the dashboard header; anything else the implementers reported), and delete `docs/backlog/plate-groups-tree-viewport-overflow-baseline.md` (closed) with a one-line pointer in the sync note.
- [ ] **Step 3:** Commit docs (`git add -f` for the spec/plan; `git rm` the backlog file), comment on issue #71.
