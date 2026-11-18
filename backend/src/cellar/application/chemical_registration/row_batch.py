"""Which batch a bulk-registration row is, from the batch IDs it carries.

One rule, used by the registration forecast, the Temporal worker and the
in-process fallback (spec 2026-11-18 column mapper §4):

* R1 — only real IDs match. An automatic alias (``<compound ID>-<ChemCellar
  batch suffix>``, ``derived_from_molecule_identifier_id`` set) says nothing
  about which source batch a ChemCellar batch is, so it never matches a row.
* R2 — the file's ID wins. An automatic alias holding a row's batch ID on
  another batch is removed, and the ID goes on the row's batch.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.inventory.create_batch import (
    CreateBatch,
    CreateBatchCommand,
    NewBatchIdentifier,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.shared.errors import DomainError

BATCH_ID_TYPE = "custom"


@dataclass(frozen=True)
class RowBatchId:
    identifier: str
    source: str


@dataclass(frozen=True)
class RowBatchMatch:
    kind: Literal["new", "existing", "problem"]
    batch: Batch | None = None
    missing: tuple[RowBatchId, ...] = ()
    # (batch_id, identifier_id) of automatic aliases to remove (R2)
    evict: tuple[tuple[uuid.UUID, uuid.UUID], ...] = ()
    problem: str | None = None


def row_batch_ids(raw: Sequence[dict[str, str]]) -> tuple[RowBatchId, ...]:
    """Item dicts ``{"identifier", "source"}`` → unique RowBatchIds, file order."""
    seen: set[str] = set()
    out: list[RowBatchId] = []
    for d in raw:
        text = (d.get("identifier") or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(RowBatchId(identifier=text, source=d.get("source") or "Bulk registration"))
    return tuple(out)


async def classify_row_batch(
    repo: BatchRepository,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID | None,
    batch_ids: Sequence[RowBatchId],
) -> RowBatchMatch:
    """``molecule_id`` None = the row's compound is new, so any real hit is another
    compound's batch."""
    real: dict[uuid.UUID, tuple[Batch, str]] = {}
    aliases: list[tuple[Batch, BatchIdentifier]] = []
    for bid in batch_ids:
        owner = await repo.find_by_external_identifier(workspace_id, bid.identifier)
        if owner is None:
            continue
        ident = next((i for i in owner.identifiers if i.identifier == bid.identifier), None)
        if ident is None:
            continue
        if ident.derived_from_molecule_identifier_id is None:
            real.setdefault(owner.id, (owner, bid.identifier))
        else:
            aliases.append((owner, ident))

    if len(real) > 1:
        (_, a), (_, b) = list(real.values())[:2]
        return RowBatchMatch("problem", problem=f"{a} and {b} belong to two different batches")
    if len(real) == 1:
        owner, text = next(iter(real.values()))
        if molecule_id is None or owner.molecule_id != molecule_id:
            return RowBatchMatch(
                "problem",
                problem=f"{text} already belongs to {owner.batch_number.value} (another compound)",
            )
        on_it = {i.identifier for i in owner.identifiers}
        return RowBatchMatch(
            "existing",
            batch=owner,
            missing=tuple(b for b in batch_ids if b.identifier not in on_it),
            evict=tuple((o.id, i.id) for o, i in aliases if o.id != owner.id),
        )
    return RowBatchMatch("new", evict=tuple((o.id, i.id) for o, i in aliases))


@dataclass(frozen=True, kw_only=True)
class ApplyRowBatchCommand(Command):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID
    batch_ids: tuple[RowBatchId, ...]
    create: CreateBatchCommand  # used only when the row is a new batch
    actor: uuid.UUID


@dataclass(frozen=True)
class RowBatchResult:
    action: Literal["created", "existing", "problem"]
    batch_id: uuid.UUID | None = None
    batch_number: str | None = None
    problem: str | None = None


class ApplyRowBatch:
    """Find or create the row's batch and store its batch IDs on it."""

    def __init__(
        self,
        uow: UnitOfWork,
        batch_repo: BatchRepository,
        create_batch: CreateBatch,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = batch_repo
        self._create_batch = create_batch
        self._dispatcher = dispatcher

    async def __call__(
        self, cmd: ApplyRowBatchCommand, auth: AuthContext | None = None
    ) -> Result[RowBatchResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, cmd.workspace_id)

        # 1. Classify, and drop automatic aliases that hold the row's IDs (R2).
        #    Committed on its own: the identifier rows are replaced on save, so
        #    moving a text between batches in one flush could trip the unique key.
        async with self._uow:
            match = await classify_row_batch(
                self._repo, cmd.workspace_id, cmd.molecule_id, cmd.batch_ids
            )
            if match.kind == "problem":
                return Success(RowBatchResult("problem", problem=match.problem))
            for owner_id, ident_id in match.evict:
                owner = await self._repo.find_by_id_in_workspace(cmd.workspace_id, owner_id)
                if owner is not None:
                    owner.remove_identifier(ident_id)
                    await self._repo.save(owner)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)

        # 2a. Existing batch: add the IDs it lacks; leave its amount, purity, salt alone.
        if match.kind == "existing":
            assert match.batch is not None
            async with self._uow:
                batch = await self._repo.find_by_id_in_workspace(cmd.workspace_id, match.batch.id)
                assert batch is not None
                for b in match.missing:
                    batch.add_identifier(
                        BatchIdentifier.create(
                            batch_id=batch.id,
                            identifier=b.identifier,
                            identifier_type=BATCH_ID_TYPE,
                            source=b.source,
                            registered_by=cmd.actor,
                        )
                    )
                if match.missing:
                    await self._repo.save(batch)
                events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(RowBatchResult("existing", batch.id, batch.batch_number.value))

        # 2b. New batch, born with the row's IDs (before automatic mirrors).
        created = await self._create_batch(
            replace(
                cmd.create,
                identifiers=tuple(
                    NewBatchIdentifier(b.identifier, BATCH_ID_TYPE, b.source)
                    for b in cmd.batch_ids
                ),
            ),
            auth=auth,
        )
        if isinstance(created, Failure):
            return created
        batch = created.unwrap().batch
        return Success(RowBatchResult("created", batch.id, batch.batch_number.value))
