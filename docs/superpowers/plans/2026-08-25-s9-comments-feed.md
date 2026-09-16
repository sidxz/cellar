# S9 — Comments Feed + Mandatory Return Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An append-only comment feed on plate loans, plate groups and plates (the legacy tracker's activity log), a mandatory per-group comment when a borrower requests a return, and the UI to read/write them.

**Architecture:** New `Comment` aggregate in the inventory context (polymorphic `target_type`/`target_id`, optional `loan_id` context link, denormalized `author_name`), table `plate_comments` (migration 068), `AddComment`/`ListComments` use cases that resolve the target through the existing visibility predicates, `GET/POST /api/v1/comments`. `RequestLoanReturn` gains a `_validate` hook that enforces one non-empty comment per distinct group among the returning plates and writes the comments in the same unit of work. Loan item responses gain `group_id`/`group_name` (borrowers cannot see the owner's group tree under strict visibility). FE: `CommentFeed` on LoanCard / group side panel / plate detail, and a `RequestReturnDialog`.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / pytest (testcontainers) · Next.js 16 / React 19 / TanStack Query / shadcn (`textarea`, `collapsible`) / vitest · orval.

**Spec:** `docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md` §7.

## Global Constraints

- Backend from `backend/` with `uv run …`; pytest touching `tests/api`/`tests/integration` needs `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`. Frontend from `frontend/` with `/Users/sidx/Library/pnpm/pnpm`.
- Layer rules: Domain imports nothing; Application never imports Infrastructure/Interface. Protocol wideners must sweep **every** structural implementer of `AuthContext` (`tests/fakes/fake_auth.py::FakeAuth` — already has `name`/`email`; `application/export/row_streams/search_results.py::_AuthShim` — does not).
- Lint scoped to touched files (`uv run ruff check <files>`, `pnpm biome check <files>`); never `--fix`/`--write` repo-wide. Pre-existing failures (ignore): the 11 in `docs/backlog/preexisting-test-lint-failures-main.md`.
- Comment rules (spec §7): `target_type ∈ {plate_loan, plate_group, plate}`; `body` stripped, 1..5000 chars; `author_id` nullable (legacy import), `author_name` ≤ 200 denormalized at write; **no edit/delete**; hidden target == 404; write requires editor; reads require viewer. A comment's `loan_id`, when given, must be a visible loan that actually contains the target (a group among its plates' groups, or the plate itself).
- Visibility for the plate target uses `can_view(plate, auth, excluded, borrowed)` **with** the borrowed set on both read and write — a deliberate, documented exception to `plate_visibility.py`'s write-path narrowing (a borrower annotates the plates it holds).
- Mandatory return comments: for every distinct non-null `group_id` among the plates whose items are being return-requested, a non-empty `comments[].body` for that `group_id` must be present → else `ValidationError` (422) naming the missing groups. Ungrouped plates need nothing (so existing `json={}` call sites keep working). Kiosk `confirm` and admin `confirm-in` are untouched.
- `Comment` keeps a `version` column (ruling R13) purely for `SQLAlchemyRepository` uniformity — it is never bumped after insert.
- New ORM model modules must be imported in `backend/alembic/env.py` and `backend/tests/unit/cascade/test_fk_coverage.py` (the kiosk line at each is the template); `plate_comments.loan_id` (ON DELETE SET NULL) goes into that test's `IGNORED_FKS` with a comment.
- Commits: explicit pathspec (`git add` new files first); each message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu`. Branch `feat/plate-tracker-revamp`.
- Orval regen with the backend on `:8000` (running with `--reload`); generated types never hand-rolled; `index.ts` never pruned by orval.

---

### Task 1: `Comment` aggregate, repository, ORM, migration 068

**Files:**
- Modify: `backend/src/cellar/domain/inventory/enums.py` (add `CommentTarget`)
- Modify: `backend/src/cellar/domain/inventory/events.py` (add `CommentAdded`)
- Create: `backend/src/cellar/domain/inventory/comment.py`
- Modify: `backend/src/cellar/domain/inventory/repository.py` (add `CommentRepository` protocol)
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_repository.py`
- Create: `backend/alembic/versions/068_plate_comments.py`
- Modify: `backend/alembic/env.py` (import line next to the kiosk one), `backend/tests/unit/cascade/test_fk_coverage.py` (import + `IGNORED_FKS` entry)
- Test: `backend/tests/unit/test_comment.py` (new), `backend/tests/integration/inventory/test_comment_repository.py` (new)

**Interfaces:**
- Produces: `CommentTarget(StrEnum)`: `PLATE_LOAN="plate_loan"`, `PLATE_GROUP="plate_group"`, `PLATE="plate"`. `Comment.create(*, workspace_id, target_type: CommentTarget, target_id: uuid.UUID, body: str, author_id: uuid.UUID | None, author_name: str, loan_id: uuid.UUID | None = None) -> Comment` (validates body 1..5000 after strip, author_name 1..200 after strip; emits `CommentAdded(user_id=author_id, target_type, target_id, loan_id)`). `CommentRepository`: `list_for_target(workspace_id, target_type, target_id) -> list[Comment]` (newest first), `list_for_loan(workspace_id, loan_id) -> list[Comment]` (newest first), `save(comment)`. Constants `MAX_COMMENT_BODY = 5000`, `MAX_AUTHOR_NAME = 200`.

- [ ] **Step 1: Failing unit tests**

Create `backend/tests/unit/test_comment.py`:

```python
"""Unit tests for the append-only Comment aggregate."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.comment import MAX_COMMENT_BODY, Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.domain.inventory.events import CommentAdded
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
USER = uuid.uuid4()


def _comment(**over) -> Comment:
    kwargs = dict(
        workspace_id=WS,
        target_type=CommentTarget.PLATE_LOAN,
        target_id=uuid.uuid4(),
        body="  0.5 uL taken for NadE screening  ",
        author_id=USER,
        author_name="  Jane Doe ",
    )
    kwargs.update(over)
    return Comment.create(**kwargs)


def test_create_strips_and_emits_event_with_actor() -> None:
    loan = uuid.uuid4()
    c = _comment(loan_id=loan)
    assert c.body == "0.5 uL taken for NadE screening"
    assert c.author_name == "Jane Doe"
    assert c.loan_id == loan
    events = c.collect_events()
    assert len(events) == 1 and isinstance(events[0], CommentAdded)
    assert events[0].user_id == USER
    assert events[0].target_type == CommentTarget.PLATE_LOAN
    assert events[0].aggregate_type == "Comment"


def test_legacy_author_may_have_no_user_id() -> None:
    c = _comment(author_id=None, author_name="Legacy Scientist")
    assert c.author_id is None
    assert c.collect_events()[0].user_id is None


@pytest.mark.parametrize("body", ["", "   ", "x" * (MAX_COMMENT_BODY + 1)])
def test_body_validation(body: str) -> None:
    with pytest.raises(ValidationError):
        _comment(body=body)


@pytest.mark.parametrize("name", ["", "  ", "x" * 201])
def test_author_name_validation(name: str) -> None:
    with pytest.raises(ValidationError):
        _comment(author_name=name)
```

Run: `cd backend && uv run pytest tests/unit/test_comment.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 2: Enum + event + aggregate**

`domain/inventory/enums.py` — append:

```python
class CommentTarget(StrEnum):
    """What a plate-tracking comment is attached to (spec 2026-08-25 §7)."""

    PLATE_LOAN = "plate_loan"
    PLATE_GROUP = "plate_group"
    PLATE = "plate"
```

`domain/inventory/events.py` — append (import `CommentTarget` from `.enums` if the module doesn't already import from it; keep the file's existing import style):

```python
@dataclass(frozen=True, kw_only=True)
class CommentAdded(DomainEvent):
    """A comment was appended to a loan / group / plate. ``user_id`` feeds the
    audit catch-all's actor attribution (None for migrated legacy authors)."""

    target_type: CommentTarget
    target_id: uuid.UUID
    loan_id: uuid.UUID | None
    user_id: uuid.UUID | None
```

Create `domain/inventory/comment.py`:

```python
"""Comment — an append-only note on a plate loan, plate group, or plate.

The legacy plate tracker's activity log: free text a scientist leaves on a
transaction, and the mandatory "what did you do with these plates" note per
set at check-in. Comments are never edited or deleted (audit alignment).
``loan_id`` is the context link: a group/plate comment written while
returning a loan carries that loan so the loan card can show it too.
``author_name`` is denormalized at write time (legacy authors have no user id).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.inventory.enums import CommentTarget
from cellar.domain.inventory.events import CommentAdded
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

MAX_COMMENT_BODY = 5000
MAX_AUTHOR_NAME = 200


def _required_text(value: str | None, *, max_len: int, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{label} must not be empty")
    if len(cleaned) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters")
    return cleaned


class Comment(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        target_type: CommentTarget,
        target_id: uuid.UUID,
        body: str,
        author_id: uuid.UUID | None,
        author_name: str,
        loan_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.target_type = target_type
        self.target_id = target_id
        self.body = _required_text(body, max_len=MAX_COMMENT_BODY, label="body")
        self.author_id = author_id
        self.author_name = _required_text(author_name, max_len=MAX_AUTHOR_NAME, label="author_name")
        self.loan_id = loan_id

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        target_type: CommentTarget,
        target_id: uuid.UUID,
        body: str,
        author_id: uuid.UUID | None,
        author_name: str,
        loan_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ) -> Comment:
        """``created_at`` is only for the legacy importer (historical timestamps)."""
        comment = cls(
            workspace_id=workspace_id,
            target_type=target_type,
            target_id=target_id,
            body=body,
            author_id=author_id,
            author_name=author_name,
            loan_id=loan_id,
            created_at=created_at,
        )
        comment.register_event(
            CommentAdded(
                aggregate_id=comment.id,
                aggregate_type="Comment",
                workspace_id=workspace_id,
                target_type=target_type,
                target_id=target_id,
                loan_id=loan_id,
                user_id=author_id,
            )
        )
        return comment
```
(If `AggregateRoot.__init__` does not accept `created_at=None` as "now", check `domain/shared/entity.py` and mirror what `PlateGroup` does — it passes `created_at` straight through.)

- [ ] **Step 3: Repository protocol, ORM model, SQLAlchemy repo**

`domain/inventory/repository.py` — append (imports: `Comment`, `CommentTarget`):

```python
@runtime_checkable
class CommentRepository(Protocol):
    """Append-only comments on loans / groups / plates (spec 2026-08-25 §7)."""

    async def list_for_target(
        self, workspace_id: uuid.UUID, target_type: CommentTarget, target_id: uuid.UUID
    ) -> list[Comment]: ...
    async def list_for_loan(self, workspace_id: uuid.UUID, loan_id: uuid.UUID) -> list[Comment]: ...
    async def save(self, aggregate: Comment) -> None: ...
```

Create `infrastructure/persistence/sqlalchemy/inventory/comment_models.py`:

```python
"""ORM model for plate_comments (spec 2026-08-25 §7.2)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class CommentModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Polymorphic target (no FK on target_id — same stance as plate_loan_items.plate_id);
    loan_id is a real FK so a deleted loan just detaches its comments."""

    __tablename__ = "plate_comments"

    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("plate_loans.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index("ix_plate_comments_ws_target", "workspace_id", "target_type", "target_id", "created_at"),
        Index("ix_plate_comments_ws_loan", "workspace_id", "loan_id"),
    )
```

Create `infrastructure/persistence/sqlalchemy/inventory/comment_repository.py`:

```python
"""SQLAlchemy repository for Comment aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.inventory.comment_models import CommentModel


class SQLAlchemyCommentRepository(SQLAlchemyRepository[Comment, CommentModel]):
    model_class = CommentModel

    async def list_for_target(
        self, workspace_id: uuid.UUID, target_type: CommentTarget, target_id: uuid.UUID
    ) -> list[Comment]:
        stmt = (
            select(CommentModel)
            .where(
                CommentModel.workspace_id == workspace_id,
                CommentModel.target_type == target_type.value,
                CommentModel.target_id == target_id,
            )
            .order_by(CommentModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_for_loan(self, workspace_id: uuid.UUID, loan_id: uuid.UUID) -> list[Comment]:
        stmt = (
            select(CommentModel)
            .where(CommentModel.workspace_id == workspace_id, CommentModel.loan_id == loan_id)
            .order_by(CommentModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    # --- Mapping ---

    def _to_domain(self, model: CommentModel) -> Comment:
        return Comment(
            id=model.id,
            workspace_id=model.workspace_id,
            target_type=CommentTarget(model.target_type),
            target_id=model.target_id,
            body=model.body,
            author_id=model.author_id,
            author_name=model.author_name,
            loan_id=model.loan_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Comment) -> CommentModel:
        model = CommentModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            target_type=aggregate.target_type.value,
            target_id=aggregate.target_id,
            loan_id=aggregate.loan_id,
            body=aggregate.body,
            author_id=aggregate.author_id,
            author_name=aggregate.author_name,
            version=aggregate.version,
        )
        if aggregate.created_at is not None:
            model.created_at = aggregate.created_at  # legacy importer supplies history
        return model

    def _update_model(self, model: CommentModel, aggregate: Comment) -> None:
        # Append-only: nothing mutable after insert.
        return None
```

- [ ] **Step 4: Migration 068 + model-import registrations**

Create `backend/alembic/versions/068_plate_comments.py`:

```python
"""068 — plate_comments (spec 2026-08-25 §7)

Append-only comments on plate loans / groups / plates. target_id has no FK
(polymorphic); loan_id is a context link that survives loan deletion as NULL.

Revision ID: 068_plate_comments
Revises: 067_plate_group_metadata
"""

import sqlalchemy as sa
from alembic import op

revision = "068_plate_comments"
down_revision = "067_plate_group_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plate_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("loan_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["loan_id"], ["plate_loans.id"], name="fk_plate_comments_loan", ondelete="SET NULL"),
    )
    op.create_index("ix_plate_comments_ws_target", "plate_comments", ["workspace_id", "target_type", "target_id", "created_at"])
    op.create_index("ix_plate_comments_ws_loan", "plate_comments", ["workspace_id", "loan_id"])


def downgrade() -> None:
    op.drop_index("ix_plate_comments_ws_loan", table_name="plate_comments")
    op.drop_index("ix_plate_comments_ws_target", table_name="plate_comments")
    op.drop_table("plate_comments")
```

`backend/alembic/env.py`: add `import cellar.infrastructure.persistence.sqlalchemy.inventory.comment_models  # noqa: F401` next to the kiosk import. `backend/tests/unit/cascade/test_fk_coverage.py`: same import next to the kiosk one, and add `("plate_comments", "loan_id", "plate_loans"),  # SET NULL by design — a deleted loan detaches its comments` to `IGNORED_FKS`.

- [ ] **Step 5: Integration test for the repository**

Create `backend/tests/integration/inventory/test_comment_repository.py` (copy the fixture usage — `session_factory` — from `tests/integration/inventory/test_kiosk_device_repository.py`):

```python
"""Comment repository round-trip + ordering against real Postgres."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.infrastructure.persistence.sqlalchemy.inventory.comment_repository import (
    SQLAlchemyCommentRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.integration
async def test_round_trip_and_newest_first(session_factory) -> None:
    ws = uuid.uuid4()
    target = uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCommentRepository(uow)
        for i in range(3):
            await repo.save(
                Comment.create(
                    workspace_id=ws,
                    target_type=CommentTarget.PLATE_GROUP,
                    target_id=target,
                    body=f"note {i}",
                    author_id=None,
                    author_name="Legacy",
                )
            )
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCommentRepository(uow)
        rows = await repo.list_for_target(ws, CommentTarget.PLATE_GROUP, target)
    assert [c.body for c in rows] == ["note 2", "note 1", "note 0"]
    assert rows[0].author_id is None and rows[0].author_name == "Legacy"
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCommentRepository(uow)
        assert await repo.list_for_loan(ws, uuid.uuid4()) == []
```

- [ ] **Step 6: Run + lint**

Run: `uv run pytest tests/unit/test_comment.py tests/unit/cascade/test_fk_coverage.py -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/inventory/test_comment_repository.py -q && uv run alembic heads && uv run ruff check src/cellar/domain/inventory/comment.py src/cellar/domain/inventory/enums.py src/cellar/domain/inventory/events.py src/cellar/domain/inventory/repository.py src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_models.py src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_repository.py alembic/versions/068_plate_comments.py alembic/env.py tests/unit/test_comment.py tests/unit/cascade/test_fk_coverage.py tests/integration/inventory/test_comment_repository.py`
Expected: PASS; single head `068_plate_comments`; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/domain/inventory/comment.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_repository.py backend/alembic/versions/068_plate_comments.py backend/tests/unit/test_comment.py backend/tests/integration/inventory/test_comment_repository.py
git commit -m "feat(inventory): append-only Comment aggregate on loans/groups/plates (migration 068)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/domain/inventory backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/comment_repository.py backend/alembic/versions/068_plate_comments.py backend/alembic/env.py backend/tests/unit/test_comment.py backend/tests/unit/cascade/test_fk_coverage.py backend/tests/integration/inventory/test_comment_repository.py
```

---

### Task 2: `AuthContext.name/email`, `AddComment`/`ListComments`, `/api/v1/comments`

**Files:**
- Modify: `backend/src/cellar/application/auth.py:18-43` (`AuthContext` gains `name`, `email`)
- Modify: `backend/src/cellar/application/export/row_streams/search_results.py:480-520` (`_AuthShim` gains both)
- Modify: `backend/src/cellar/interface/routes/user.py:37-38` (direct attribute access)
- Create: `backend/src/cellar/application/inventory/comments.py`
- Create: `backend/src/cellar/interface/routes/comments.py`
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py` (two factories), `backend/src/cellar/interface/dependencies/_inventory.py` (`AddCommentDep`, `ListCommentsDep` + `__all__`), `backend/src/cellar/interface/app.py` (include router), `backend/tests/api/conftest.py` (include router)
- Test: `backend/tests/api/test_comments.py` (new)

**Interfaces:**
- Consumes: Task 1's `Comment`, `CommentTarget`, `CommentRepository`, `SQLAlchemyCommentRepository`.
- Produces: `AddCommentCommand(workspace_id, target_type: CommentTarget, target_id, body, loan_id=None)`; `ListCommentsQuery(workspace_id, target_type=None, target_id=None, loan_id=None)` (exactly one of target/loan forms); use cases `AddComment(uow, comment_repo, plate_repo, group_repo, loan_repo, dispatcher, visibility)` and `ListComments(uow, comment_repo, plate_repo, group_repo, loan_repo, visibility)`; module helper `async def resolve_target_visible(...) -> DomainError | None` reused by Task 3; routes `GET /api/v1/comments`, `POST /api/v1/comments` → `CommentResponse{id, target_type, target_id, loan_id, body, author_id, author_name, created_at}`.

- [ ] **Step 1: Failing API tests**

Create `backend/tests/api/test_comments.py` (helpers copied from `test_plate_loans.py` — `_mk_plate`, `_mk_group`, `_mk_loan`, `_set_policy`; fixtures `client` admin / `editor_client_own_org` / `editor_client_other_org` / `viewer_client`; constants from `tests.api.conftest`):

```python
"""Comments API — feed on loans/groups/plates with visibility (spec 2026-08-25 §7)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID


async def _mk_plate(client: AsyncClient, barcode: str, **overrides) -> dict:
    body = {"barcode": barcode, "plate_label": barcode, "format": "96", "plate_type": "assay", **overrides}
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_group(client: AsyncClient, name: str, **overrides) -> dict:
    resp = await client.post("/api/v1/plate-groups", json={"name": name, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_loan(client: AsyncClient, **body) -> dict:
    resp = await client.post("/api/v1/plate-loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _post(client: AsyncClient, **body) -> object:
    return await client.post("/api/v1/comments", json=body)


class TestAddAndList:
    async def test_group_comment_round_trips_with_author_name(
        self, editor_client_own_org: AsyncClient, client: AsyncClient
    ) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        resp = await _post(editor_client_own_org, target_type="plate_group", target_id=g["id"], body="  screened vs NadE  ")
        assert resp.status_code == 201, resp.text
        c = resp.json()
        assert c["body"] == "screened vs NadE"
        assert c["author_name"] == "Test User"
        assert c["loan_id"] is None
        listed = await editor_client_own_org.get("/api/v1/comments", params={"target_type": "plate_group", "target_id": g["id"]})
        assert listed.status_code == 200, listed.text
        assert [x["id"] for x in listed.json()] == [c["id"]]

    async def test_newest_first(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        for body in ("first", "second"):
            assert (await _post(client, target_type="plate", target_id=plate["id"], body=body)).status_code == 201
        listed = await client.get("/api/v1/comments", params={"target_type": "plate", "target_id": plate["id"]})
        assert [x["body"] for x in listed.json()] == ["second", "first"]

    async def test_loan_comment_and_loan_feed(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await _post(client, target_type="plate_loan", target_id=loan["id"], body="By Friday")
        assert resp.status_code == 201, resp.text
        # a plate comment made in the context of this loan shows up on the loan feed too
        resp = await _post(client, target_type="plate", target_id=plate["id"], loan_id=loan["id"], body="removed 12.5 uL")
        assert resp.status_code == 201, resp.text
        feed = await client.get("/api/v1/comments", params={"loan_id": loan["id"]})
        assert feed.status_code == 200, feed.text
        assert sorted(x["body"] for x in feed.json()) == ["By Friday", "removed 12.5 uL"]

    async def test_loan_context_must_contain_target(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        other = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await _post(client, target_type="plate", target_id=other["id"], loan_id=loan["id"], body="x")
        assert resp.status_code == 422, resp.text


class TestValidation:
    async def test_empty_body_422(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        assert (await _post(client, target_type="plate", target_id=plate["id"], body="   ")).status_code == 422

    async def test_unknown_target_type_422(self, client: AsyncClient) -> None:
        assert (await _post(client, target_type="batch", target_id=str(uuid.uuid4()), body="x")).status_code == 422

    async def test_list_requires_exactly_one_form(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/comments")).status_code == 422
        assert (await client.get("/api/v1/comments", params={"target_type": "plate"})).status_code == 422


class TestVisibility:
    async def test_hidden_plate_404_for_foreign_editor_visible_for_owner(
        self, client: AsyncClient, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID))
        assert (await _post(editor_client_own_org, target_type="plate", target_id=plate["id"], body="x")).status_code == 404
        assert (await editor_client_own_org.get("/api/v1/comments", params={"target_type": "plate", "target_id": plate["id"]})).status_code == 404
        assert (await _post(editor_client_other_org, target_type="plate", target_id=plate["id"], body="x")).status_code == 201

    async def test_borrower_can_comment_on_borrowed_plate(
        self, client: AsyncClient, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        # OTHER org lends its plate to AUTH org (owner-initiated, auto-approved)
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]], borrower_org_id=str(AUTH_ORG_ID))
        resp = await _post(editor_client_own_org, target_type="plate", target_id=plate["id"], loan_id=loan["id"], body="took 1 uL")
        assert resp.status_code == 201, resp.text

    async def test_hidden_group_and_loan_404(
        self, client: AsyncClient, editor_client_own_org: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID))
        assert (await _post(editor_client_own_org, target_type="plate_group", target_id=g["id"], body="x")).status_code == 404
        plate = await _mk_plate(editor_client_other_org, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(editor_client_other_org, plate_ids=[plate["id"]])
        assert (await _post(editor_client_own_org, target_type="plate_loan", target_id=loan["id"], body="x")).status_code == 404
        assert (await editor_client_own_org.get("/api/v1/comments", params={"loan_id": loan["id"]})).status_code == 404

    async def test_viewer_can_read_not_write(self, client: AsyncClient, viewer_client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        assert (await _post(client, target_type="plate", target_id=plate["id"], body="x")).status_code == 201
        assert (await viewer_client.get("/api/v1/comments", params={"target_type": "plate", "target_id": plate["id"]})).status_code == 200
        assert (await _post(viewer_client, target_type="plate", target_id=plate["id"], body="y")).status_code == 403
```
(`viewer_client` is in conftest — confirm its org; if it has no `org_id`, the viewer's excluded set is "every org" and the read 404s: give the test a viewer in `AUTH_ORG_ID` via the `_client_as` pattern instead.)

Run: `DOCKER_HOST=… uv run pytest tests/api/test_comments.py -q` → FAIL (404 route missing).

- [ ] **Step 2: Widen `AuthContext`**

`application/auth.py` — add to the Protocol after `org_slug`:
```python
    @property
    def name(self) -> str: ...

    @property
    def email(self) -> str: ...
```
`_AuthShim` (`search_results.py`): add `name` → `return ""` and `email` → `return ""` properties with a one-line comment (exports have no display identity). `interface/routes/user.py`: `email=auth.email, name=auth.name`.

- [ ] **Step 3: Use cases**

Create `application/inventory/comments.py`:

```python
"""Comment use cases — append-only feed on loans / groups / plates (spec 2026-08-25 §7)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_loans import _loan_visible
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.domain.inventory.repository import (
    CommentRepository,
    PlateGroupRepository,
    PlateLoanRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class AddCommentCommand(Command):
    workspace_id: uuid.UUID
    target_type: CommentTarget
    target_id: uuid.UUID
    body: str
    loan_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ListCommentsQuery(Query):
    workspace_id: uuid.UUID
    target_type: CommentTarget | None = None
    target_id: uuid.UUID | None = None
    loan_id: uuid.UUID | None = None


@dataclass
class TargetRepos:
    plate_repo: RegisteredPlateRepository
    group_repo: PlateGroupRepository
    loan_repo: PlateLoanRepository


async def resolve_target_visible(
    *,
    repos: TargetRepos,
    visibility: PlateVisibilityService,
    workspace_id: uuid.UUID,
    auth: AuthContext | None,
    target_type: CommentTarget,
    target_id: uuid.UUID,
) -> DomainError | None:
    """None when the caller may see the target; NotFoundError otherwise (hidden == missing).
    Plate targets use the borrowed carve-out on purpose: a borrower annotates the
    plates it holds (documented exception to plate_visibility's write narrowing)."""
    excluded = await visibility.excluded_org_ids(workspace_id, auth)
    if target_type is CommentTarget.PLATE:
        plate = await repos.plate_repo.find_by_id_in_workspace(workspace_id, target_id)
        borrowed = await visibility.borrowed_plate_ids(workspace_id, auth)
        if plate is None or not visibility.can_view(plate, auth, excluded, borrowed):
            return NotFoundError("RegisteredPlate", str(target_id))
        return None
    if target_type is CommentTarget.PLATE_GROUP:
        group = await repos.group_repo.find_by_id_in_workspace(workspace_id, target_id)
        if group is None or not visibility.can_view_owner(group.owner_org_id, excluded):
            return NotFoundError("PlateGroup", str(target_id))
        return None
    loan = await repos.loan_repo.find_by_id_in_workspace(workspace_id, target_id)
    if loan is None or not _loan_visible(loan, auth, excluded):
        return NotFoundError("PlateLoan", str(target_id))
    return None


async def _loan_contains_target(
    repos: TargetRepos, workspace_id: uuid.UUID, loan_id: uuid.UUID,
    target_type: CommentTarget, target_id: uuid.UUID,
) -> bool:
    loan = await repos.loan_repo.find_by_id_in_workspace(workspace_id, loan_id)
    if loan is None:
        return False
    plate_ids = [i.plate_id for i in loan.items]
    if target_type is CommentTarget.PLATE_LOAN:
        return loan.id == target_id
    if target_type is CommentTarget.PLATE:
        return target_id in plate_ids
    plates = await repos.plate_repo.find_by_ids(workspace_id, plate_ids)
    return any(p.group_id == target_id for p in plates)


class AddComment:
    def __init__(
        self,
        uow: UnitOfWork,
        comment_repo: CommentRepository,
        repos: TargetRepos,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._comments = comment_repo
        self._repos = repos
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: AddCommentCommand, auth: AuthContext | None = None
    ) -> Result[Comment, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None

        async with self._uow:
            err = await resolve_target_visible(
                repos=self._repos, visibility=self._visibility, workspace_id=input.workspace_id,
                auth=auth, target_type=input.target_type, target_id=input.target_id,
            )
            if err is not None:
                return Failure(err)
            if input.loan_id is not None:
                loan_err = await resolve_target_visible(
                    repos=self._repos, visibility=self._visibility, workspace_id=input.workspace_id,
                    auth=auth, target_type=CommentTarget.PLATE_LOAN, target_id=input.loan_id,
                )
                if loan_err is not None:
                    return Failure(loan_err)
                if not await _loan_contains_target(
                    self._repos, input.workspace_id, input.loan_id, input.target_type, input.target_id
                ):
                    return Failure(ValidationError("The loan does not contain this target"))
            comment = Comment.create(
                workspace_id=input.workspace_id,
                target_type=input.target_type,
                target_id=input.target_id,
                body=input.body,
                author_id=auth.user_id,
                author_name=auth.name or auth.email,
                loan_id=input.loan_id,
            )
            await self._comments.save(comment)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(comment)


class ListComments:
    def __init__(
        self,
        uow: UnitOfWork,
        comment_repo: CommentRepository,
        repos: TargetRepos,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._comments = comment_repo
        self._repos = repos
        self._visibility = visibility

    async def __call__(
        self, input: ListCommentsQuery, auth: AuthContext | None = None
    ) -> Result[list[Comment], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        by_target = input.target_type is not None and input.target_id is not None
        by_loan = input.loan_id is not None
        if by_target == by_loan:
            return Failure(ValidationError("Provide target_type+target_id or loan_id (not both)"))
        async with self._uow:
            if by_loan:
                assert input.loan_id is not None
                err = await resolve_target_visible(
                    repos=self._repos, visibility=self._visibility, workspace_id=input.workspace_id,
                    auth=auth, target_type=CommentTarget.PLATE_LOAN, target_id=input.loan_id,
                )
                if err is not None:
                    return Failure(err)
                return Success(await self._comments.list_for_loan(input.workspace_id, input.loan_id))
            assert input.target_type is not None and input.target_id is not None
            err = await resolve_target_visible(
                repos=self._repos, visibility=self._visibility, workspace_id=input.workspace_id,
                auth=auth, target_type=input.target_type, target_id=input.target_id,
            )
            if err is not None:
                return Failure(err)
            return Success(
                await self._comments.list_for_target(input.workspace_id, input.target_type, input.target_id)
            )
```
(`RegisteredPlateRepository.find_by_ids(workspace_id, ids)` exists — it is what `_enrich` uses.)

- [ ] **Step 4: Routes + DI + registration**

Create `interface/routes/comments.py`:

```python
"""Comment endpoints — feed on plate loans / groups / plates."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from cellar.application.inventory.comments import AddCommentCommand, ListCommentsQuery
from cellar.domain.inventory.comment import MAX_COMMENT_BODY, Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.interface.dependencies import AddCommentDep, AuthDep, ListCommentsDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/comments", tags=["comments"])


class CommentResponse(BaseModel):
    id: uuid.UUID
    target_type: CommentTarget
    target_id: uuid.UUID
    loan_id: uuid.UUID | None = None
    body: str
    author_id: uuid.UUID | None = None
    author_name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, c: Comment) -> CommentResponse:
        return cls(
            id=c.id, target_type=c.target_type, target_id=c.target_id, loan_id=c.loan_id,
            body=c.body, author_id=c.author_id, author_name=c.author_name, created_at=c.created_at,
        )


class AddCommentBody(BaseModel):
    target_type: CommentTarget
    target_id: uuid.UUID
    body: str = Field(min_length=1, max_length=MAX_COMMENT_BODY)
    loan_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


@router.get("", response_model=list[CommentResponse])
async def list_comments(
    auth: AuthDep,
    uc: ListCommentsDep,
    target_type: CommentTarget | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    loan_id: uuid.UUID | None = Query(default=None),
) -> list[CommentResponse]:
    """Comments on one target (target_type + target_id) or every comment made in a loan's context (loan_id)."""
    query = ListCommentsQuery(
        workspace_id=auth.workspace_id, target_type=target_type, target_id=target_id, loan_id=loan_id
    )
    comments = result_to_response(await uc(query, auth=auth))
    return [CommentResponse.from_domain(c) for c in comments]


@router.post("", response_model=CommentResponse, status_code=201)
async def add_comment(body: AddCommentBody, auth: AuthDep, uc: AddCommentDep) -> CommentResponse:
    command = AddCommentCommand(
        workspace_id=auth.workspace_id, target_type=body.target_type, target_id=body.target_id,
        body=body.body, loan_id=body.loan_id,
    )
    return CommentResponse.from_domain(result_to_response(await uc(command, auth=auth)))
```
(`ValidationError` from the domain maps to 422 via `result_to_response`/error handlers — the empty-body test passes through the domain strip since `"   "` has `min_length=1`.)

`infrastructure/di/_inventory.py` — add after the kiosk block:
```python
    # --- Comments ---
    def _comment_target_repos(uow: AsyncUnitOfWork) -> TargetRepos:
        return TargetRepos(
            plate_repo=SQLAlchemyRegisteredPlateRepository(uow),
            group_repo=SQLAlchemyPlateGroupRepository(uow),
            loan_repo=SQLAlchemyPlateLoanRepository(uow),
        )

    def _add_comment(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AddComment(
            uow, SQLAlchemyCommentRepository(uow), _comment_target_repos(uow), c[EventDispatcher],
            PlateVisibilityService(c[OrgDirectoryPort], SQLAlchemyPlateLoanRepository(uow)),
        )

    def _list_comments(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListComments(
            uow, SQLAlchemyCommentRepository(uow), _comment_target_repos(uow),
            PlateVisibilityService(c[OrgDirectoryPort], SQLAlchemyPlateLoanRepository(uow)),
        )

    container.define(AddComment, _add_comment)
    container.define(ListComments, _list_comments)
```
(imports at the top of the module: `AddComment, ListComments, TargetRepos` from `cellar.application.inventory.comments`; `SQLAlchemyCommentRepository`.) Note the visibility service gets the loan repo so `borrowed_plate_ids` works.

`interface/dependencies/_inventory.py`: `AddCommentDep = Annotated[AddComment, Depends(_get_use_case(AddComment))]`, `ListCommentsDep = …`, both added to `__all__` (keep it sorted). `interface/app.py` + `tests/api/conftest.py::_create_test_app`: import and `include_router` the comments router next to the plate-loan router.

- [ ] **Step 5: Run + lint**

Run: `DOCKER_HOST=… uv run pytest tests/api/test_comments.py tests/api/test_plate_loans.py tests/unit -q -k "comment or user or export" && uv run ruff check src/cellar/application/auth.py src/cellar/application/export/row_streams/search_results.py src/cellar/interface/routes/user.py src/cellar/application/inventory/comments.py src/cellar/interface/routes/comments.py src/cellar/infrastructure/di/_inventory.py src/cellar/interface/dependencies/_inventory.py src/cellar/interface/app.py tests/api/conftest.py tests/api/test_comments.py`
Expected: PASS, ruff clean. Then `uv run pytest tests/unit -q` → only the 2 known pre-existing failures.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/inventory/comments.py backend/src/cellar/interface/routes/comments.py backend/tests/api/test_comments.py
git commit -m "feat(inventory): comments API — add/list on loans, groups and plates with strict visibility; AuthContext exposes name/email

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/application/auth.py backend/src/cellar/application/export/row_streams/search_results.py backend/src/cellar/interface/routes/user.py backend/src/cellar/application/inventory/comments.py backend/src/cellar/interface/routes/comments.py backend/src/cellar/infrastructure/di/_inventory.py backend/src/cellar/interface/dependencies/_inventory.py backend/src/cellar/interface/app.py backend/tests/api/conftest.py backend/tests/api/test_comments.py
```

---

### Task 3: Mandatory per-group return comments + `group_id`/`group_name` on loan items

**Files:**
- Modify: `backend/src/cellar/domain/inventory/repository.py` (`PlateGroupRepository.find_by_ids`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py` (`find_by_ids`)
- Modify: `backend/src/cellar/application/inventory/plate_loans.py` (`LoanWithPlates.groups`, shared `enrich_loans`, `_LoanItemsUseCase` hooks, `RequestLoanReturnCommand`, `RequestLoanReturn`)
- Modify: `backend/src/cellar/interface/routes/plate_loans.py` (`LoanItemResponse.group_id/group_name`, `RequestReturnBody`, route)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py` (group repo into the loan read/verb factories; comment repo into `RequestLoanReturn`)
- Test: `backend/tests/api/test_plate_loans.py` (new class `TestReturnComments`)

**Interfaces:**
- Consumes: Task 1 `Comment`/`CommentRepository`; Task 2 nothing directly.
- Produces: `PlateGroupRepository.find_by_ids(workspace_id, ids) -> list[PlateGroup]`; `LoanWithPlates(loan, plates, groups: dict[UUID, PlateGroup])`; `async def enrich_loans(loans, *, plate_repo, group_repo) -> list[LoanWithPlates]` (batched) used by `GetLoan`, `ListLoans` and `_LoanItemsUseCase._enrich`; `_LoanItemsUseCase` hooks `async def _validate(self, loan, item_ids, input, auth) -> DomainError | None` and `async def _after_save(self, loan, item_ids, input, auth) -> None`; `RequestLoanReturnCommand(LoanItemsCommand)` with `comments: tuple[GroupComment, ...] = ()`, `plate_comments: tuple[PlateComment, ...] = ()` (`GroupComment(group_id, body)`, `PlateComment(plate_id, body)` frozen dataclasses); API `POST /plate-loans/{id}/items:request-return` body `RequestReturnBody{item_ids?, comments: [{group_id, body}] = [], plate_comments: [{plate_id, body}] = []}` (`extra: forbid`); `LoanItemResponse.group_id: UUID | None`, `group_name: str | None`.

- [ ] **Step 1: Failing API tests**

Append to `backend/tests/api/test_plate_loans.py`:

```python
class TestReturnComments:
    """Spec §7.3: one non-empty comment per distinct group among the returning plates."""

    async def _checked_out_loan_with_groups(self, client: AsyncClient) -> tuple[dict, dict, dict, dict]:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False, confirmation="none")
        g1 = await _mk_group(client, f"G1-{uuid.uuid4().hex[:6]}")
        g2 = await _mk_group(client, f"G2-{uuid.uuid4().hex[:6]}")
        p1 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        p2 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        p3 = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # ungrouped
        for gid, pid in ((g1["id"], p1["id"]), (g2["id"], p2["id"])):
            r = await client.post(f"/api/v1/plate-groups/{gid}/plates", json={"plate_ids": [pid]})
            assert r.status_code == 204, r.text
        loan = await _mk_loan(client, plate_ids=[p1["id"], p2["id"], p3["id"]])
        assert {i["status"] for i in loan["items"]} == {"checked_out"}
        return loan, g1, g2, p1

    async def test_items_expose_group(self, client: AsyncClient) -> None:
        loan, g1, g2, p1 = await self._checked_out_loan_with_groups(client)
        by_plate = {i["plate_id"]: i for i in loan["items"]}
        assert by_plate[p1["id"]]["group_id"] == g1["id"]
        assert by_plate[p1["id"]]["group_name"] == g1["name"]
        assert sum(1 for i in loan["items"] if i["group_id"] is None) == 1

    async def test_missing_group_comment_422_names_groups(self, client: AsyncClient) -> None:
        loan, g1, g2, _ = await self._checked_out_loan_with_groups(client)
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={"comments": [{"group_id": g1["id"], "body": "0.5 uL for NadE"}]},
        )
        assert resp.status_code == 422, resp.text
        assert g2["name"] in resp.text and g1["name"] not in resp.text
        # nothing moved
        got = (await client.get(f"/api/v1/plate-loans/{loan['id']}")).json()
        assert {i["status"] for i in got["items"]} == {"checked_out"}

    async def test_blank_comment_counts_as_missing(self, client: AsyncClient) -> None:
        loan, g1, g2, _ = await self._checked_out_loan_with_groups(client)
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={"comments": [{"group_id": g1["id"], "body": "  "}, {"group_id": g2["id"], "body": "ok"}]},
        )
        assert resp.status_code == 422, resp.text

    async def test_comments_written_in_loan_context(self, client: AsyncClient) -> None:
        loan, g1, g2, p1 = await self._checked_out_loan_with_groups(client)
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={
                "comments": [{"group_id": g1["id"], "body": "0.5 uL for NadE"}, {"group_id": g2["id"], "body": "untouched"}],
                "plate_comments": [{"plate_id": p1["id"], "body": "removed 12.5 uL from each well"}],
            },
        )
        assert resp.status_code == 200, resp.text
        # confirmation=none collapses request-return straight to returned
        assert {i["status"] for i in resp.json()["items"]} == {"returned"}
        feed = (await client.get("/api/v1/comments", params={"loan_id": loan["id"]})).json()
        assert sorted(c["body"] for c in feed) == ["0.5 uL for NadE", "removed 12.5 uL from each well", "untouched"]
        g1_feed = (await client.get("/api/v1/comments", params={"target_type": "plate_group", "target_id": g1["id"]})).json()
        assert [c["body"] for c in g1_feed] == ["0.5 uL for NadE"]
        assert g1_feed[0]["loan_id"] == loan["id"]

    async def test_partial_return_only_requires_groups_of_returning_items(self, client: AsyncClient) -> None:
        loan, g1, g2, p1 = await self._checked_out_loan_with_groups(client)
        item_p1 = next(i["id"] for i in loan["items"] if i["plate_id"] == p1["id"])
        resp = await client.post(
            f"/api/v1/plate-loans/{loan['id']}/items:request-return",
            json={"item_ids": [item_p1], "comments": [{"group_id": g1["id"], "body": "done"}]},
        )
        assert resp.status_code == 200, resp.text

    async def test_ungrouped_plates_need_no_comment(self, client: AsyncClient) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=False, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:request-return", json={})
        assert resp.status_code == 200, resp.text

    async def test_unknown_field_still_forbidden_on_other_verbs(self, client: AsyncClient) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(client, plate_ids=[plate["id"]])
        resp = await client.post(f"/api/v1/plate-loans/{loan['id']}/items:approve", json={"comments": []})
        assert resp.status_code == 422, resp.text
```

Run: `DOCKER_HOST=… uv run pytest tests/api/test_plate_loans.py -q -k TestReturnComments` → FAIL (`group_id` missing / 422 on `comments`).

- [ ] **Step 2: Group lookup + enrichment**

`domain/inventory/repository.py` `PlateGroupRepository`: add `async def find_by_ids(self, workspace_id: uuid.UUID, ids: list[uuid.UUID]) -> list[PlateGroup]: ...`. `plate_group_repository.py`:
```python
    async def find_by_ids(self, workspace_id: uuid.UUID, ids: list[uuid.UUID]) -> list[PlateGroup]:
        if not ids:
            return []
        stmt = select(PlateGroupModel).where(
            PlateGroupModel.workspace_id == workspace_id, PlateGroupModel.id.in_(ids)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]
```

`application/inventory/plate_loans.py`:
```python
@dataclass
class LoanWithPlates:
    loan: PlateLoan
    plates: dict[uuid.UUID, RegisteredPlate]
    groups: dict[uuid.UUID, PlateGroup] = field(default_factory=dict)


async def enrich_loans(
    loans: list[PlateLoan], *, plate_repo: RegisteredPlateRepository, group_repo: PlateGroupRepository
) -> list[LoanWithPlates]:
    """One plate fetch + one group fetch for any number of loans (no N+1)."""
    if not loans:
        return []
    ws = loans[0].workspace_id
    plate_ids = sorted({i.plate_id for loan in loans for i in loan.items})
    plates = {p.id: p for p in await plate_repo.find_by_ids(ws, plate_ids)}
    group_ids = sorted({p.group_id for p in plates.values() if p.group_id is not None})
    groups = {g.id: g for g in await group_repo.find_by_ids(ws, group_ids)}
    out: list[LoanWithPlates] = []
    for loan in loans:
        mine = {i.plate_id: plates[i.plate_id] for i in loan.items if i.plate_id in plates}
        out.append(LoanWithPlates(loan=loan, plates=mine, groups={
            gid: groups[gid] for gid in {p.group_id for p in mine.values() if p.group_id} if gid in groups
        }))
    return out
```
Give `GetLoan`, `ListLoans` and `_LoanItemsUseCase` a `group_repo: PlateGroupRepository` constructor parameter (LAST parameter) and replace their private plate-fetching with `enrich_loans` (`_enrich(loan)` → `(await enrich_loans([loan], plate_repo=self._plate_repo, group_repo=self._group_repo))[0]`; `ListLoans` → one batched call). Update every DI factory for `GetLoan`, `ListLoans` and the six verb use cases to pass `SQLAlchemyPlateGroupRepository(uow)`.

- [ ] **Step 3: Hooks + the return verb**

In `_LoanItemsUseCase.__call__`, after `item_ids` are computed and the "No eligible loan items" check:
```python
            err = await self._validate(loan, item_ids, input, auth)
            if err is not None:
                return Failure(err)
```
and after `await self._repo.save(loan)` (before `commit()`): `await self._after_save(loan, item_ids, input, auth)`. Defaults on the base class:
```python
    async def _validate(self, loan, item_ids, input, auth) -> DomainError | None:
        return None

    async def _after_save(self, loan, item_ids, input, auth) -> None:
        return None
```

Commands (next to `LoanItemsCommand`):
```python
@dataclass(frozen=True)
class GroupComment:
    group_id: uuid.UUID
    body: str


@dataclass(frozen=True)
class PlateComment:
    plate_id: uuid.UUID
    body: str


@dataclass(frozen=True, kw_only=True)
class RequestLoanReturnCommand(LoanItemsCommand):
    comments: tuple[GroupComment, ...] = ()
    plate_comments: tuple[PlateComment, ...] = ()
```

`RequestLoanReturn` — new constructor parameter `comment_repo: CommentRepository` (last), and:
```python
    async def _validate(self, loan, item_ids, input, auth) -> DomainError | None:
        if not isinstance(input, RequestLoanReturnCommand):
            return None
        returning = {i.plate_id for i in loan.items if i.id in set(item_ids)}
        plates = await self._plate_repo.find_by_ids(loan.workspace_id, sorted(returning))
        required = {p.group_id for p in plates if p.group_id is not None}
        provided = {c.group_id for c in input.comments if c.body.strip()}
        missing = required - provided
        if missing:
            groups = await self._group_repo.find_by_ids(loan.workspace_id, sorted(missing))
            names = ", ".join(sorted(g.name for g in groups)) or ", ".join(str(m) for m in sorted(missing))
            return ValidationError(f"A return comment is required for group(s): {names}")
        for pc in input.plate_comments:
            if pc.plate_id not in returning:
                return ValidationError("plate_comments may only name plates being returned")
        return None

    async def _after_save(self, loan, item_ids, input, auth) -> None:
        if not isinstance(input, RequestLoanReturnCommand) or auth is None:
            return
        author = auth.name or auth.email
        for gc in input.comments:
            if gc.body.strip():
                await self._comment_repo.save(Comment.create(
                    workspace_id=loan.workspace_id, target_type=CommentTarget.PLATE_GROUP,
                    target_id=gc.group_id, body=gc.body, author_id=auth.user_id,
                    author_name=author, loan_id=loan.id,
                ))
        for pc in input.plate_comments:
            if pc.body.strip():
                await self._comment_repo.save(Comment.create(
                    workspace_id=loan.workspace_id, target_type=CommentTarget.PLATE,
                    target_id=pc.plate_id, body=pc.body, author_id=auth.user_id,
                    author_name=author, loan_id=loan.id,
                ))
```
(The comments' `CommentAdded` events are collected by the UoW on commit like any aggregate saved through the repository — confirm `SQLAlchemyRepository.save` registers the aggregate for event collection the way `_to_domain_tracked` does; if `save` of a new aggregate does not track it, call `self._uow.track(comment)` or whatever `AsyncUnitOfWork` exposes — read `infrastructure/persistence/unit_of_work.py` and mirror what other creates do.) Also extend `_require_borrower_authority`-based `_authorize` nothing else.

- [ ] **Step 4: Route + response**

`interface/routes/plate_loans.py`:
```python
class LoanItemResponse(BaseModel):
    ...existing fields...
    group_id: uuid.UUID | None = None
    group_name: str | None = None
```
populate in `LoanResponse.from_dto` from `dto.plates[item.plate_id].group_id` and `dto.groups[group_id].name`.

```python
class GroupCommentBody(BaseModel):
    group_id: uuid.UUID
    body: str
    model_config = {"extra": "forbid"}


class PlateCommentBody(BaseModel):
    plate_id: uuid.UUID
    body: str
    model_config = {"extra": "forbid"}


class RequestReturnBody(LoanItemsBody):
    comments: list[GroupCommentBody] = []
    plate_comments: list[PlateCommentBody] = []
```
`request_loan_return` takes `body: RequestReturnBody` and builds `RequestLoanReturnCommand(workspace_id=…, loan_id=…, item_ids=body.item_ids, comments=tuple(GroupComment(c.group_id, c.body) for c in body.comments), plate_comments=tuple(PlateComment(p.plate_id, p.body) for p in body.plate_comments))`. The other five verbs keep `LoanItemsBody`.

- [ ] **Step 5: Run + lint**

Run: `DOCKER_HOST=… uv run pytest tests/api/test_plate_loans.py tests/api/test_kiosk.py tests/api/test_comments.py tests/api/test_plate_groups.py -q && uv run ruff check src/cellar/application/inventory/plate_loans.py src/cellar/interface/routes/plate_loans.py src/cellar/infrastructure/di/_inventory.py src/cellar/domain/inventory/repository.py src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py tests/api/test_plate_loans.py`
Expected: PASS (all pre-existing loan tests still green — their plates are ungrouped), ruff clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(inventory): return requests require a comment per group; loan items expose group_id/group_name

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/domain/inventory/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py backend/src/cellar/application/inventory/plate_loans.py backend/src/cellar/interface/routes/plate_loans.py backend/src/cellar/infrastructure/di/_inventory.py backend/tests/api/test_plate_loans.py
```

---

### Task 4: Frontend — comments hooks, `CommentFeed`, placements, regen

**Files:**
- Modify (regen): `frontend/src/shared/lib/api/model/*` (new `commentResponse*.ts`, `addCommentBody*.ts`, `commentTarget.ts`, `requestReturnBody*.ts`, `groupCommentBody*.ts`, `plateCommentBody*.ts`, `loanItemResponse*.ts` gains group fields, `index.ts`)
- Modify: `frontend/src/features/inventory/hooks/query-keys.ts` (`COMMENTS_KEY = ["comments"]`)
- Create: `frontend/src/features/inventory/hooks/use-comments.ts`
- Create: `frontend/src/features/inventory/components/comment-feed.tsx`
- Modify: `frontend/src/features/inventory/components/loan-card.tsx` (collapsible "Comments (n)" after the verb row), `plate-group-details.tsx` (Comments section after the plates list), `plate-detail.tsx` (Comments card after Loan History)
- Test: `frontend/src/features/inventory/components/comment-feed.test.tsx` (new), `frontend/src/features/inventory/hooks/use-comments.test.tsx` (new)

**Interfaces:**
- Consumes: Task 2/3 API.
- Produces: `useComments(scope: { targetType: CommentTarget; targetId: string } | { loanId: string }, opts?: { enabled?: boolean })` → `CommentResponse[]`; `useAddComment()` mutation `{ target_type, target_id, body, loan_id? }` invalidating `COMMENTS_KEY`; `<CommentFeed scope={…} canWrite={boolean} title?="Comments" />`.

- [ ] **Step 1: Regen** — `/Users/sidx/Library/pnpm/pnpm generate:api`; keep the additive diff.

- [ ] **Step 2: Failing tests**

`use-comments.test.tsx` (mirror `use-org-plate-policy.test.tsx`'s style — mocked `customInstance`, `QueryClientProvider` wrapper):
- `useComments({ targetType: "plate_group", targetId: "g1" })` GETs `/api/v1/comments` with `params: { target_type: "plate_group", target_id: "g1" }`;
- `useComments({ loanId: "l1" })` GETs with `params: { loan_id: "l1" }`;
- `useAddComment().mutate({ target_type: "plate", target_id: "p1", body: "x" })` POSTs `/api/v1/comments` with that body.

`comment-feed.test.tsx`: mock `customInstance` to return two comments (`author_name: "Jane Doe"`, bodies "second"/"first", `created_at` ISO strings); assert both bodies + author render, newest first; with `canWrite` a textarea + "Add comment" button exist and submitting POSTs `{ target_type, target_id, body }` then clears the textarea; with `canWrite={false}` no textarea.

- [ ] **Step 3: Hooks**

`query-keys.ts`: `export const COMMENTS_KEY = ["comments"] as const;` (match the file's existing style).

`use-comments.ts`:
```ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { AddCommentBody, CommentResponse, CommentTarget } from "@/shared/lib/api/model";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { COMMENTS_KEY, LOANS_KEY } from "./query-keys";

export type Comment = CommentResponse;
export type CommentScope = { targetType: CommentTarget; targetId: string } | { loanId: string };

function scopeParams(scope: CommentScope): Record<string, string> {
  return "loanId" in scope
    ? { loan_id: scope.loanId }
    : { target_type: scope.targetType, target_id: scope.targetId };
}

export function useComments(scope: CommentScope, opts?: { enabled?: boolean }) {
  const params = scopeParams(scope);
  return useQuery({
    queryKey: [...COMMENTS_KEY, params],
    queryFn: ({ signal }) =>
      customInstance<Comment[]>({ url: `${API_V1}/comments`, method: "GET", params, signal }),
    enabled: opts?.enabled ?? true,
  });
}

export function useAddComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddCommentBody) =>
      customInstance<Comment>({ url: `${API_V1}/comments`, method: "POST", data: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COMMENTS_KEY });
      qc.invalidateQueries({ queryKey: LOANS_KEY });
      showSuccess("Comment added");
    },
  });
}
```

- [ ] **Step 4: `CommentFeed`**

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import { Textarea } from "@/shared/components/ui/textarea";
import { formatDateTime } from "@/shared/lib/format-date";
import { useState } from "react";
import type { CommentTarget } from "@/shared/lib/api/model";
import { type CommentScope, useAddComment, useComments } from "../hooks/use-comments";

export interface CommentFeedProps {
  /** What to LIST: one target, or everything written in a loan's context. */
  scope: CommentScope;
  /** Editors may append; viewers only read. */
  canWrite: boolean;
  /** Where a new comment is POSTED. Defaults to `scope` when it is a target
   *  scope; required to enable the composer on a loanId scope (the loan card
   *  lists the whole loan context but posts to the loan itself). */
  composerTarget?: { targetType: CommentTarget; targetId: string };
  /** Extra context sent with a new comment (a group/plate comment made from a loan card). */
  loanContextId?: string;
  emptyText?: string;
}

export function CommentFeed({
  scope,
  canWrite,
  composerTarget,
  loanContextId,
  emptyText = "No comments yet.",
}: CommentFeedProps) {
  const { data: comments, isLoading } = useComments(scope);
  const add = useAddComment();
  const [draft, setDraft] = useState("");
  const postTarget = composerTarget ?? ("targetType" in scope ? scope : undefined);

  const submit = () => {
    if (!postTarget || !draft.trim()) return;
    add.mutate(
      { target_type: postTarget.targetType, target_id: postTarget.targetId, body: draft.trim(), loan_id: loanContextId ?? null },
      { onSuccess: () => setDraft("") },
    );
  };

  return (
    <div className="flex flex-col gap-3" data-testid="comment-feed">
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !comments?.length ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {comments.map((c) => (
            <li key={c.id} className="px-3 py-2 text-sm">
              <div className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{c.author_name}</span>
                <time dateTime={c.created_at}>{formatDateTime(c.created_at)}</time>
              </div>
              <p className="mt-1 whitespace-pre-wrap">{c.body}</p>
            </li>
          ))}
        </ul>
      )}
      {canWrite && postTarget ? (
        <div className="flex flex-col gap-2">
          <Textarea
            aria-label="New comment"
            rows={2}
            maxLength={5000}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a comment…"
          />
          <div>
            <Button size="sm" onClick={submit} disabled={!draft.trim() || add.isPending}>
              {add.isPending ? "Adding…" : "Add comment"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Placements**

- `loan-card.tsx`: after the verb row, a `Collapsible` (`@/shared/components/ui/collapsible`) with trigger text `Comments ({count})` — `count` from `useComments({ loanId: loan.id })` — whose content renders `<CommentFeed scope={{ loanId: loan.id }} composerTarget={{ targetType: "plate_loan", targetId: loan.id }} canWrite={canWrite} />` — the list shows every comment written in this loan's context (loan, group and plate notes from the return dialog), the composer posts a loan comment.
- `plate-group-details.tsx`: after the plates section, `<div><h3 className="mb-2 text-sm font-medium">Comments</h3><CommentFeed scope={{ targetType: "plate_group", targetId: node.id }} canWrite /></div>` (the panel is already editor-gated by the page's CRUD buttons; pass `canWrite` from `useCurrentUser` role like the loan card).
- `plate-detail.tsx`: a `Card` titled "Comments" between Loan History and Files with `<CommentFeed scope={{ targetType: "plate", targetId: plateId }} canWrite={canEditTags} />` (`canEditTags` is the file's existing editor flag).
- The `canWrite` derivation: `const { data: me } = useCurrentUser(); const canWrite = !!me && me.workspace_role !== "viewer";` — extract a tiny `useCanEdit()` helper in `frontend/src/shared/hooks/use-current-user.ts` if the same three lines would otherwise be pasted three times.

- [ ] **Step 6: Type-check, lint, test**

`/Users/sidx/Library/pnpm/pnpm tsc --noEmit && /Users/sidx/Library/pnpm/pnpm biome check <touched files>; echo "biome exit=$?" && /Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory src/shared/hooks`
Expected: clean / 0 / PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/shared/lib/api/model frontend/src/features/inventory/hooks/use-comments.ts frontend/src/features/inventory/hooks/use-comments.test.tsx frontend/src/features/inventory/components/comment-feed.tsx frontend/src/features/inventory/components/comment-feed.test.tsx
git commit -m "feat(frontend): comment feed on loan cards, group side panel and plate detail

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- frontend/src/shared/lib/api/model frontend/src/features/inventory/hooks/query-keys.ts frontend/src/features/inventory/hooks/use-comments.ts frontend/src/features/inventory/hooks/use-comments.test.tsx frontend/src/features/inventory/components/comment-feed.tsx frontend/src/features/inventory/components/comment-feed.test.tsx frontend/src/features/inventory/components/loan-card.tsx frontend/src/features/inventory/components/plate-group-details.tsx frontend/src/features/inventory/components/plate-detail.tsx frontend/src/shared/hooks/use-current-user.ts
```

---

### Task 5: Frontend — `RequestReturnDialog`

**Files:**
- Create: `frontend/src/features/inventory/components/request-return-dialog.tsx`
- Modify: `frontend/src/features/inventory/hooks/use-plate-loans.ts` (`useLoanItemsAction` vars gain optional `comments`/`plateComments`, sent only for `request-return`)
- Modify: `frontend/src/features/inventory/components/loan-card.tsx` (the `request-return` button opens the dialog instead of firing immediately)
- Test: `frontend/src/features/inventory/components/request-return-dialog.test.tsx` (new), `loan-card.test.tsx` (one case: clicking "Request return" opens the dialog)

**Interfaces:**
- Consumes: `LoanItemResponse.group_id/group_name` (Task 3), `useLoanItemsAction`.
- Produces: `RequestReturnDialog({ open, onOpenChange, loan, itemIds })` — `itemIds` = the items being returned (selected or all eligible); groups derived from those items' `group_id`/`group_name`; one required `Textarea` per group labelled `${group_name} (${barcodes.join(", ")})`; a collapsible "Per-plate notes (optional)" with one textarea per returning plate; Submit disabled until every group textarea is non-blank; on submit `action.mutate({ loanId, verb: "request-return", itemIds, comments: [{group_id, body}], plateComments: [{plate_id, body}] (non-blank only) })`.

- [ ] **Step 1: Failing tests** — `request-return-dialog.test.tsx`: a loan with items p1(g1 "Vendor A"), p2(g2 "Screen B"), p3(no group); render with all three item ids; assert two group textareas labelled with the group names, submit disabled; fill both, submit → `customInstance` called with `url` ending `items:request-return` and `data` `{ item_ids: [...], comments: [{group_id:"g1",body:"a"},{group_id:"g2",body:"b"}], plate_comments: [] }`; a second case with only p3 → no group textareas, submit enabled immediately.

- [ ] **Step 2: Hook** — `useLoanItemsAction` mutation vars: `{ loanId, verb, itemIds?, comments?: GroupCommentBody[], plateComments?: PlateCommentBody[] }`; `data` = `verb === "request-return" ? { item_ids: itemIds ?? null, comments: comments ?? [], plate_comments: plateComments ?? [] } : { item_ids: itemIds ?? null }`.

- [ ] **Step 3: Dialog + LoanCard wiring** — in `loan-card.tsx` `runVerb`, when `verb === "request-return"` set `returnTargets` state (the target item ids) and open the dialog instead of mutating; mount `<RequestReturnDialog open={returnTargets !== null} onOpenChange={(o) => !o && setReturnTargets(null)} loan={loan} itemIds={returnTargets ?? []} />`; on success clear `checked` and close.

- [ ] **Step 4: tsc / biome / vitest** as in Task 4 Step 6; then in the browser (dev servers up): request a loan on grouped plates, check out (policy admin_confirm → confirm-out as admin), click Request return → the dialog demands one note per group; submit → items `return_pending`, comments visible on the loan card's Comments and on the group side panel.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/inventory/components/request-return-dialog.tsx frontend/src/features/inventory/components/request-return-dialog.test.tsx
git commit -m "feat(frontend): Request return dialog — one mandatory note per group, optional per-plate notes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- frontend/src/features/inventory/components/request-return-dialog.tsx frontend/src/features/inventory/components/request-return-dialog.test.tsx frontend/src/features/inventory/hooks/use-plate-loans.ts frontend/src/features/inventory/components/loan-card.tsx frontend/src/features/inventory/components/loan-card.test.tsx
```

---

### Task 6: Suites, sync note, tracking (controller, inline)

- Full backend suite (`DOCKER_HOST=… uv run pytest -q`) → green except the 11 pre-existing; frontend `pnpm vitest run` + `tsc --noEmit` green.
- Spec "S9 sync note": rulings (own body model for request-return; `group_id/group_name` on loan items; `_validate`/`_after_save` hooks; `version` column kept; borrowed carve-out on plate-comment writes), deviations reported by implementers, suite counts.
- Commit docs, comment on issue #71.
