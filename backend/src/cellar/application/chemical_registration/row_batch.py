"""Which batch a bulk-registration row is, from the batch IDs it carries.

One rule, used by the registration forecast, the Temporal worker and the
in-process fallback (spec 2026-11-18 column mapper §4):

* R1 — only real IDs match. An automatic alias (``<compound ID>-<ChemCellar
  batch suffix>``, ``derived_from_molecule_identifier_id`` set) says nothing
  about which source batch a ChemCellar batch is, so it never matches a row.
* R2 — the file's ID wins. An automatic alias holding a row's batch ID on
  another batch is removed, and the ID goes on the row's batch.

Only deciding IDs take part in R1/R2. A stored-only ID (``decides`` False, CDD
mapper spec 2026-11-18 §3a) is stored on the row's batch when no other batch
holds it, otherwise skipped with a warning; it never matches and is never a problem.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

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
    identifier_type: str = BATCH_ID_TYPE
    decides: bool = True  # False = stored only


@dataclass(frozen=True)
class RowBatchMatch:
    kind: Literal["new", "existing", "problem"]
    batch: Batch | None = None
    # IDs to store on the row's batch: what an existing batch lacks, or all a new
    # batch is born with.
    missing: tuple[RowBatchId, ...] = ()
    # (batch_id, identifier_id, text) of automatic aliases to remove (R2)
    evict: tuple[tuple[uuid.UUID, uuid.UUID, str], ...] = ()
    problem: str | None = None
    # Stored-only IDs another batch holds: (text, that batch's number).
    held: tuple[tuple[str, str], ...] = ()


def row_batch_ids(raw: Sequence[Mapping[str, Any]]) -> tuple[RowBatchId, ...]:
    """Item dicts ``{"identifier", "source", "identifier_type"?, "decides"?}`` →
    unique RowBatchIds, file order. A text given twice decides if either copy does."""
    out: dict[str, RowBatchId] = {}
    for d in raw:
        text = (d.get("identifier") or "").strip()
        if not text:
            continue
        bid = RowBatchId(
            identifier=text,
            source=d.get("source") or "Bulk registration",
            identifier_type=d.get("identifier_type") or BATCH_ID_TYPE,
            decides=d.get("decides", True),
        )
        if text not in out or (bid.decides and not out[text].decides):
            out[text] = bid
    return tuple(out.values())


def skipped_batch_id_warnings(held: Sequence[tuple[str, str]], this: str) -> tuple[str, ...]:
    return tuple(f"'{v}' is already an ID of batch {b}; not stored on {this}" for v, b in held)


async def classify_row_batch(
    repo: BatchRepository,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID | None,
    batch_ids: Sequence[RowBatchId],
) -> RowBatchMatch:
    """``molecule_id`` None = the row's compound is new, so any real hit is another
    compound's batch."""
    deciding = [b for b in batch_ids if b.decides]
    real: dict[uuid.UUID, tuple[Batch, str]] = {}
    aliases: list[tuple[Batch, BatchIdentifier]] = []
    for bid in deciding:
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
        free, held = await _stored_only(repo, workspace_id, batch_ids, owner, on_it)
        return RowBatchMatch(
            "existing",
            batch=owner,
            missing=(*(b for b in deciding if b.identifier not in on_it), *free),
            evict=tuple((o.id, i.id, i.identifier) for o, i in aliases if o.id != owner.id),
            held=held,
        )
    free, held = await _stored_only(repo, workspace_id, batch_ids, None, set())
    return RowBatchMatch(
        "new",
        missing=(*deciding, *free),
        evict=tuple((o.id, i.id, i.identifier) for o, i in aliases),
        held=held,
    )


async def _stored_only(
    repo: BatchRepository,
    workspace_id: uuid.UUID,
    batch_ids: Sequence[RowBatchId],
    row_batch: Batch | None,
    on_it: set[str],
) -> tuple[tuple[RowBatchId, ...], tuple[tuple[str, str], ...]]:
    """Split the row's stored-only IDs it lacks into (free to store, held by
    another batch as (text, batch number))."""
    free: list[RowBatchId] = []
    held: list[tuple[str, str]] = []
    # ponytail: one lookup per stored-only ID; batch them per chunk if a full
    # vault run proves too slow.
    for bid in batch_ids:
        if bid.decides or bid.identifier in on_it:
            continue
        owner = await repo.find_by_external_identifier(workspace_id, bid.identifier)
        if owner is None:
            free.append(bid)
        elif row_batch is None or owner.id != row_batch.id:
            held.append((bid.identifier, owner.batch_number.value))
    return tuple(free), tuple(held)


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
    ids_added: int = 0  # batch IDs this call stored on the batch (new or existing)
    skipped: tuple[str, ...] = ()  # stored-only IDs another batch holds, one warning each


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

        async with self._uow:
            match = await classify_row_batch(
                self._repo, cmd.workspace_id, cmd.molecule_id, cmd.batch_ids
            )
        if match.kind == "problem":
            return Success(RowBatchResult("problem", problem=match.problem))

        # R2: an ID an automatic alias holds moves to the row's batch only once that
        # batch exists, in the transaction that removes the alias, so a failure on the
        # way leaves every alias where it was.
        moved = {text for _, _, text in match.evict}
        if match.kind == "existing":
            # Existing batch: add the IDs it lacks; leave its amount, purity, salt alone.
            assert match.batch is not None
            batch_id, later = match.batch.id, match.missing
        else:
            # New batch, born with the row's IDs (before automatic mirrors).
            created = await self._create_batch(
                replace(
                    cmd.create,
                    identifiers=tuple(
                        NewBatchIdentifier(b.identifier, b.identifier_type, b.source)
                        for b in match.missing
                        if b.identifier not in moved
                    ),
                ),
                auth=auth,
            )
            if isinstance(created, Failure):
                return created
            batch_id = created.unwrap().batch.id
            later = tuple(b for b in match.missing if b.identifier in moved)
        number = await self._store(cmd, batch_id, match.evict, later)
        return Success(
            RowBatchResult(
                "existing" if match.kind == "existing" else "created",
                batch_id,
                number,
                ids_added=len(match.missing),
                skipped=skipped_batch_id_warnings(match.held, number),
            )
        )

    async def _store(
        self,
        cmd: ApplyRowBatchCommand,
        batch_id: uuid.UUID,
        evict: Sequence[tuple[uuid.UUID, uuid.UUID, str]],
        ids: Sequence[RowBatchId],
    ) -> str:
        """Remove the automatic aliases, then add ``ids`` to the batch, in one
        transaction. Returns the batch's number."""
        async with self._uow:
            for owner_id, ident_id, _ in evict:
                owner = await self._repo.find_by_id_in_workspace(cmd.workspace_id, owner_id)
                if owner is not None:
                    owner.remove_identifier(ident_id)
                    await self._repo.save(owner)
            if evict:
                # Identifier rows are replaced on save: the removals reach the database
                # before another batch takes their text, or the unique key trips.
                await self._uow.session.flush()
            batch = await self._repo.find_by_id_in_workspace(cmd.workspace_id, batch_id)
            assert batch is not None
            for b in ids:
                batch.add_identifier(
                    BatchIdentifier.create(
                        batch_id=batch.id,
                        identifier=b.identifier,
                        identifier_type=b.identifier_type,
                        source=b.source,
                        registered_by=cmd.actor,
                    )
                )
            if ids:
                await self._repo.save(batch)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return batch.batch_number.value
