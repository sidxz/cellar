# Targets from Prot-Cellar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make prot-cellar the sole source of biological targets — chem-vault2's `targets` table becomes a read-only mirror (same UUIDs) synced from prot-cellar's API, triggered from a new admin page and refreshed best-effort on read.

**Architecture:** A `TargetSource` port (application) with an httpx adapter (`infrastructure/prot_cellar/`) pages through prot-cellar's `GET /api/v1/targets` forwarding the caller's two Duar headers (both apps share realm `daikon-siblings`). `SyncTargetsFromProtCellar` diffs by `source_version` and upserts via the existing `TargetRepository.save`. Local create/update/delete is removed end-to-end. A one-off script remaps the pre-existing saclab-dev rows.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / Lagom / dry-returns / httpx / pytest; Next.js 16 / React 19 / TanStack Query / shadcn / vitest; orval.

**Spec:** `docs/superpowers/specs/2026-08-24-targets-from-prot-cellar-design.md`

## Global Constraints

- Layer rules (CLAUDE.md): Domain depends on nothing; Application on Domain; Infrastructure on Domain+Application; Interface on all. `uv run lint-imports` enforces it.
- Every use case: `require_workspace_role`/`require_same_workspace` guards, Railway `Result`, workspace-scoped repo calls (`docs/backend-code-guidelines.md`).
- Mirror rows use prot-cellar's UUID as `targets.id` (spec D2). No new tables; one migration adds `targets.chembl_id` and `targets.source_version`.
- Sync = full cursor scan at `limit=200` until `next_cursor` is null — no cap (spec D3).
- Forward only `Authorization` and `X-Authz-Token` request headers to prot-cellar. Never the service key (spec D5).
- Error mapping reuses existing domain errors: prot-cellar 401/403 → `AuthorizationError` (HTTP 403); unreachable/timeout/5xx → `ServiceUnavailableError` (HTTP 503). *(Deviation from spec §5 which said 502 — 503 is what the existing `_ERROR_STATUS_MAP` gives; no new error classes.)*
- `SyncReport` has `fetched, created, updated, skipped` — the spec's `pages` field is dropped (the port returns a flat list).
- Frontend: never hand-write a type that mirrors a backend DTO — alias orval-generated types (CLAUDE.md "Frontend API Layer").
- Commit with explicit pathspecs: `git commit -m "..." -- <paths>` (the working tree may carry unrelated staged work).
- Backend line length 99 (`backend/ruff.toml`). Frontend: `pnpm lint` (biome) must exit 0.
- Test commands: `cd backend && uv run pytest tests/unit/ -v --tb=short && uv run lint-imports` (unit), `uv run pytest tests/api/ tests/integration/ -v --tb=short` (needs `make up` from repo root for Postgres), `cd frontend && pnpm test && pnpm lint`.

---

## File map

**Backend — create**
- `backend/alembic/versions/065_target_mirror_columns.py` — adds `chembl_id`, `source_version`.
- `backend/src/cellar/application/screening/target_source.py` — `SourceTarget` + `TargetSource` port.
- `backend/src/cellar/application/screening/sync_targets.py` — `SyncFreshness`, `SyncTargetsCommand`, `SyncReport`, `SyncTargetsFromProtCellar`.
- `backend/src/cellar/infrastructure/prot_cellar/__init__.py`, `settings.py`, `target_source.py` — `ProtCellarSettings`, `HttpTargetSource`.
- `backend/scripts/remap_targets_to_prot_cellar.py` — one-off cutover.
- Tests: `tests/unit/domain/screening_assay/test_target.py` (rewritten), `tests/unit/infrastructure/test_http_target_source.py`, `tests/unit/application/screening/test_sync_targets.py`, `tests/api/test_targets_sync.py`, `tests/integration/scripts/test_remap_targets_to_prot_cellar.py`.

**Backend — modify**
- `domain/screening_assay/enums.py` (TargetType +3), `domain/screening_assay/target.py` (fields, `from_mirror`, drop `create`/`update`), `domain/screening_assay/repository.py` (drop `count_references`).
- `infrastructure/persistence/sqlalchemy/screening_assay/models.py` (+2 columns), `.../target_repository.py` (mapping, drop `count_references`).
- `application/screening/get_target.py` (`ListTargets` best-effort refresh).
- `infrastructure/di/_screening.py`, `infrastructure/di/container.py` (`overrides` seam).
- `interface/dependencies/_screening.py`, `interface/routes/targets.py`.
- `backend/.env.example`, `docker-compose.prod.yml`.
- Delete: `application/screening/create_target.py`, `update_target.py`, `delete_target.py`.
- Tests modified: `tests/api/conftest.py` (`make_target` fixture, `overrides`), `tests/api/test_protocol_run_targets.py`, `tests/api/test_campaigns_api.py`.

**Frontend — create**
- `src/features/screening-assay/components/admin-targets-page.tsx` (+ `.test.tsx`), `src/app/(dashboard)/admin/targets/page.tsx`.

**Frontend — modify**
- `src/app/api/config/route.ts` (+test), `src/shared/lib/app-config.tsx`, `frontend/.env.example`, root `.env.example`, `docker-compose.prod.yml`.
- `src/features/screening-assay/types/index.ts`, `hooks/use-targets.ts`, `components/target-list.tsx`, `components/target-multi-select.tsx` (+test), `components/screening-dashboard.tsx`, `components/detail-tabs/design-tab-protocol-card.test.tsx`, `src/shared/lib/navigation.ts`.
- Delete: `components/create-target-dialog.tsx`, `components/edit-target-dialog.tsx`.
- orval regen: `src/shared/lib/api/model/**`, `src/shared/lib/api/targets/targets.ts`.

---

### Task 1: Mirror columns — migration, ORM, domain enum/entity, repository mapping

**Files:**
- Create: `backend/alembic/versions/065_target_mirror_columns.py`
- Modify: `backend/src/cellar/domain/screening_assay/enums.py:92-101`
- Modify: `backend/src/cellar/domain/screening_assay/target.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py:136-151`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/target_repository.py`
- Test: `backend/tests/unit/domain/screening_assay/test_target.py`

**Interfaces:**
- Produces: `TargetType.DOMAIN / PROTEIN_PROTEIN_INTERACTION / UNKNOWN`; `Target(..., chembl_id: str | None = None, source_version: int | None = None)`; `Target.from_mirror(*, id, workspace_id, name, target_type, organism, chembl_id, source_version) -> Target`; ORM columns `TargetModel.chembl_id`, `TargetModel.source_version`.

- [ ] **Step 1: Write the failing domain test**

Append to `backend/tests/unit/domain/screening_assay/test_target.py` (keep the existing tests for now — Task 4 rewrites the file when `Target.create` goes away):

```python
class TestTargetMirror:
    def test_from_mirror_uses_supplied_id_and_stores_source_fields(
        self, workspace_id: uuid.UUID
    ) -> None:
        tid = uuid.uuid4()
        t = Target.from_mirror(
            id=tid,
            workspace_id=workspace_id,
            name="  NadD ",
            target_type=TargetType.SINGLE_PROTEIN,
            organism="Mycobacterium tuberculosis",
            chembl_id="CHEMBL4630874",
            source_version=3,
        )
        assert t.id == tid
        assert t.name == "NadD"
        assert t.organism == "Mycobacterium tuberculosis"
        assert t.chembl_id == "CHEMBL4630874"
        assert t.source_version == 3

    def test_from_mirror_rejects_blank_name(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError):
            Target.from_mirror(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                name="  ",
                target_type=TargetType.DOMAIN,
                organism=None,
                chembl_id=None,
                source_version=1,
            )

    def test_new_enum_values_exist(self) -> None:
        assert TargetType("domain") is TargetType.DOMAIN
        assert TargetType("protein_protein_interaction") is TargetType.PROTEIN_PROTEIN_INTERACTION
        assert TargetType("unknown") is TargetType.UNKNOWN
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_target.py -v --tb=short -k Mirror`
Expected: FAIL — `AttributeError: type object 'Target' has no attribute 'from_mirror'` / `ValueError: 'domain' is not a valid TargetType`.

- [ ] **Step 3: Extend the enum**

In `backend/src/cellar/domain/screening_assay/enums.py` replace the `TargetType` class body:

```python
class TargetType(StrEnum):
    """Classification of a biological target.

    Superset of prot-cellar's ``TargetType`` — the mirror must accept every
    value the source can emit (unknown source values map to ``UNKNOWN``).
    """

    SINGLE_PROTEIN = "single_protein"
    DOMAIN = "domain"
    PROTEIN_COMPLEX = "protein_complex"
    PROTEIN_FAMILY = "protein_family"
    PROTEIN_PROTEIN_INTERACTION = "protein_protein_interaction"
    NUCLEIC_ACID = "nucleic_acid"
    ORGANISM = "organism"
    CELL_LINE = "cell_line"
    TISSUE = "tissue"
    UNKNOWN = "unknown"
```

- [ ] **Step 4: Extend the entity**

In `backend/src/cellar/domain/screening_assay/target.py`:

1. Add two kwargs to `Target.__init__` (after `sequence`): `chembl_id: str | None = None, source_version: int | None = None,` and assign `self.chembl_id = chembl_id` / `self.source_version = source_version` after `self.sequence = sequence`.
2. Update the class docstring invariants list with: `- mirror rows carry the prot-cellar id and ``source_version`` (the source's optimistic-concurrency counter, used as the change signal on re-sync)`.
3. Add the factory (keep `create`/`update` for now; Task 4 deletes them):

```python
    @classmethod
    def from_mirror(
        cls,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        target_type: TargetType,
        organism: str | None,
        chembl_id: str | None,
        source_version: int,
    ) -> Target:
        """Build the local mirror row for a prot-cellar target.

        ``id`` is prot-cellar's target id — identical on both sides so link
        tables (``protocol_targets`` / ``run_targets``) need no translation.
        """
        return cls(
            id=id,
            workspace_id=workspace_id,
            name=name,
            target_type=target_type,
            organism=organism,
            chembl_id=chembl_id,
            source_version=source_version,
        )
```

- [ ] **Step 5: ORM columns + repository mapping**

In `models.py` `TargetModel`, add after `sequence`:

```python
    # Mirror of prot-cellar (spec 2026-08-24): the source's ChEMBL id and its
    # ``version`` counter — the change signal for re-sync. NULL = a legacy
    # locally-created row (only the cutover script should ever see one).
    chembl_id: Mapped[str | None] = mapped_column(String(30))
    source_version: Mapped[int | None] = mapped_column(Integer)
```

In `target_repository.py`: add `chembl_id=model.chembl_id, source_version=model.source_version,` to `_to_domain`; `chembl_id=entity.chembl_id, source_version=entity.source_version,` to `_to_model`; and `model.chembl_id = entity.chembl_id` / `model.source_version = entity.source_version` to `_update_model`.

- [ ] **Step 6: Migration**

Create `backend/alembic/versions/065_target_mirror_columns.py`:

```python
"""065 — targets mirror columns (spec 2026-08-24-targets-from-prot-cellar)

``targets`` becomes a read-only mirror of prot-cellar's catalog. Two
nullable columns: ``chembl_id`` (carried from the source) and
``source_version`` (prot-cellar's optimistic-concurrency counter — the
re-sync change signal; NULL marks a pre-mirror, locally-created row).

Revision ID: 065_target_mirror_columns
Revises: 064_kiosk_devices
"""

import sqlalchemy as sa
from alembic import op

revision = "065_target_mirror_columns"
down_revision = "064_kiosk_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("chembl_id", sa.String(30), nullable=True))
    op.add_column("targets", sa.Column("source_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("targets", "source_version")
    op.drop_column("targets", "chembl_id")
```

- [ ] **Step 7: Run tests + migration**

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_target.py -v --tb=short`
Expected: PASS (all, including the pre-existing `Target.create` tests).

Run: `cd .. && make migrate` (Postgres must be up: `make up`)
Expected: `Running upgrade 064_kiosk_devices -> 065_target_mirror_columns`.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/065_target_mirror_columns.py backend/src/cellar/domain/screening_assay/enums.py backend/src/cellar/domain/screening_assay/target.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/target_repository.py backend/tests/unit/domain/screening_assay/test_target.py
git commit -m "feat(targets): mirror columns + Target.from_mirror + TargetType superset (migration 065)" -- backend/alembic/versions/065_target_mirror_columns.py backend/src/cellar/domain/screening_assay/enums.py backend/src/cellar/domain/screening_assay/target.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/target_repository.py backend/tests/unit/domain/screening_assay/test_target.py
```

---

### Task 2: `TargetSource` port + `HttpTargetSource` adapter

**Files:**
- Create: `backend/src/cellar/application/screening/target_source.py`
- Create: `backend/src/cellar/infrastructure/prot_cellar/__init__.py`
- Create: `backend/src/cellar/infrastructure/prot_cellar/settings.py`
- Create: `backend/src/cellar/infrastructure/prot_cellar/target_source.py`
- Modify: `backend/.env.example` (append after the Duar block)
- Test: `backend/tests/unit/infrastructure/test_http_target_source.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class SourceTarget: id: uuid.UUID; name: str; target_type: str; organism: str | None; chembl_id: str | None; version: int
  class TargetSource(Protocol):
      async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]: ...
  class ProtCellarSettings(BaseSettings): url: str = "http://localhost:8001"; timeout_seconds: float = 30.0   # env prefix PROT_CELLAR_
  class HttpTargetSource(TargetSource): def __init__(self, client: httpx.AsyncClient, settings: ProtCellarSettings)
  ```
- Raises: `AuthorizationError` (prot-cellar 401/403), `ServiceUnavailableError` (connect/timeout/other non-2xx).

- [ ] **Step 1: Write the failing adapter test**

Create `backend/tests/unit/infrastructure/test_http_target_source.py`:

```python
"""HttpTargetSource — pages through prot-cellar's target list, forwarding auth."""

from __future__ import annotations

import uuid

import httpx
import pytest

from cellar.application.screening.target_source import SourceTarget
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from cellar.infrastructure.prot_cellar.settings import ProtCellarSettings
from cellar.infrastructure.prot_cellar.target_source import HttpTargetSource

ORG_ID = str(uuid.uuid4())
T1, T2, T3 = (str(uuid.uuid4()) for _ in range(3))
HEADERS = {"authorization": "Bearer idp", "x-authz-token": "authz"}


def _target(tid: str, name: str, ttype: str = "single_protein", org: str | None = ORG_ID):
    return {
        "id": tid,
        "workspace_id": str(uuid.uuid4()),
        "pref_name": name,
        "target_type": ttype,
        "components": [],
        "organism_id": org,
        "chembl_id": "CHEMBL1" if name == "AspS" else None,
        "chembl_url": None,
        "pharmacological_class": None,
        "cross_references": [],
        "version": 2,
    }


def _source(handler) -> HttpTargetSource:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpTargetSource(client, ProtCellarSettings(url="http://prot", _env_file=None))


@pytest.mark.asyncio
async def test_pages_until_cursor_exhausted_and_forwards_auth_headers():
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["authorization"] == "Bearer idp"
        assert req.headers["x-authz-token"] == "authz"
        if req.url.path == "/api/v1/targets":
            assert req.url.params["limit"] == "200"
            cursor = req.url.params.get("cursor")
            if cursor is None:
                return httpx.Response(
                    200, json={"items": [_target(T1, "AspS"), _target(T2, "ClpC1")], "next_cursor": T2}
                )
            assert cursor == T2
            return httpx.Response(
                200, json={"items": [_target(T3, "Weird", ttype="martian")], "next_cursor": None}
            )
        if req.url.path == f"/api/v1/organisms/{ORG_ID}":
            return httpx.Response(200, json={"id": ORG_ID, "scientific_name": "Mycobacterium tuberculosis"})
        raise AssertionError(f"unexpected {req.url}")

    result = await _source(handler).fetch_all(forwarded_headers=HEADERS)

    assert result == [
        SourceTarget(uuid.UUID(T1), "AspS", "single_protein", "Mycobacterium tuberculosis", "CHEMBL1", 2),
        SourceTarget(uuid.UUID(T2), "ClpC1", "single_protein", "Mycobacterium tuberculosis", None, 2),
        SourceTarget(uuid.UUID(T3), "Weird", "unknown", "Mycobacterium tuberculosis", None, 2),
    ]
    # 2 target pages + exactly ONE organism lookup (cached per fetch_all).
    assert [c.url.path for c in calls].count(f"/api/v1/organisms/{ORG_ID}") == 1
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_organism_lookup_failure_degrades_to_none():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/targets":
            return httpx.Response(200, json={"items": [_target(T1, "AspS")], "next_cursor": None})
        return httpx.Response(500)

    [t] = await _source(handler).fetch_all(forwarded_headers=HEADERS)
    assert t.organism is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_rejection_raises_authorization_error(status: int):
    src = _source(lambda req: httpx.Response(status, json={"detail": "editor required"}))
    with pytest.raises(AuthorizationError, match="editor"):
        await src.fetch_all(forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_unreachable_raises_service_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    with pytest.raises(ServiceUnavailableError, match="prot-cellar"):
        await _source(handler).fetch_all(forwarded_headers=HEADERS)


@pytest.mark.asyncio
async def test_5xx_raises_service_unavailable():
    src = _source(lambda req: httpx.Response(502))
    with pytest.raises(ServiceUnavailableError):
        await src.fetch_all(forwarded_headers=HEADERS)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_http_target_source.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.application.screening.target_source'`.

- [ ] **Step 3: Write the port**

Create `backend/src/cellar/application/screening/target_source.py`:

```python
"""Port: where the target catalog comes from (prot-cellar).

The application layer only knows "give me every target for the caller, using
the caller's own credentials". The adapter lives in
``infrastructure/prot_cellar`` and must raise ``AuthorizationError`` when the
source refuses the forwarded credentials and ``ServiceUnavailableError`` when
it cannot be reached — both already map to HTTP statuses in the API layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SourceTarget:
    """One target as the source describes it — already flattened for the mirror."""

    id: uuid.UUID
    name: str
    target_type: str
    organism: str | None
    chembl_id: str | None
    version: int


@runtime_checkable
class TargetSource(Protocol):
    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        """Every target visible to the caller. Pages internally; no cap."""
        ...
```

- [ ] **Step 4: Write settings + adapter**

Create `backend/src/cellar/infrastructure/prot_cellar/__init__.py` (empty docstring module):

```python
"""prot-cellar integration — the sister app that owns the target catalog."""
```

Create `backend/src/cellar/infrastructure/prot_cellar/settings.py`:

```python
"""prot-cellar connection settings (``PROT_CELLAR_*`` env vars)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProtCellarSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROT_CELLAR_", env_file=".env")

    url: str = "http://localhost:8001"
    timeout_seconds: float = 30.0
```

Create `backend/src/cellar/infrastructure/prot_cellar/target_source.py`:

```python
"""HTTP adapter for the ``TargetSource`` port — prot-cellar's ``/api/v1/targets``.

Auth: forwards the caller's own Duar headers (``Authorization`` +
``X-Authz-Token``). Both apps are members of the same Duar realm, so a
chem-vault2-minted authz token is accepted by prot-cellar as-is. The service
key is never sent.

Paging: keyset cursor, ``limit=200`` (prot-cellar's max), until
``next_cursor`` is null — the whole catalog, no cap.

Organism names are not on prot-cellar's target DTO; they are resolved via
``GET /api/v1/organisms/{id}`` with a per-call cache (a workspace typically
has 1–3 distinct organisms).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

import httpx
import structlog

from cellar.application.screening.target_source import SourceTarget, TargetSource
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from cellar.infrastructure.prot_cellar.settings import ProtCellarSettings

_log = structlog.get_logger(__name__)

PAGE_SIZE = 200
_KNOWN_TYPES = {t.value for t in TargetType}


class HttpTargetSource(TargetSource):
    def __init__(self, client: httpx.AsyncClient, settings: ProtCellarSettings) -> None:
        self._client = client
        self._base = settings.url.rstrip("/")
        self._timeout = settings.timeout_seconds

    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        headers = dict(forwarded_headers)
        organisms: dict[str, str | None] = {}
        out: list[SourceTarget] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            page = await self._get_json("/api/v1/targets", headers, params)
            for item in page["items"]:
                org_id = item.get("organism_id")
                if org_id and org_id not in organisms:
                    organisms[org_id] = await self._organism_name(org_id, headers)
                ttype = item["target_type"]
                if ttype not in _KNOWN_TYPES:
                    _log.warning("targets.sync.unknown_type", target_type=ttype, target_id=item["id"])
                    ttype = TargetType.UNKNOWN.value
                out.append(
                    SourceTarget(
                        id=uuid.UUID(item["id"]),
                        name=item["pref_name"],
                        target_type=ttype,
                        organism=organisms.get(org_id) if org_id else None,
                        chembl_id=item.get("chembl_id"),
                        version=int(item["version"]),
                    )
                )
            cursor = page.get("next_cursor")
            if not cursor:
                return out

    async def _organism_name(self, org_id: str, headers: dict[str, str]) -> str | None:
        try:
            data = await self._get_json(f"/api/v1/organisms/{org_id}", headers, {})
        except (AuthorizationError, ServiceUnavailableError) as exc:
            _log.warning("targets.sync.organism_lookup_failed", organism_id=org_id, reason=str(exc))
            return None
        return data.get("scientific_name")

    async def _get_json(
        self, path: str, headers: dict[str, str], params: dict[str, str | int]
    ) -> dict:
        try:
            resp = await self._client.get(
                f"{self._base}{path}", headers=headers, params=params, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"prot-cellar unreachable: {exc}") from exc
        if resp.status_code in (401, 403):
            detail = _detail(resp)
            raise AuthorizationError(
                f"prot-cellar refused the request ({resp.status_code}): {detail}. "
                "Target reads in prot-cellar require the editor role."
            )
        if resp.status_code >= 400:
            raise ServiceUnavailableError(
                f"prot-cellar returned {resp.status_code} for {path}: {_detail(resp)}"
            )
        return resp.json()


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    return str(body.get("detail") or body.get("message") or body)[:200]
```

Append to `backend/.env.example` after the Duar block:

```
# prot-cellar (sister app that owns the target catalog). Targets are mirrored
# from its API using the caller's own Duar credentials (shared realm).
PROT_CELLAR_URL=http://localhost:8001
```

- [ ] **Step 5: Run tests + import-linter**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_http_target_source.py -v --tb=short && uv run lint-imports`
Expected: 6 PASS; import-linter "Contracts: N kept, 0 broken".

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/screening/target_source.py backend/src/cellar/infrastructure/prot_cellar backend/tests/unit/infrastructure/test_http_target_source.py backend/.env.example
git commit -m "feat(targets): TargetSource port + prot-cellar HTTP adapter (cursor-paged, auth forwarded)" -- backend/src/cellar/application/screening/target_source.py backend/src/cellar/infrastructure/prot_cellar backend/tests/unit/infrastructure/test_http_target_source.py backend/.env.example
```

---

### Task 3: `SyncTargetsFromProtCellar` use case + `SyncFreshness`

**Files:**
- Create: `backend/src/cellar/application/screening/sync_targets.py`
- Test: `backend/tests/unit/application/screening/test_sync_targets.py`

**Interfaces:**
- Consumes: `TargetSource`, `SourceTarget` (Task 2); `Target.from_mirror`, `TargetRepository.find_by_workspace/save` (Task 1 / existing).
- Produces:
  ```python
  class SyncFreshness: def __init__(self, ttl_seconds: float = 300.0); def is_fresh(self, workspace_id) -> bool; def mark(self, workspace_id) -> None; def reset(self) -> None
  @dataclass(frozen=True, kw_only=True) class SyncTargetsCommand(Command): workspace_id: uuid.UUID; forwarded_headers: Mapping[str, str]; force: bool = False
  @dataclass(frozen=True) class SyncReport: fetched: int; created: int; updated: int; skipped: int
  class SyncTargetsFromProtCellar: def __init__(self, uow, repo: TargetRepository, source: TargetSource, freshness: SyncFreshness); async def __call__(self, input: SyncTargetsCommand, auth=None) -> Result[SyncReport, DomainError]
  ```
- Semantics: `force=True` requires **admin** and always fetches; `force=False` requires viewer and is a no-op while the workspace is fresh. Freshness is marked on *attempt* (so a failing prot-cellar isn't hammered).

- [ ] **Step 1: Write the failing use-case tests**

Create `backend/tests/unit/application/screening/test_sync_targets.py`:

```python
"""SyncTargetsFromProtCellar — diff-by-version upsert, TTL gate, role gate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from cellar.application.screening.sync_targets import (
    SyncFreshness,
    SyncReport,
    SyncTargetsCommand,
    SyncTargetsFromProtCellar,
)
from cellar.application.screening.target_source import SourceTarget
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from cellar.domain.shared.events import DomainEvent

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
HEADERS = {"authorization": "Bearer x", "x-authz-token": "y"}


class FakeUoW:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> list[DomainEvent]:
        self.commits += 1
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


class FakeRepo:
    def __init__(self, existing: list[Target] | None = None) -> None:
        self.rows: dict[uuid.UUID, Target] = {t.id: t for t in existing or []}
        self.saved: list[Target] = []

    async def find_by_workspace(self, workspace_id, *, cursor_id=None, limit=None):
        return [t for t in self.rows.values() if t.workspace_id == workspace_id]

    async def save(self, entity: Target) -> None:
        self.saved.append(entity)
        self.rows[entity.id] = entity


class FakeSource:
    def __init__(self, targets: list[SourceTarget] | None = None, error: Exception | None = None):
        self.targets = targets or []
        self.error = error
        self.calls: list[dict] = []

    async def fetch_all(self, *, forwarded_headers):
        self.calls.append(dict(forwarded_headers))
        if self.error:
            raise self.error
        return self.targets


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = WS
    workspace_role: str = "admin"
    is_admin: bool = True

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


def _src(tid: uuid.UUID, name: str, version: int = 1) -> SourceTarget:
    return SourceTarget(tid, name, "single_protein", "Mtb", None, version)


def _build(source: FakeSource, existing: list[Target] | None = None, ttl: float = 300.0):
    uow, repo, fresh = FakeUoW(), FakeRepo(existing), SyncFreshness(ttl_seconds=ttl)
    return SyncTargetsFromProtCellar(uow, repo, source, fresh), uow, repo, fresh


async def test_creates_updates_and_skips_by_source_version():
    t_new, t_changed, t_same = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    existing = [
        Target.from_mirror(id=t_changed, workspace_id=WS, name="Old", target_type=TargetType.SINGLE_PROTEIN, organism=None, chembl_id=None, source_version=1),
        Target.from_mirror(id=t_same, workspace_id=WS, name="Same", target_type=TargetType.SINGLE_PROTEIN, organism=None, chembl_id=None, source_version=4),
    ]
    source = FakeSource([_src(t_new, "New"), _src(t_changed, "Renamed", version=2), _src(t_same, "Same", version=4)])
    uc, uow, repo, _ = _build(source, existing)

    result = await uc(SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True), auth=FakeAuth())

    assert result == Success(SyncReport(fetched=3, created=1, updated=1, skipped=1))
    assert {t.id for t in repo.saved} == {t_new, t_changed}
    assert repo.rows[t_changed].name == "Renamed"
    assert repo.rows[t_changed].source_version == 2
    assert uow.commits == 1
    assert source.calls == [HEADERS]


async def test_non_forced_sync_is_noop_while_fresh_then_refetches_after_ttl(monkeypatch):
    source = FakeSource([_src(uuid.uuid4(), "A")])
    uc, _, _, fresh = _build(source, ttl=300.0)
    cmd = SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS)

    first = await uc(cmd, auth=FakeAuth(workspace_role="viewer", is_admin=False))
    second = await uc(cmd, auth=FakeAuth(workspace_role="viewer", is_admin=False))
    assert first.unwrap().fetched == 1
    assert second == Success(SyncReport(fetched=0, created=0, updated=0, skipped=0))
    assert len(source.calls) == 1

    import cellar.application.screening.sync_targets as mod

    base = mod.time.monotonic()
    monkeypatch.setattr(mod.time, "monotonic", lambda: base + 400.0)
    third = await uc(cmd, auth=FakeAuth(workspace_role="viewer", is_admin=False))
    assert third.unwrap().fetched == 1
    assert len(source.calls) == 2


async def test_force_bypasses_ttl_but_requires_admin():
    source = FakeSource([_src(uuid.uuid4(), "A")])
    uc, _, _, _ = _build(source)
    admin = FakeAuth()
    await uc(SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True), auth=admin)
    await uc(SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True), auth=admin)
    assert len(source.calls) == 2

    with pytest.raises(AuthorizationError):
        await uc(
            SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True),
            auth=FakeAuth(workspace_role="editor", is_admin=False),
        )


async def test_source_errors_become_failures_and_still_mark_freshness():
    source = FakeSource(error=ServiceUnavailableError("prot-cellar unreachable"))
    uc, uow, _, fresh = _build(source)
    result = await uc(SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True), auth=FakeAuth())
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ServiceUnavailableError)
    assert uow.commits == 0
    assert fresh.is_fresh(WS)  # a failing source is not retried until the TTL lapses


async def test_rejects_other_workspace():
    uc, _, _, _ = _build(FakeSource())
    with pytest.raises(AuthorizationError):
        await uc(
            SyncTargetsCommand(workspace_id=uuid.uuid4(), forwarded_headers=HEADERS, force=True),
            auth=FakeAuth(),
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_sync_targets.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: cellar.application.screening.sync_targets`.

- [ ] **Step 3: Write the use case**

Create `backend/src/cellar/application/screening/sync_targets.py`:

```python
"""SyncTargetsFromProtCellar — refresh the local read-only target mirror.

prot-cellar owns the catalog (spec 2026-08-24). This use case pulls every
target the caller can see, diffs against the mirror by ``source_version``,
and upserts through the ordinary ``TargetRepository.save`` (ids are shared,
so an existing row is updated in place and every link table keeps working).

Two call modes:
- ``force=True``  — the admin "Sync from Prot-Cellar" button. Admin-only,
  always hits the source.
- ``force=False`` — best-effort refresh on ``GET /targets``. Viewer+, and a
  no-op while the workspace's mirror is fresh (``SyncFreshness`` TTL).

Freshness is marked on *attempt*, not success: a viewer whose token
prot-cellar refuses (its reads need editor) or a down prot-cellar must not be
re-hit on every list call. Deletions are not synced — prot-cellar has no
target delete.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.target_source import TargetSource
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import DomainError

_log = structlog.get_logger(__name__)


class SyncFreshness:
    """Per-workspace "last attempted" clock. One instance per process (DI Singleton).

    # ponytail: in-process; move to Valkey if multi-replica staleness ever matters.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._ttl = ttl_seconds
        self._last: dict[uuid.UUID, float] = {}

    def is_fresh(self, workspace_id: uuid.UUID) -> bool:
        return time.monotonic() - self._last.get(workspace_id, float("-inf")) < self._ttl

    def mark(self, workspace_id: uuid.UUID) -> None:
        self._last[workspace_id] = time.monotonic()

    def reset(self) -> None:
        self._last.clear()


@dataclass(frozen=True, kw_only=True)
class SyncTargetsCommand(Command):
    workspace_id: uuid.UUID
    forwarded_headers: Mapping[str, str] = field(default_factory=dict)
    force: bool = False


@dataclass(frozen=True)
class SyncReport:
    fetched: int
    created: int
    updated: int
    skipped: int


_NOOP = SyncReport(fetched=0, created=0, updated=0, skipped=0)


class SyncTargetsFromProtCellar:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: TargetRepository,
        source: TargetSource,
        freshness: SyncFreshness,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._source = source
        self._freshness = freshness

    async def __call__(
        self, input: SyncTargetsCommand, auth: AuthContext | None = None
    ) -> Result[SyncReport, DomainError]:
        require_workspace_role(auth, "admin" if input.force else "viewer")
        require_same_workspace(auth, input.workspace_id)

        if not input.force and self._freshness.is_fresh(input.workspace_id):
            return Success(_NOOP)
        self._freshness.mark(input.workspace_id)

        try:
            fetched = await self._source.fetch_all(forwarded_headers=input.forwarded_headers)
        except DomainError as exc:
            _log.warning("targets.sync.failed", workspace_id=str(input.workspace_id), reason=str(exc))
            return Failure(exc)

        created = updated = skipped = 0
        async with self._uow:
            existing = {t.id: t for t in await self._repo.find_by_workspace(input.workspace_id)}
            for st in fetched:
                current = existing.get(st.id)
                if current is not None and current.source_version == st.version:
                    skipped += 1
                    continue
                await self._repo.save(
                    Target.from_mirror(
                        id=st.id,
                        workspace_id=input.workspace_id,
                        name=st.name,
                        target_type=TargetType(st.target_type),
                        organism=st.organism,
                        chembl_id=st.chembl_id,
                        source_version=st.version,
                    )
                )
                if current is None:
                    created += 1
                else:
                    updated += 1
            await self._uow.commit()

        report = SyncReport(fetched=len(fetched), created=created, updated=updated, skipped=skipped)
        _log.info("targets.sync.completed", workspace_id=str(input.workspace_id), **report.__dict__)
        return Success(report)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/unit/application/screening/test_sync_targets.py -v --tb=short && uv run lint-imports`
Expected: 5 PASS, contracts kept.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/screening/sync_targets.py backend/tests/unit/application/screening/test_sync_targets.py
git commit -m "feat(targets): SyncTargetsFromProtCellar use case (diff by source_version, TTL gate, admin force)" -- backend/src/cellar/application/screening/sync_targets.py backend/tests/unit/application/screening/test_sync_targets.py
```

---

### Task 4: Remove local target CRUD (backend) + test seeding helper

**Files:**
- Delete: `backend/src/cellar/application/screening/create_target.py`, `update_target.py`, `delete_target.py`
- Modify: `backend/src/cellar/domain/screening_assay/target.py` (drop `create`, `update`)
- Modify: `backend/src/cellar/domain/screening_assay/repository.py:193-201` (drop `count_references`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/target_repository.py` (drop `count_references` + unused imports)
- Modify: `backend/src/cellar/infrastructure/di/_screening.py:39,43,173,355-373`
- Modify: `backend/src/cellar/interface/dependencies/_screening.py:19,22,120,147,152,222,298-302`
- Modify: `backend/src/cellar/interface/routes/targets.py` (drop POST/PATCH/DELETE + request models + `UNSET` import)
- Modify: `backend/tests/unit/domain/screening_assay/test_target.py` (rewrite around `from_mirror`)
- Modify: `backend/tests/api/conftest.py` (`make_target` fixture)
- Modify: `backend/tests/api/test_protocol_run_targets.py`, `backend/tests/api/test_campaigns_api.py`

**Interfaces:**
- Produces (tests): fixture `make_target(name: str, *, target_type: str = "single_protein") -> str` (async callable returning the new target id, inserted as a mirror row with `source_version=1`).

- [ ] **Step 1: Rewrite the domain test**

Replace `backend/tests/unit/domain/screening_assay/test_target.py` entirely with:

```python
"""Tests for Target entity (read-only mirror of prot-cellar)."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import ValidationError


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


def _mirror(workspace_id: uuid.UUID, **overrides) -> Target:
    kwargs = dict(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="NadD",
        target_type=TargetType.SINGLE_PROTEIN,
        organism="Mycobacterium tuberculosis",
        chembl_id=None,
        source_version=1,
    )
    kwargs.update(overrides)
    return Target.from_mirror(**kwargs)


class TestTargetMirror:
    def test_from_mirror_uses_supplied_id_and_stores_source_fields(
        self, workspace_id: uuid.UUID
    ) -> None:
        tid = uuid.uuid4()
        t = _mirror(workspace_id, id=tid, name="  NadD ", chembl_id="CHEMBL4630874", source_version=3)
        assert t.id == tid
        assert t.workspace_id == workspace_id
        assert t.name == "NadD"
        assert t.target_type is TargetType.SINGLE_PROTEIN
        assert t.organism == "Mycobacterium tuberculosis"
        assert t.chembl_id == "CHEMBL4630874"
        assert t.source_version == 3

    def test_from_mirror_rejects_blank_name(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError):
            _mirror(workspace_id, name="  ")

    def test_no_local_mutation_api(self) -> None:
        # The catalog is owned by prot-cellar — no create/update on the mirror.
        assert not hasattr(Target, "create")
        assert not hasattr(Target, "update")

    def test_new_enum_values_exist(self) -> None:
        assert TargetType("domain") is TargetType.DOMAIN
        assert TargetType("protein_protein_interaction") is TargetType.PROTEIN_PROTEIN_INTERACTION
        assert TargetType("unknown") is TargetType.UNKNOWN

    def test_identity_equality(self, workspace_id: uuid.UUID) -> None:
        tid = uuid.uuid4()
        assert _mirror(workspace_id, id=tid) == _mirror(workspace_id, id=tid, name="Other")
        assert _mirror(workspace_id) != _mirror(workspace_id)
```

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_target.py -v --tb=short`
Expected: FAIL only on `test_no_local_mutation_api` (create/update still exist).

- [ ] **Step 2: Strip the domain entity**

In `target.py`: delete the `create` classmethod and the `update` method (and the `# Factory method` / `# Updates` section comments). Keep `__init__`, `from_mirror`. Remove the now-unused `from datetime import UTC, datetime` → keep `datetime` (used in `__init__` type hints), drop `UTC`. Update the class docstring: `"""A biological target — read-only mirror of prot-cellar's catalog. Reference entity (not AggregateRoot); rows are created/updated only by SyncTargetsFromProtCellar. Invariants: name non-empty."""`.

Run the domain test again → all PASS.

- [ ] **Step 3: Delete use cases, repo method, DI, deps, routes**

1. `git rm backend/src/cellar/application/screening/create_target.py backend/src/cellar/application/screening/update_target.py backend/src/cellar/application/screening/delete_target.py`
2. `domain/screening_assay/repository.py`: delete the `count_references` method from `TargetRepository` (lines 193-201), leaving `find_by_workspace`, `save`, `delete`.
3. `target_repository.py`: delete `count_references`; remove now-unused imports (`func`, `select`, `ProtocolModel`, `RunModel`, `protocol_targets`, `run_targets`). Update the module docstring: `"""SQLAlchemy repository for Target entities (read-only mirror rows — see sync_targets)."""`.
4. `infrastructure/di/_screening.py`: remove the three imports (`CreateTarget`, `DeleteTarget`, `UpdateTarget`), the `_target_cmd` factory and its three `container.define` lines. Keep `_target_query` + `GetTarget`/`ListTargets` defines (Task 5 rewires `ListTargets`).
5. `interface/dependencies/_screening.py`: remove the three imports, the three `__all__` entries (`CreateTargetDep`, `DeleteTargetDep`, `UpdateTargetDep`) and the three `Annotated` definitions.
6. `interface/routes/targets.py`: delete `CreateTargetRequest`, `UpdateTargetRequest`, the `create_target`, `update_target`, `delete_target` handlers, and the imports `CreateTargetCommand`, `DeleteTargetCommand`, `UpdateTargetCommand`, `UNSET`, `CreateTargetDep`, `DeleteTargetDep`, `UpdateTargetDep`. Add `chembl_id: str | None = None` to `TargetResponse` (after `target_class`) and `chembl_id=t.chembl_id,` in `from_domain`. Update the module docstring: `"""Target API routes — read-only mirror of prot-cellar's catalog (see sync_targets)."""`.

Run: `cd backend && uv run python -c "import cellar.interface.app"` → no ImportError. `grep -rn "CreateTarget\|UpdateTarget\|DeleteTarget\|count_references" src/` → no hits.

- [ ] **Step 4: Add the `make_target` API-test fixture**

In `backend/tests/api/conftest.py`, add after the `client` fixture:

```python
@pytest.fixture
def make_target(api_app: FastAPI, workspace_id: uuid.UUID):
    """Seed a mirror target row directly (there is no create route — prot-cellar owns targets).

    Returns ``async (name, *, target_type="single_protein") -> str`` (the new id).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import TargetModel

    async def _make(name: str, *, target_type: str = "single_protein") -> str:
        tid = uuid.uuid4()
        factory = api_app.state.container[async_sessionmaker]
        async with factory() as session, session.begin():
            session.add(
                TargetModel(
                    id=tid,
                    workspace_id=workspace_id,
                    name=name,
                    target_type=target_type,
                    source_version=1,
                )
            )
        return str(tid)

    return _make
```

- [ ] **Step 5: Migrate the two API test files**

In `tests/api/test_protocol_run_targets.py` and `tests/api/test_campaigns_api.py`:
1. Delete the module-level `_make_target(client, name)` helper.
2. For every test method that calls `_make_target(...)`: add `make_target` to its parameters and replace `await _make_target(<any client>, "X")` with `await make_target("X")`. Find them with `grep -n "_make_target(" tests/api/test_protocol_run_targets.py tests/api/test_campaigns_api.py`.
3. Any test that asserts a `POST /api/v1/targets` status (grep `"/api/v1/targets"` with `.post(`) — delete that assertion; the route no longer exists.

Run: `cd backend && uv run pytest tests/api/test_protocol_run_targets.py tests/api/test_campaigns_api.py -v --tb=short`
Expected: PASS (all).

- [ ] **Step 6: Full backend check**

Run: `cd backend && uv run pytest tests/unit/ -q --tb=short && uv run lint-imports && uv run pytest tests/api/ tests/integration/ -q --tb=short`
Expected: green. If any other test references the removed routes/use cases, fix it the same way (`make_target`).

- [ ] **Step 7: Commit**

```bash
git add -A backend/src/cellar/application/screening backend/src/cellar/domain/screening_assay backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/target_repository.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_screening.py backend/src/cellar/interface/routes/targets.py backend/tests/unit/domain/screening_assay/test_target.py backend/tests/api/conftest.py backend/tests/api/test_protocol_run_targets.py backend/tests/api/test_campaigns_api.py
git commit -m "refactor(targets)!: remove local target create/update/delete — prot-cellar owns the catalog" -- backend/src/cellar/application/screening backend/src/cellar/domain/screening_assay backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/target_repository.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_screening.py backend/src/cellar/interface/routes/targets.py backend/tests/unit/domain/screening_assay/test_target.py backend/tests/api/conftest.py backend/tests/api/test_protocol_run_targets.py backend/tests/api/test_campaigns_api.py
```

---

### Task 5: API — `POST /targets/sync`, best-effort refresh on `GET /targets`, DI wiring

**Files:**
- Modify: `backend/src/cellar/application/screening/get_target.py` (`ListTargetsQuery.forwarded_headers`, `ListTargets(sync=...)`)
- Modify: `backend/src/cellar/infrastructure/di/container.py` (`overrides` seam)
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (wire `TargetSource`, `SyncFreshness`, `SyncTargetsFromProtCellar`, `ListTargets`)
- Modify: `backend/src/cellar/interface/dependencies/_screening.py` (`SyncTargetsDep`)
- Modify: `backend/src/cellar/interface/routes/targets.py`
- Modify: `backend/tests/api/conftest.py` (`_create_test_app(..., overrides=None)`)
- Modify: `docker-compose.prod.yml:29-40` (backend env)
- Test: `backend/tests/api/test_targets_sync.py`

**Interfaces:**
- Consumes: Task 2 `TargetSource`, `HttpTargetSource`, `ProtCellarSettings`; Task 3 `SyncFreshness`, `SyncTargetsCommand`, `SyncReport`, `SyncTargetsFromProtCellar`.
- Produces: `POST /api/v1/targets/sync` → `TargetSyncReportResponse{fetched, created, updated, skipped}` (201? no — **200**); `create_container(db_settings=None, *, overrides: Mapping[type, object] | None = None)`; `ListTargetsQuery.forwarded_headers: Mapping[str, str]`; `ListTargets.__init__(uow, repo, sync: SyncTargetsFromProtCellar | None = None)`.

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/api/test_targets_sync.py`:

```python
"""POST /api/v1/targets/sync + best-effort refresh on GET /api/v1/targets.

The prot-cellar adapter is replaced with an in-memory ``TargetSource`` via the
container ``overrides`` seam — no network in tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.screening.target_source import SourceTarget, TargetSource
from cellar.domain.shared.errors import AuthorizationError, ServiceUnavailableError
from tests.api.conftest import AUTH_ORG_ID, _create_test_app
from tests.fakes.fake_auth import FakeAuth

pytestmark = pytest.mark.asyncio

FWD = {"Authorization": "Bearer idp-token", "X-Authz-Token": "authz-token"}


class StubSource:
    def __init__(self) -> None:
        self.targets: list[SourceTarget] = []
        self.error: Exception | None = None
        self.calls: list[Mapping[str, str]] = []

    async def fetch_all(self, *, forwarded_headers: Mapping[str, str]) -> list[SourceTarget]:
        self.calls.append(dict(forwarded_headers))
        if self.error:
            raise self.error
        return list(self.targets)


@pytest.fixture
def stub_source() -> StubSource:
    return StubSource()


async def _app_for(database_url: str, role: str, workspace_id: uuid.UUID, stub: StubSource):
    auth = FakeAuth(role=role, workspace_id=workspace_id, org_id=AUTH_ORG_ID)
    return _create_test_app(database_url, auth, overrides={TargetSource: stub})


@pytest.fixture
async def admin_sync_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, stub_source: StubSource
) -> AsyncIterator[AsyncClient]:
    app = await _app_for(database_url, "admin", workspace_id, stub_source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


@pytest.fixture
async def viewer_sync_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, stub_source: StubSource
) -> AsyncIterator[AsyncClient]:
    app = await _app_for(database_url, "viewer", workspace_id, stub_source)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await app.state.container[AsyncEngine].dispose()


def _src(name: str, version: int = 1) -> SourceTarget:
    return SourceTarget(uuid.uuid4(), name, "single_protein", "Mtb", None, version)


async def test_admin_sync_upserts_mirror_and_forwards_only_auth_headers(
    admin_sync_client: AsyncClient, stub_source: StubSource
) -> None:
    stub_source.targets = [_src("NadD"), _src("AspS")]

    resp = await admin_sync_client.post(
        "/api/v1/targets/sync", headers={**FWD, "X-Service-Key": "must-not-forward"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"fetched": 2, "created": 2, "updated": 0, "skipped": 0}
    assert stub_source.calls == [{"authorization": "Bearer idp-token", "x-authz-token": "authz-token"}]

    listed = await admin_sync_client.get("/api/v1/targets")
    names = sorted(t["name"] for t in listed.json()["items"])
    assert names == ["AspS", "NadD"]
    assert {t["id"] for t in listed.json()["items"]} == {str(t.id) for t in stub_source.targets}

    # Second forced sync: nothing changed → all skipped.
    again = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert again.json() == {"fetched": 2, "created": 0, "updated": 0, "skipped": 2}


async def test_sync_requires_admin(viewer_sync_client: AsyncClient) -> None:
    resp = await viewer_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert resp.status_code == 403


async def test_sync_surfaces_prot_cellar_auth_and_outage(
    admin_sync_client: AsyncClient, stub_source: StubSource
) -> None:
    stub_source.error = AuthorizationError("prot-cellar refused (403): editor required")
    resp = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert resp.status_code == 403
    assert "editor" in resp.json()["message"]

    stub_source.error = ServiceUnavailableError("prot-cellar unreachable")
    resp = await admin_sync_client.post("/api/v1/targets/sync", headers=FWD)
    assert resp.status_code == 503


async def test_list_refreshes_best_effort_and_serves_mirror_when_source_fails(
    viewer_sync_client: AsyncClient, stub_source: StubSource, make_target
) -> None:
    seeded = await make_target("Seeded")
    stub_source.error = ServiceUnavailableError("down")

    resp = await viewer_sync_client.get("/api/v1/targets", headers=FWD)
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()["items"]] == [seeded]
    assert len(stub_source.calls) == 1

    # Fresh (attempt marked) → no second call within the TTL.
    await viewer_sync_client.get("/api/v1/targets", headers=FWD)
    assert len(stub_source.calls) == 1


async def test_list_without_forwardable_auth_skips_refresh(
    admin_sync_client: AsyncClient, stub_source: StubSource
) -> None:
    resp = await admin_sync_client.get("/api/v1/targets")  # FakeAuth path: no Duar headers
    assert resp.status_code == 200
    assert stub_source.calls == []


async def test_local_mutation_routes_are_gone(admin_sync_client: AsyncClient) -> None:
    assert (await admin_sync_client.post("/api/v1/targets", json={"name": "x", "target_type": "single_protein"})).status_code == 405
    tid = uuid.uuid4()
    assert (await admin_sync_client.patch(f"/api/v1/targets/{tid}", json={"name": "x"})).status_code == 405
    assert (await admin_sync_client.delete(f"/api/v1/targets/{tid}")).status_code == 405
```

Note: `make_target` (Task 4) seeds through `api_app`'s container; `viewer_sync_client` is a different app on the same DB and workspace — committed rows are visible.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_targets_sync.py -v --tb=short`
Expected: FAIL — `TypeError: _create_test_app() got an unexpected keyword argument 'overrides'`.

- [ ] **Step 3: Container `overrides` seam**

In `backend/src/cellar/infrastructure/di/container.py`:

```python
from collections.abc import Mapping

from lagom import Container, Singleton
...
def create_container(
    db_settings: DatabaseSettings | None = None,
    *,
    overrides: Mapping[type, object] | None = None,
) -> Container:
    """Build and return the fully-wired DI container.

    ``overrides`` pre-registers ready-made instances (tests stub external
    adapters such as ``TargetSource`` here). Registrars that provide a
    swappable external adapter must guard with ``if X not in
    container.defined_types`` — Lagom raises on a duplicate ``define``.
    """
    container = Container()
    for dep_type, instance in (overrides or {}).items():
        container.define(dep_type, Singleton(_constant(instance)))

    register_core(container, db_settings)
    ...


def _constant(value: object):
    # A zero-arg resolver. (A `lambda value=value: value` would have ONE
    # parameter and Lagom would pass the container into it.)
    return lambda: value
```

In `tests/api/conftest.py` change the signature to `def _create_test_app(database_url: str, fake_auth: FakeAuth, overrides: Mapping[type, object] | None = None) -> FastAPI:` (import `Mapping` from `collections.abc`) and pass `create_container(db_settings, overrides=overrides)`.

- [ ] **Step 4: DI wiring in `_screening.py`**

Add imports:

```python
import httpx

from cellar.application.screening.sync_targets import SyncFreshness, SyncTargetsFromProtCellar
from cellar.application.screening.target_source import TargetSource
from cellar.infrastructure.prot_cellar.settings import ProtCellarSettings
from cellar.infrastructure.prot_cellar.target_source import HttpTargetSource
```

Replace the `# --- Targets ---` block with:

```python
    # --- Targets (read-only mirror of prot-cellar) ---
    # TargetSource is guarded so create_container(overrides={TargetSource: stub})
    # can pre-register an in-memory source for API tests.
    if TargetSource not in container.defined_types:
        container.define(
            TargetSource,
            Singleton(lambda c: HttpTargetSource(c[httpx.AsyncClient], ProtCellarSettings())),
        )
    container.define(SyncFreshness, Singleton(SyncFreshness))

    def _sync_targets(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SyncTargetsFromProtCellar(
            uow, SQLAlchemyTargetRepository(uow), c[TargetSource], c[SyncFreshness]
        )

    def _list_targets(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListTargets(uow, SQLAlchemyTargetRepository(uow), sync=c[SyncTargetsFromProtCellar])

    def _get_target(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetTarget(uow, SQLAlchemyTargetRepository(uow))

    container.define(SyncTargetsFromProtCellar, _sync_targets)
    container.define(ListTargets, _list_targets)
    container.define(GetTarget, _get_target)
```

(Delete the old `_target_query` helper.)

- [ ] **Step 5: `ListTargets` best-effort refresh**

In `get_target.py`:

```python
from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog
from returns.result import Failure, Result, Success

from cellar.application.screening.sync_targets import SyncTargetsCommand, SyncTargetsFromProtCellar
...
_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class ListTargetsQuery(Query):
    workspace_id: uuid.UUID
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    # The caller's Duar headers, forwarded to prot-cellar for the best-effort
    # mirror refresh. Empty (e.g. FakeAuth in tests) = skip the refresh.
    forwarded_headers: Mapping[str, str] = field(default_factory=dict)


class ListTargets:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: TargetRepository,
        sync: SyncTargetsFromProtCellar | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._sync = sync

    async def __call__(
        self, input: ListTargetsQuery, auth: AuthContext | None = None
    ) -> Result[PageResult[Target], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        # Best-effort: a stale mirror is served rather than failing the list.
        # The sync use case logs the reason; viewers hitting prot-cellar's
        # editor requirement land here on every TTL lapse — expected.
        if self._sync is not None and input.forwarded_headers:
            await self._sync(
                SyncTargetsCommand(
                    workspace_id=input.workspace_id,
                    forwarded_headers=input.forwarded_headers,
                    force=False,
                ),
                auth=auth,
            )

        async with self._uow:
            ... (existing body unchanged)
```

- [ ] **Step 6: Route + dependency**

`interface/dependencies/_screening.py`: import `SyncTargetsFromProtCellar`, add `"SyncTargetsDep"` to `__all__` (alphabetical, near `"ListTargetsDep"`), and:

```python
SyncTargetsDep = Annotated[
    SyncTargetsFromProtCellar, Depends(_get_use_case(SyncTargetsFromProtCellar))
]
```

`interface/routes/targets.py`:

```python
from fastapi import APIRouter, Request
...
from cellar.application.screening.sync_targets import SyncReport, SyncTargetsCommand
from cellar.interface.dependencies import (AuthDep, GetTargetDep, ListTargetsDep, SyncTargetsDep)

# Only the caller's own Duar credentials travel to prot-cellar (shared realm).
_FORWARDED_HEADERS = ("authorization", "x-authz-token")


def _forwarded_auth(request: Request) -> dict[str, str]:
    return {h: v for h in _FORWARDED_HEADERS if (v := request.headers.get(h))}


class TargetSyncReportResponse(BaseModel):
    fetched: int
    created: int
    updated: int
    skipped: int

    @classmethod
    def from_report(cls, r: SyncReport) -> TargetSyncReportResponse:
        return cls(fetched=r.fetched, created=r.created, updated=r.updated, skipped=r.skipped)


@router.post("/targets/sync", response_model=TargetSyncReportResponse, tags=["targets"])
async def sync_targets(
    request: Request, auth: AuthDep, uc: SyncTargetsDep
) -> TargetSyncReportResponse:
    """Admin: pull the full target catalog from prot-cellar into the local mirror."""
    cmd = SyncTargetsCommand(
        workspace_id=auth.workspace_id, forwarded_headers=_forwarded_auth(request), force=True
    )
    return TargetSyncReportResponse.from_report(result_to_response(await uc(cmd, auth=auth)))
```

Place `sync_targets` **before** `get_target` (`/targets/{target_id}`) and add `request: Request` to `list_targets`, passing `forwarded_headers=_forwarded_auth(request)` into `ListTargetsQuery`.

`docker-compose.prod.yml` backend `environment:` — add `PROT_CELLAR_URL: ${PROT_CELLAR_URL:-http://localhost:8001}` after `DUAR_URL`. Root `.env.example`: add under the Duar/backend section `PROT_CELLAR_URL=http://localhost:8001` with the comment `# prot-cellar API (owns the target catalog; mirrored via admin → Targets)`.

- [ ] **Step 7: Run the tests**

Run: `cd backend && uv run pytest tests/api/test_targets_sync.py tests/api/test_protocol_run_targets.py -v --tb=short && uv run pytest tests/unit -q --tb=short && uv run lint-imports`
Expected: all PASS; import-linter kept (infrastructure→application import of `TargetSource` is allowed; interface imports application).

- [ ] **Step 8: Commit**

```bash
git add backend/src/cellar/application/screening/get_target.py backend/src/cellar/infrastructure/di/container.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_screening.py backend/src/cellar/interface/routes/targets.py backend/tests/api/conftest.py backend/tests/api/test_targets_sync.py docker-compose.prod.yml .env.example
git commit -m "feat(targets): POST /targets/sync (admin) + best-effort mirror refresh on GET /targets" -- backend/src/cellar/application/screening/get_target.py backend/src/cellar/infrastructure/di/container.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/interface/dependencies/_screening.py backend/src/cellar/interface/routes/targets.py backend/tests/api/conftest.py backend/tests/api/test_targets_sync.py docker-compose.prod.yml .env.example
```

---

### Task 6: Frontend — runtime config, orval regen, types, hooks

**Files:**
- Modify: `frontend/src/app/api/config/route.ts`, `frontend/src/app/api/config/route.test.ts`
- Modify: `frontend/src/shared/lib/app-config.tsx`
- Modify: `frontend/.env.example`, root `.env.example`, `docker-compose.prod.yml:71-79`
- Regenerate: `frontend/src/shared/lib/api/model/**`, `frontend/src/shared/lib/api/targets/targets.ts`
- Modify: `frontend/src/features/screening-assay/types/index.ts:106-123, 407-418, 580-600`
- Modify: `frontend/src/features/screening-assay/hooks/use-targets.ts`

**Interfaces:**
- Produces: `AppConfig.protCellarUrl: string` (default `http://localhost:3001`); `Target = TargetResponse`; `TargetSyncReport = TargetSyncReportResponse`; `useTargets(): UseQueryResult<Target[]>` (all pages); `useSyncTargets(): UseMutationResult<TargetSyncReport>`; `TargetType` +3; `TARGET_TYPE_LABELS` +3.

- [ ] **Step 1: Failing config test**

Append to `frontend/src/app/api/config/route.test.ts` inside the `describe`:

```ts
  it("exposes the prot-cellar UI url with a dev default", async () => {
    vi.stubEnv("APP_PROT_CELLAR_URL", "");
    expect((await GET().json()).protCellarUrl).toBe("http://localhost:3001");

    vi.stubEnv("APP_PROT_CELLAR_URL", "https://prot-cellar.example");
    expect((await GET().json()).protCellarUrl).toBe("https://prot-cellar.example");
  });
```

Run: `cd frontend && pnpm test src/app/api/config` → FAIL (`undefined` ≠ `http://localhost:3001`).

- [ ] **Step 2: Runtime config**

`route.ts`: add `protCellarUrl: process.env.APP_PROT_CELLAR_URL || "http://localhost:3001",` after `duarUrl`.

`app-config.tsx`: add `protCellarUrl: string;` to `AppConfig` (after `duarUrl`), `protCellarUrl: "http://localhost:3001",` to `defaultConfig`, and `protCellarUrl: process.env.NEXT_PUBLIC_PROT_CELLAR_URL ?? defaultConfig.protCellarUrl,` in the `fetchAppConfig` fallback.

`frontend/.env.example`: add `APP_PROT_CELLAR_URL=http://localhost:3001` after `APP_DUAR_URL`, and `NEXT_PUBLIC_PROT_CELLAR_URL=http://localhost:3001` in the dev-fallback block. Root `.env.example`: add `APP_PROT_CELLAR_URL=http://localhost:3001` after `APP_DUAR_URL`. `docker-compose.prod.yml` frontend env: `APP_PROT_CELLAR_URL: ${APP_PROT_CELLAR_URL:-http://localhost:3001}`.

Check the existing `settings/page.test.tsx` config literal (it builds a full `AppConfig` object) — add `protCellarUrl: ""` to it so TypeScript stays happy. `grep -rn "uiBuildDate:" frontend/src --include='*.test.tsx'` finds every such literal.

Run: `cd frontend && pnpm test src/app/api/config` → PASS.

- [ ] **Step 3: Regenerate orval types**

Backend must be up on `:8000` with the Task 5 routes: from repo root `make dev-be` (loads root `.env`, which must have `DUAR_SERVICE_KEY`). Then:

```bash
cd frontend && pnpm generate:api
git status --short src/shared/lib/api | head -40
```

Expected: `model/targetSyncReportResponse.ts` created; `model/targetResponse.ts` gains `chembl_id`; `api/targets/targets.ts` loses the create/update/delete hooks. orval never prunes `model/index.ts` — delete these 18 lines by hand (`createTargetRequest*` at ~473-480, `updateTargetRequest*` at ~1567-1576) and `git rm` the matching files:

```bash
cd frontend/src/shared/lib/api/model && git rm -q createTargetRequest*.ts updateTargetRequest*.ts && sed -i '' "/createTargetRequest\|updateTargetRequest/d" index.ts
```

Run: `cd frontend && pnpm tsc --noEmit -p tsconfig.json` → errors only in files this task/Task 7 will touch (`types/index.ts`, dialogs, target-list). Stop the backend afterwards if you started it (`make stop`).

- [ ] **Step 4: Types**

In `frontend/src/features/screening-assay/types/index.ts`:

1. Add `TargetResponse, TargetSyncReportResponse` to the `@/shared/lib/api/model` import block at the top (alongside `TargetRefResponse`).
2. `TargetType` union: add `| "domain" | "protein_protein_interaction" | "unknown"`; `TARGET_TYPE_LABELS`: add `domain: "Domain"`, `protein_protein_interaction: "Protein–Protein Interaction"`, `unknown: "Unknown"`.
3. Replace the hand-written `export interface Target {...}` (lines ~407-418) with:

```ts
/** Read-only mirror of a prot-cellar target. Aliases the orval DTO — never
 *  redefine its shape. `target_type` is widened by `TargetType` at use sites. */
export type Target = TargetResponse;

/** Result of `POST /targets/sync` (admin → Targets → Sync from Prot-Cellar). */
export type TargetSyncReport = TargetSyncReportResponse;
```

4. Delete `CreateTargetInput` and `UpdateTargetInput` interfaces.

- [ ] **Step 5: Hooks**

Replace `frontend/src/features/screening-assay/hooks/use-targets.ts`:

```ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { PaginatedResponse } from "@/shared/types/pagination";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Target, TargetSyncReport } from "../types";

export const TARGETS_KEY = ["targets"];

/** Every target in the mirror. Pickers must see the whole catalog, so this
 *  follows the cursor to the end instead of taking the server's default page. */
async function fetchAllTargets(): Promise<Target[]> {
  const items: Target[] = [];
  let cursor: string | null = null;
  do {
    const page: PaginatedResponse<Target> = await customInstance({
      url: `${API_V1}/targets`,
      method: "GET",
      params: { limit: 200, ...(cursor ? { cursor } : {}) },
    });
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}

export function useTargets() {
  return useQuery({ queryKey: TARGETS_KEY, queryFn: fetchAllTargets });
}

export function useTarget(id: string | undefined) {
  return useQuery({
    queryKey: [...TARGETS_KEY, id],
    queryFn: () => customInstance<Target>({ url: `${API_V1}/targets/${id}`, method: "GET" }),
    enabled: !!id,
  });
}

/** Admin-only full sync from prot-cellar. Errors carry the backend message
 *  (e.g. "prot-cellar refused … requires the editor role"). */
export function useSyncTargets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      customInstance<TargetSyncReport>({ url: `${API_V1}/targets/sync`, method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TARGETS_KEY });
    },
  });
}
```

Check `PaginatedResponse` exists in `@/shared/types/pagination` (`grep -n "export interface PaginatedResponse\|export type PaginatedResponse" frontend/src/shared/types/pagination.ts`); if it is named differently, use that name.

- [ ] **Step 6: Typecheck + lint (expect only dialog/list errors)**

Run: `cd frontend && pnpm tsc --noEmit -p tsconfig.json 2>&1 | grep -v "create-target-dialog\|edit-target-dialog\|target-list\|target-multi-select\|screening-dashboard"`
Expected: no other errors. `pnpm lint` may flag the two dialogs (they die in Task 7).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/api/config frontend/src/shared/lib/app-config.tsx frontend/.env.example .env.example docker-compose.prod.yml frontend/src/shared/lib/api frontend/src/features/screening-assay/types/index.ts frontend/src/features/screening-assay/hooks/use-targets.ts "frontend/src/app/(dashboard)/settings/page.test.tsx"
git commit -m "feat(frontend): prot-cellar runtime config, regenerated target DTOs, all-pages useTargets + useSyncTargets" -- frontend/src/app/api/config frontend/src/shared/lib/app-config.tsx frontend/.env.example .env.example docker-compose.prod.yml frontend/src/shared/lib/api frontend/src/features/screening-assay/types/index.ts frontend/src/features/screening-assay/hooks/use-targets.ts "frontend/src/app/(dashboard)/settings/page.test.tsx"
```

---

### Task 7: Frontend — admin Targets page, read-only list, picker link, dialogs removed

**Files:**
- Create: `frontend/src/features/screening-assay/components/admin-targets-page.tsx`
- Create: `frontend/src/features/screening-assay/components/admin-targets-page.test.tsx`
- Create: `frontend/src/app/(dashboard)/admin/targets/page.tsx`
- Modify: `frontend/src/features/screening-assay/components/target-list.tsx`
- Modify: `frontend/src/features/screening-assay/components/target-multi-select.tsx` (+ `.test.tsx`)
- Modify: `frontend/src/features/screening-assay/components/screening-dashboard.tsx`
- Modify: `frontend/src/features/screening-assay/components/detail-tabs/design-tab-protocol-card.test.tsx:50`
- Modify: `frontend/src/shared/lib/navigation.ts`
- Delete: `frontend/src/features/screening-assay/components/create-target-dialog.tsx`, `edit-target-dialog.tsx`

**Interfaces:**
- Consumes: Task 6 `useTargets`, `useSyncTargets`, `Target`, `TargetSyncReport`, `useAppConfig().protCellarUrl`.
- Produces: `<AdminTargetsPage />`, `<TargetList />` (read-only, no props), route `/admin/targets`.

- [ ] **Step 1: Failing admin page test**

Create `frontend/src/features/screening-assay/components/admin-targets-page.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const targets = [
  {
    id: "t-1",
    workspace_id: "ws",
    name: "NadD",
    target_type: "single_protein",
    organism: "Mycobacterium tuberculosis",
    chembl_id: "CHEMBL4630874",
    gene_name: null,
    uniprot_id: null,
    ncbi_gene_id: null,
    description: null,
    target_class: null,
  },
];

let syncResult: () => Promise<unknown> = async () => ({
  fetched: 126,
  created: 3,
  updated: 1,
  skipped: 122,
});

const customInstance = vi.fn(async (args: { url: string; method: string }) => {
  if (args.url === "/api/v1/targets" && args.method === "GET") {
    return { items: targets, next_cursor: null };
  }
  if (args.url === "/api/v1/targets/sync" && args.method === "POST") return syncResult();
  throw new Error(`unexpected ${args.method} ${args.url}`);
});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args as never),
}));

import { AdminTargetsPage } from "./admin-targets-page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<AdminTargetsPage />, { wrapper });
}

describe("AdminTargetsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists mirrored targets read-only with a prot-cellar deep link", async () => {
    renderPage();
    expect(await screen.findByText("NadD")).toBeInTheDocument();
    expect(screen.getByText("Mycobacterium tuberculosis")).toBeInTheDocument();
    expect(screen.getByText("CHEMBL4630874")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open nadd in prot-cellar/i });
    expect(link).toHaveAttribute("href", "http://localhost:3001/targets/t-1");
    expect(screen.queryByRole("button", { name: /delete|edit/i })).not.toBeInTheDocument();
  });

  it("sync button reports counts on success", async () => {
    renderPage();
    await screen.findByText("NadD");
    fireEvent.click(screen.getByRole("button", { name: /sync from prot-cellar/i }));
    await waitFor(() => expect(screen.getByText(/126 fetched/i)).toBeInTheDocument());
    expect(screen.getByText(/3 created · 1 updated · 122 unchanged/i)).toBeInTheDocument();
  });

  it("sync button surfaces the backend error message", async () => {
    syncResult = async () => {
      throw new Error("API error: 403 — prot-cellar refused the request (403): editor required");
    };
    renderPage();
    await screen.findByText("NadD");
    fireEvent.click(screen.getByRole("button", { name: /sync from prot-cellar/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/editor required/i);
  });
});
```

Run: `cd frontend && pnpm test admin-targets-page` → FAIL (module not found).

- [ ] **Step 2: Read-only `TargetList`**

Replace `frontend/src/features/screening-assay/components/target-list.tsx`:

```tsx
"use client";

import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useAppConfig } from "@/shared/lib/app-config";
import { Crosshair, ExternalLink } from "lucide-react";
import { useTargets } from "../hooks/use-targets";
import { TARGET_TYPE_LABELS, type Target, type TargetType } from "../types";

/** Read-only mirror of prot-cellar's target catalog. Edits happen in
 *  prot-cellar; Admin → Targets pulls them across. */
export function TargetList() {
  const { data: targets, isLoading, error } = useTargets();
  const { protCellarUrl } = useAppConfig();

  if (isLoading) return <SkeletonList />;

  if (error) {
    return (
      <ErrorState
        message="Failed to load targets. Is the backend running?"
        details={error.message}
      />
    );
  }

  if (!targets?.length) {
    return (
      <EmptyState
        icon={Crosshair}
        title="No targets"
        description="Targets come from Prot-Cellar. Ask an admin to run Sync from Prot-Cellar (Admin → Targets)."
      />
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Organism</TableHead>
            <TableHead>ChEMBL</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {targets.map((target: Target) => (
            <TableRow key={target.id}>
              <TableCell className="font-medium">{target.name}</TableCell>
              <TableCell>
                <Badge variant="outline">
                  {TARGET_TYPE_LABELS[target.target_type as TargetType] ?? target.target_type}
                </Badge>
              </TableCell>
              <TableCell>{target.organism ?? "—"}</TableCell>
              <TableCell className="font-mono text-sm">{target.chembl_id ?? "—"}</TableCell>
              <TableCell>
                <a
                  href={`${protCellarUrl}/targets/${target.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Open ${target.name} in Prot-Cellar`}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 3: Admin page component + route + nav**

Create `frontend/src/features/screening-assay/components/admin-targets-page.tsx`:

```tsx
"use client";

import { PageHeader } from "@/shared/components/page-header";
import { Alert, AlertDescription } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { useAppConfig } from "@/shared/lib/app-config";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useSyncTargets } from "../hooks/use-targets";
import { TargetList } from "./target-list";

/** Admin → Targets: the mirror table plus the one explicit gesture that
 *  changes it — a full pull from prot-cellar (no limit; the backend pages
 *  through prot-cellar's cursor). */
export function AdminTargetsPage() {
  const { protCellarUrl } = useAppConfig();
  const sync = useSyncTargets();

  return (
    <>
      <PageHeader
        title="Targets"
        subtitle="Biological targets are owned by Prot-Cellar and mirrored here read-only."
      >
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <a href={`${protCellarUrl}/targets`} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="mr-2 h-4 w-4" />
              Manage in Prot-Cellar
            </a>
          </Button>
          <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
            <RefreshCw className={`mr-2 h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} />
            {sync.isPending ? "Syncing…" : "Sync from Prot-Cellar"}
          </Button>
        </div>
      </PageHeader>

      {sync.isSuccess && (
        <p className="mt-2 text-muted-foreground text-sm" data-testid="sync-report">
          {sync.data.fetched} fetched — {sync.data.created} created · {sync.data.updated} updated
          · {sync.data.skipped} unchanged
        </p>
      )}
      {sync.isError && (
        <Alert variant="destructive" className="mt-2">
          <AlertDescription>{sync.error.message}</AlertDescription>
        </Alert>
      )}

      <div className="mt-6">
        <TargetList />
      </div>
    </>
  );
}
```

If `@/shared/components/ui/alert` does not exist (`ls frontend/src/shared/components/ui/alert.tsx`), add it with `pnpm dlx shadcn@latest add alert` from `frontend/`. Confirm the `Alert` root renders `role="alert"` (shadcn's does).

Create `frontend/src/app/(dashboard)/admin/targets/page.tsx`:

```tsx
import { AdminTargetsPage } from "@/features/screening-assay/components/admin-targets-page";

export default function TargetsAdminPage() {
  return <AdminTargetsPage />;
}
```

`frontend/src/shared/lib/navigation.ts`: add `Crosshair` to the lucide import list (alphabetical, after `ClipboardList`) and insert `{ title: "Targets", href: "/admin/targets", icon: Crosshair },` in the "Organization" group's `children` right after the Data Sources entry.

Run: `cd frontend && pnpm test admin-targets-page` → 3 PASS. (The "126 fetched" text is split across the `<p>` — if `getByText(/126 fetched/)` fails on whitespace, assert on `screen.getByTestId("sync-report")` `toHaveTextContent` instead.)

- [ ] **Step 4: Screening dashboard + picker**

`screening-dashboard.tsx`:
- Remove `import { CreateTargetDialog } ...`, the `createTargetOpen` state, the `<CreateTargetDialog …/>` element, and `Plus` stays (used by New Protocol).
- Add `import Link from "next/link";` and `Settings2` to the lucide import.
- Replace the `{tab === "targets" && (<Button …>New Target</Button>)}` block with:

```tsx
          {tab === "targets" && (
            <Button asChild variant="outline">
              <Link href="/admin/targets">
                <Settings2 className="mr-2 h-4 w-4" />
                Manage targets
              </Link>
            </Button>
          )}
```

`target-multi-select.tsx`:
- Remove `import { CreateTargetDialog } …`, the `createOpen` state, `handleCreated`, and the trailing `<CreateTargetDialog …/>`.
- Add `import { useAppConfig } from "@/shared/lib/app-config";` and `ExternalLink` to the lucide import (drop `Plus`).
- Inside the component: `const { protCellarUrl } = useAppConfig();`
- Replace the "Create target…" `CommandItem` with:

```tsx
                <CommandItem
                  value="__manage_targets__"
                  onSelect={() => {
                    setOpen(false);
                    window.open(`${protCellarUrl}/targets`, "_blank", "noopener,noreferrer");
                  }}
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Manage in Prot-Cellar
                </CommandItem>
```

- Update the JSDoc: `an inline "Manage in Prot-Cellar" action opens the catalog owner in a new tab — targets are not created here.`

`target-multi-select.test.tsx`: in the `vi.mock("../hooks/use-targets", …)` drop the `useCreateTarget` line and the comment above it (keep `useTargets`); change the assertion `expect(screen.getByText(/create target/i))` → `expect(screen.getByText(/manage in prot-cellar/i))`. Add one test:

```tsx
  it("'Manage in Prot-Cellar' opens the catalog in a new tab", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    const item = screen
      .getByText(/manage in prot-cellar/i)
      .closest("[data-slot='command-item']") as HTMLElement;
    fireEvent.click(item);
    expect(open).toHaveBeenCalledWith("http://localhost:3001/targets", "_blank", "noopener,noreferrer");
    open.mockRestore();
  });
```

`design-tab-protocol-card.test.tsx:50`: delete the `useCreateTarget: () => …` line from the mock.

Delete the dialogs: `git rm frontend/src/features/screening-assay/components/create-target-dialog.tsx frontend/src/features/screening-assay/components/edit-target-dialog.tsx`.

- [ ] **Step 5: Verify**

Run: `cd frontend && pnpm tsc --noEmit -p tsconfig.json && pnpm lint && pnpm test`
Expected: typecheck clean, biome exit 0, all vitest suites green (including `target-filter.test.tsx`, `design-tab-protocol-card.test.tsx`).

Manual smoke (optional but recommended): `make dev` from repo root, log in, open `/admin/targets`, press **Sync from Prot-Cellar** with prot-cellar running on `:8001` (`cd ~/workspace/prot-cellar && make dev`). Expect "126 fetched — 126 created …", the table populated, and the picker in **New Protocol** listing all 126.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/features/screening-assay/components "frontend/src/app/(dashboard)/admin/targets" frontend/src/shared/lib/navigation.ts frontend/src/shared/components/ui/alert.tsx
git commit -m "feat(frontend): admin Targets page with Sync from Prot-Cellar; read-only target list; picker links to prot-cellar" -- frontend/src/features/screening-assay/components "frontend/src/app/(dashboard)/admin/targets" frontend/src/shared/lib/navigation.ts frontend/src/shared/components/ui/alert.tsx
```

(Drop `alert.tsx` from both commands if it already existed.)

---

### Task 8: Cutover script — remap legacy local targets onto the mirror

**Files:**
- Create: `backend/scripts/remap_targets_to_prot_cellar.py`
- Test: `backend/tests/integration/scripts/test_remap_targets_to_prot_cellar.py`

**Interfaces:**
- Produces: `async def plan_remap(session: AsyncSession, workspace_id: uuid.UUID) -> list[Action]`; `async def apply_remap(session: AsyncSession, actions: list[Action]) -> None`; `@dataclass(frozen=True) class Action: kind: Literal["remap", "drop"]; legacy_id: uuid.UUID; name: str; mirror_id: uuid.UUID | None; protocol_links: int; run_links: int`.
- Semantics: legacy = `source_version IS NULL`; match = case-insensitive name equality against a mirror row (`source_version IS NOT NULL`) in the same workspace. `remap` moves link rows (skipping duplicates), `drop` deletes link rows; both delete the legacy target. `--dry-run` is the default; `--apply` executes everything in one transaction.

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/scripts/test_remap_targets_to_prot_cellar.py` (create `backend/tests/integration/scripts/__init__.py` if the directory has no `__init__.py`):

```python
"""remap_targets_to_prot_cellar — legacy local targets → mirror rows by name."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from scripts.remap_targets_to_prot_cellar import Action, apply_remap, plan_remap

pytestmark = pytest.mark.asyncio

_USER = uuid.UUID("eeeeeeee-0000-0000-0000-000000000002")


async def _seed(session: AsyncSession, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    ids = {k: uuid.uuid4() for k in ("legacy_nadd", "mirror_nadd", "legacy_egfr", "proto", "run")}
    await session.execute(
        sa.text(
            "INSERT INTO targets (id, workspace_id, name, target_type, source_version) VALUES "
            "(:ln, :ws, 'NadD', 'single_protein', NULL), "
            "(:mn, :ws, 'nadd', 'single_protein', 7), "
            "(:le, :ws, 'Epidermal Growth Factor Receptor', 'single_protein', NULL)"
        ),
        {"ln": ids["legacy_nadd"], "mn": ids["mirror_nadd"], "le": ids["legacy_egfr"], "ws": ws},
    )
    await session.execute(
        sa.text(
            "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, is_locked, "
            "dose_unit, pos_control_signal, version, protocol_version, created_by) VALUES "
            "(:p, :ws, 'P', 'biochemical', 'active', false, 'uM', 'high', 1, 1, :u)"
        ),
        {"p": ids["proto"], "ws": ws, "u": _USER},
    )
    await session.execute(
        sa.text(
            "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, status, "
            "is_locked, version) VALUES (:r, :ws, :p, :d, :u, 'draft', false, 1)"
        ),
        {"r": ids["run"], "ws": ws, "p": ids["proto"], "d": date.today(), "u": _USER},
    )
    # legacy NadD linked to the run; the mirror NadD ALSO already linked to the same run
    # (dedupe case); legacy EGFR linked to the protocol.
    await session.execute(
        sa.text("INSERT INTO run_targets (run_id, target_id) VALUES (:r, :ln), (:r, :mn)"),
        {"r": ids["run"], "ln": ids["legacy_nadd"], "mn": ids["mirror_nadd"]},
    )
    await session.execute(
        sa.text("INSERT INTO protocol_targets (protocol_id, target_id) VALUES (:p, :le)"),
        {"p": ids["proto"], "le": ids["legacy_egfr"]},
    )
    return ids


async def _count(session: AsyncSession, sql: str, **params) -> int:
    return int(await session.scalar(sa.text(sql), params) or 0)


async def test_plan_then_apply(session_factory: async_sessionmaker[AsyncSession]) -> None:
    ws = uuid.uuid4()
    async with session_factory() as session, session.begin():
        ids = await _seed(session, ws)

    async with session_factory() as session:
        actions = await plan_remap(session, ws)
    assert sorted(actions, key=lambda a: a.name) == [
        Action("drop", ids["legacy_egfr"], "Epidermal Growth Factor Receptor", None, 1, 0),
        Action("remap", ids["legacy_nadd"], "NadD", ids["mirror_nadd"], 0, 1),
    ]

    async with session_factory() as session, session.begin():
        await apply_remap(session, actions)

    async with session_factory() as session:
        assert await _count(session, "SELECT count(*) FROM targets WHERE workspace_id=:ws", ws=ws) == 1
        assert await _count(session, "SELECT count(*) FROM run_targets WHERE run_id=:r", r=ids["run"]) == 1
        assert await _count(
            session, "SELECT count(*) FROM run_targets WHERE run_id=:r AND target_id=:t",
            r=ids["run"], t=ids["mirror_nadd"],
        ) == 1
        assert await _count(session, "SELECT count(*) FROM protocol_targets WHERE protocol_id=:p", p=ids["proto"]) == 0

    # cleanup (session_factory rows are committed; keep the shared test DB tidy)
    async with session_factory() as session, session.begin():
        await session.execute(sa.text("DELETE FROM runs WHERE id=:r"), {"r": ids["run"]})
        await session.execute(sa.text("DELETE FROM protocols WHERE id=:p"), {"p": ids["proto"]})
        await session.execute(sa.text("DELETE FROM targets WHERE workspace_id=:ws"), {"ws": ws})
```

Run: `cd backend && uv run pytest tests/integration/scripts/test_remap_targets_to_prot_cellar.py -v --tb=short` → FAIL (`ModuleNotFoundError: scripts.remap_targets_to_prot_cellar`). If `scripts` is not importable from tests, check how `tests/integration/scripts/` imports other scripts (`grep -rn "^from scripts\|^import scripts" backend/tests | head -2`) and mirror that.

- [ ] **Step 2: Write the script**

Create `backend/scripts/remap_targets_to_prot_cellar.py`:

```python
"""One-shot cutover: move legacy local targets onto their prot-cellar mirror rows.

Run AFTER the first admin "Sync from Prot-Cellar" (Admin → Targets), which
creates the mirror rows (``source_version IS NOT NULL``). For every legacy
row (``source_version IS NULL``):

- name matches a mirror row (case-insensitive) → **remap**: move its
  ``protocol_targets`` / ``run_targets`` links to the mirror id (skipping
  links the mirror already has), then delete the legacy row;
- no match → **drop**: delete its links and the row.

Default is a dry run that prints the plan. ``--apply`` executes it in one
transaction.

    cd backend && uv run python scripts/remap_targets_to_prot_cellar.py --workspace-id <uuid>
    cd backend && uv run python scripts/remap_targets_to_prot_cellar.py --workspace-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cellar.infrastructure.persistence.settings import DatabaseSettings


@dataclass(frozen=True)
class Action:
    kind: Literal["remap", "drop"]
    legacy_id: uuid.UUID
    name: str
    mirror_id: uuid.UUID | None
    protocol_links: int
    run_links: int


async def plan_remap(session: AsyncSession, workspace_id: uuid.UUID) -> list[Action]:
    rows = (
        await session.execute(
            sa.text(
                "SELECT l.id, l.name, m.id AS mirror_id, "
                "(SELECT count(*) FROM protocol_targets pt WHERE pt.target_id = l.id) AS pl, "
                "(SELECT count(*) FROM run_targets rt WHERE rt.target_id = l.id) AS rl "
                "FROM targets l "
                "LEFT JOIN targets m ON m.workspace_id = l.workspace_id "
                "  AND m.source_version IS NOT NULL AND lower(m.name) = lower(l.name) "
                "WHERE l.workspace_id = :ws AND l.source_version IS NULL "
                "ORDER BY l.name"
            ),
            {"ws": workspace_id},
        )
    ).all()
    return [
        Action(
            kind="remap" if mirror_id else "drop",
            legacy_id=lid,
            name=name,
            mirror_id=mirror_id,
            protocol_links=int(pl),
            run_links=int(rl),
        )
        for lid, name, mirror_id, pl, rl in rows
    ]


_MOVE = {
    "protocol_targets": (
        "INSERT INTO protocol_targets (protocol_id, target_id) "
        "SELECT protocol_id, :new FROM protocol_targets WHERE target_id = :old "
        "ON CONFLICT DO NOTHING"
    ),
    "run_targets": (
        "INSERT INTO run_targets (run_id, target_id) "
        "SELECT run_id, :new FROM run_targets WHERE target_id = :old "
        "ON CONFLICT DO NOTHING"
    ),
}


async def apply_remap(session: AsyncSession, actions: list[Action]) -> None:
    for a in actions:
        if a.kind == "remap":
            for stmt in _MOVE.values():
                await session.execute(sa.text(stmt), {"new": a.mirror_id, "old": a.legacy_id})
        for table in ("protocol_targets", "run_targets"):
            await session.execute(
                sa.text(f"DELETE FROM {table} WHERE target_id = :old"), {"old": a.legacy_id}
            )
        await session.execute(sa.text("DELETE FROM targets WHERE id = :old"), {"old": a.legacy_id})


def _print_plan(actions: list[Action]) -> None:
    if not actions:
        print("nothing to do — no legacy (source_version IS NULL) targets")
        return
    for a in actions:
        target = f"→ {a.mirror_id}" if a.kind == "remap" else "(no prot-cellar match)"
        print(
            f"{a.kind:5} {a.name!r:45} {target}  "
            f"[{a.protocol_links} protocol link(s), {a.run_links} run link(s)]"
        )


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace-id", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="Execute (default: dry run).")
    args = parser.parse_args()

    engine = create_async_engine(DatabaseSettings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        actions = await plan_remap(session, args.workspace_id)
        _print_plan(actions)
        if args.apply and actions:
            async with session.begin():
                await apply_remap(session, actions)
            print(f"applied {len(actions)} action(s)")
        elif actions:
            print("dry run — re-run with --apply to execute")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
```

Note the `ON CONFLICT DO NOTHING` relies on the composite primary keys of `protocol_targets` / `run_targets` (migration 051) — verify with `grep -n "primary_key=True" backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py | sed -n 1,8p`; both link columns are PK members.

- [ ] **Step 3: Run the test**

Run: `cd backend && uv run pytest tests/integration/scripts/test_remap_targets_to_prot_cellar.py -v --tb=short`
Expected: PASS.

- [ ] **Step 4: Run it for real on saclab-dev (dry-run first)**

Prerequisites: backend + prot-cellar running, admin sync executed once from `/admin/targets` (Task 7 smoke). Then:

```bash
cd backend && uv run python scripts/remap_targets_to_prot_cellar.py --workspace-id 442df0cf-e618-4938-a089-80ae2f1e43e7
```

Expected plan: `remap 'NadD' → <mirror id> [0 protocol, 4 run]`, and `drop` for the other 5 (COX-2 and EGFR show 1 protocol link each). Then `--apply`. Verify:

```bash
docker exec -i chem-vault2-postgres-1 psql -U cellar -d cellar -Atc "select count(*) filter (where source_version is null) legacy, count(*) mirror from targets; select count(*) from run_targets; select count(*) from protocol_targets;"
```

Expected: `0|126`, run_targets `4`, protocol_targets `0`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/remap_targets_to_prot_cellar.py backend/tests/integration/scripts
git commit -m "feat(scripts): remap legacy local targets onto prot-cellar mirror rows (dry-run default)" -- backend/scripts/remap_targets_to_prot_cellar.py backend/tests/integration/scripts
```

---

### Task 9: Final verification + status

- [ ] **Step 1: Full test sweep**

```bash
cd backend && uv run pytest -q --tb=short && uv run lint-imports
cd ../frontend && pnpm tsc --noEmit -p tsconfig.json && pnpm lint && pnpm test
```

Expected: all green.

- [ ] **Step 2: Spec deviations recorded**

Append a short "Shipped — deviations" section to the spec (`docs/superpowers/specs/2026-08-24-targets-from-prot-cellar-design.md`):
- 503 instead of 502 for outages (existing `ServiceUnavailableError`, no new error classes).
- `SyncReport` has no `pages`.
- Freshness is marked on attempt, not success (a failing prot-cellar is not re-hit within the TTL).
- No `upsert_many` / `find_all_by_workspace` on the repository — the existing `save` (get-or-add + update) and `find_by_workspace(limit=None)` suffice.
- A same-id row in a *different* workspace surfaces as a 403 from `EntityRepository.save`'s workspace guard rather than "skip + log" (cannot happen while both apps share Duar workspace ids).
- `TargetSource` stub seam for API tests = `create_container(overrides=…)`.
- Frontend `useTargets` follows the cursor to the end (the server default page is 50; the picker must see the whole catalog).

Commit with `git add -f` (docs/ is gitignored) and an explicit pathspec.

- [ ] **Step 3: Push**

`git push origin main` (or the feature branch you are on).
