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
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ServiceUnavailableError
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
        Target.from_mirror(
            id=t_changed,
            workspace_id=WS,
            name="Old",
            target_type=TargetType.SINGLE_PROTEIN,
            organism=None,
            chembl_id=None,
            source_version=1,
        ),
        Target.from_mirror(
            id=t_same,
            workspace_id=WS,
            name="Same",
            target_type=TargetType.SINGLE_PROTEIN,
            organism=None,
            chembl_id=None,
            source_version=4,
        ),
    ]
    source = FakeSource(
        [
            _src(t_new, "New"),
            _src(t_changed, "Renamed", version=2),
            _src(t_same, "Same", version=4),
        ]
    )
    uc, uow, repo, _ = _build(source, existing)

    result = await uc(
        SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True),
        auth=FakeAuth(),
    )

    assert result == Success(SyncReport(fetched=3, created=1, updated=1, skipped=1))
    assert {t.id for t in repo.saved} == {t_new, t_changed}
    assert repo.rows[t_changed].name == "Renamed"
    assert repo.rows[t_changed].source_version == 2
    assert uow.commits == 1
    assert source.calls == [HEADERS]


async def test_non_forced_sync_is_noop_while_fresh_then_refetches_after_ttl(monkeypatch):
    source = FakeSource([_src(uuid.uuid4(), "A")])
    uc, _, _, _fresh = _build(source, ttl=300.0)
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
    await uc(
        SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True),
        auth=admin,
    )
    await uc(
        SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True),
        auth=admin,
    )
    assert len(source.calls) == 2

    with pytest.raises(AuthorizationError):
        await uc(
            SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True),
            auth=FakeAuth(workspace_role="editor", is_admin=False),
        )


async def test_source_errors_become_failures_and_still_mark_freshness():
    source = FakeSource(error=ServiceUnavailableError("prot-cellar unreachable"))
    uc, uow, _, fresh = _build(source)
    result = await uc(
        SyncTargetsCommand(workspace_id=WS, forwarded_headers=HEADERS, force=True),
        auth=FakeAuth(),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ServiceUnavailableError)
    assert uow.commits == 0
    assert fresh.is_fresh(WS)  # a failing source is not retried until TTL lapses


async def test_rejects_other_workspace():
    uc, _, _, _ = _build(FakeSource())
    with pytest.raises(NotFoundError):
        await uc(
            SyncTargetsCommand(workspace_id=uuid.uuid4(), forwarded_headers=HEADERS, force=True),
            auth=FakeAuth(),
        )
