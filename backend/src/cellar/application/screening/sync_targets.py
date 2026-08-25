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
from cellar.domain.shared.errors import DomainError, ServiceUnavailableError

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
            _log.warning(
                "targets.sync.failed", workspace_id=str(input.workspace_id), reason=str(exc)
            )
            return Failure(exc)
        except Exception as exc:  # any adapter bug must not 500 the caller (Critical 1)
            _log.warning(
                "targets.sync.failed", workspace_id=str(input.workspace_id), reason=repr(exc)
            )
            return Failure(
                ServiceUnavailableError(f"prot-cellar returned an unusable response: {exc!r}")
            )

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

        report = SyncReport(
            fetched=len(fetched), created=created, updated=updated, skipped=skipped
        )
        _log.info(
            "targets.sync.completed", workspace_id=str(input.workspace_id), **report.__dict__
        )
        return Success(report)
