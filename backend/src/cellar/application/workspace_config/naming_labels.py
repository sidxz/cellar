"""Short labels: admin overrides of how ontology terms read inside protocol names."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.naming_changes import (
    apply_naming_change,
    compute_naming_change,
    plan_label,
    refuse_collisions,
)
from cellar.domain.screening_assay.repository import ProtocolRepository, TargetRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError
from cellar.domain.shared.protocol_naming import (
    NamingContext,
    NamingTerm,
    organism_short_label,
    short_label,
)
from cellar.domain.workspace_config.naming_label import NamingLabel
from cellar.domain.workspace_config.repository import NamingLabelRepository

# Annotation slots whose terms appear in protocol names.
NAME_SLOTS = ("organism", "cell_line", "assay_format")


@dataclass(frozen=True, kw_only=True)
class ListNamingLabelsQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListNamingTermsInUseQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class CreateNamingLabelCommand(Command):
    workspace_id: uuid.UUID
    term_id: str
    term_label: str
    ontology_source: str
    short_label: str


@dataclass(frozen=True, kw_only=True)
class UpdateNamingLabelCommand(Command):
    workspace_id: uuid.UUID
    label_id: uuid.UUID
    short_label: str


@dataclass(frozen=True, kw_only=True)
class DeleteNamingLabelCommand(Command):
    workspace_id: uuid.UUID
    label_id: uuid.UUID


@dataclass(frozen=True)
class NamingTermInUse:
    """A term protocol names draw on, the label it renders as by default, and any override."""

    slot: str
    term_id: str
    term_label: str
    ontology_source: str
    protocol_count: int
    default_short_label: str
    override: NamingLabel | None


class ListNamingLabels:
    def __init__(self, uow: UnitOfWork, repo: NamingLabelRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListNamingLabelsQuery, auth: AuthContext | None = None
    ) -> Result[list[NamingLabel], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(await self._repo.find_by_workspace(input.workspace_id))


class ListNamingTermsInUse:
    """Every term a protocol name can draw on, with the short label it renders as."""

    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        target_repo: TargetRepository,
        label_repo: NamingLabelRepository,
    ) -> None:
        self._uow = uow
        self._protocols = protocol_repo
        self._targets = target_repo
        self._labels = label_repo

    async def __call__(
        self, input: ListNamingTermsInUseQuery, auth: AuthContext | None = None
    ) -> Result[list[NamingTermInUse], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            uses = await self._protocols.list_annotation_terms(input.workspace_id, NAME_SLOTS)
            organisms = await self._targets.list_organisms(input.workspace_id)
            overrides = {
                label.term_id: label
                for label in await self._labels.find_by_workspace(input.workspace_id)
            }
        defaults = NamingContext()
        out = [
            NamingTermInUse(
                slot=u.slot,
                term_id=u.term_id,
                term_label=u.label,
                ontology_source=u.ontology_source,
                protocol_count=u.protocol_count,
                default_short_label=short_label(
                    NamingTerm(u.term_id, u.label, u.ontology_source), defaults
                ),
                override=overrides.get(u.term_id),
            )
            for u in uses
        ]
        # Registry target organisms not yet used as an Organism facet: shown with their default.
        # They have no taxon id here, so an override waits until a protocol uses the organism.
        known = {u.label.lower() for u in uses if u.slot == "organism"}
        for organism in organisms:
            if organism.lower() not in known:
                out.append(
                    NamingTermInUse(
                        slot="target organism",
                        term_id="",
                        term_label=organism,
                        ontology_source="NCBITAXON",
                        protocol_count=0,
                        default_short_label=organism_short_label(organism, defaults),
                        override=None,
                    )
                )
        return Success(out)


async def _relabel(
    protocols: ProtocolRepository,
    names: ProtocolNameService,
    *,
    workspace_id: uuid.UUID,
    term_id: str,
    term_label: str,
    short_label: str | None,
    user_id: uuid.UUID | None,
) -> Result[None, DomainError]:
    """Plan, refuse a collision, then rename: the same steps the admin's preview showed."""
    plan = await plan_label(
        workspace_id=workspace_id,
        protocol_repo=protocols,
        names=names,
        term_id=term_id,
        term_label=term_label,
        short_label=short_label,
    )
    preview = await compute_naming_change(
        workspace_id=workspace_id, protocol_repo=protocols, names=names, plan=plan
    )
    refused = refuse_collisions(preview)
    if isinstance(refused, Failure):
        return refused
    await apply_naming_change(
        protocol_repo=protocols,
        names=names,
        plan=plan,
        preview=preview,
        reason=f"Short label changed: {term_label}",
        user_id=user_id,
    )
    return Success(None)


class CreateNamingLabel:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: NamingLabelRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        protocol_repo: ProtocolRepository,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._protocols = protocol_repo
        self._names = names

    async def __call__(
        self, input: CreateNamingLabelCommand, auth: AuthContext | None = None
    ) -> Result[NamingLabel, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            if await self._repo.find_by_term(input.workspace_id, input.term_id.strip()):
                return Failure(ConflictError(f"'{input.term_label}' already has a short label"))
            label = NamingLabel.create(
                workspace_id=input.workspace_id,
                term_id=input.term_id,
                term_label=input.term_label,
                ontology_source=input.ontology_source,
                short_label=input.short_label,
            )
            relabeled = await _relabel(
                self._protocols,
                self._names,
                workspace_id=input.workspace_id,
                term_id=label.term_id,
                term_label=label.term_label,
                short_label=label.short_label,
                user_id=auth.user_id if auth else None,
            )
            if isinstance(relabeled, Failure):
                return relabeled
            await self._repo.save(label)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(label)


class UpdateNamingLabel:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: NamingLabelRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        protocol_repo: ProtocolRepository,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._protocols = protocol_repo
        self._names = names

    async def __call__(
        self, input: UpdateNamingLabelCommand, auth: AuthContext | None = None
    ) -> Result[NamingLabel, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            label = await self._repo.find_by_id_in_workspace(input.workspace_id, input.label_id)
            if label is None:
                return Failure(NotFoundError("NamingLabel", str(input.label_id)))
            label.update(short_label=input.short_label)
            relabeled = await _relabel(
                self._protocols,
                self._names,
                workspace_id=input.workspace_id,
                term_id=label.term_id,
                term_label=label.term_label,
                short_label=label.short_label,
                user_id=auth.user_id if auth else None,
            )
            if isinstance(relabeled, Failure):
                return relabeled
            await self._repo.save(label)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(label)


class DeleteNamingLabel:
    """Back to the computed default; relabels like any other short label change."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: NamingLabelRepository,
        *,
        protocol_repo: ProtocolRepository,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._protocols = protocol_repo
        self._names = names

    async def __call__(
        self, input: DeleteNamingLabelCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            label = await self._repo.find_by_id_in_workspace(input.workspace_id, input.label_id)
            if label is None:
                return Failure(NotFoundError("NamingLabel", str(input.label_id)))
            relabeled = await _relabel(
                self._protocols,
                self._names,
                workspace_id=input.workspace_id,
                term_id=label.term_id,
                term_label=label.term_label,
                short_label=None,
                user_id=auth.user_id if auth else None,
            )
            if isinstance(relabeled, Failure):
                return relabeled
            await self._repo.delete(input.workspace_id, label.id)
            await self._uow.commit()
        return Success(None)
