"""Synthesis route use cases — CRUD + state transitions + step management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.enums import (
    ReagentRole,
    RouteScale,
    RouteSource,
    RouteStatus,
    RouteType,
)
from cellar.domain.chemical_registration.repository import (
    MoleculeRepository,
    SynthesisRouteRepository,
)
from cellar.domain.chemical_registration.synthesis_route import (
    ReactionReagent,
    ReactionStep,
    SynthesisRoute,
)
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.value_objects import ReactionConditions, ReactionOutcome

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreateSynthesisRouteCommand(Command):
    workspace_id: uuid.UUID
    target_molecule_id: uuid.UUID
    name: str
    description: str | None = None
    route_type: str = "linear"
    scale: str | None = None
    source: str = "manual"
    source_reference: str | None = None


@dataclass(frozen=True, kw_only=True)
class AddReactionStepCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID
    step_number: int
    branch_label: str | None = None
    name: str | None = None
    named_reaction: str | None = None
    reaction_smiles: str | None = None
    reaction_smarts: str | None = None
    product_molecule_id: uuid.UUID | None = None
    product_description: str | None = None
    conditions: dict[str, Any] | None = None
    reagents: list[dict[str, Any]] = field(default_factory=list)
    preceding_step_ids: list[uuid.UUID] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateSynthesisRouteCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID
    name: str | object = UNSET
    description: str | object | None = UNSET
    scale: str | object | None = UNSET


@dataclass(frozen=True, kw_only=True)
class DeleteSynthesisRouteCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveReactionStepCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID
    step_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RecordStepOutcomeCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID
    step_id: uuid.UUID
    yield_percent: float | None = None
    crude_yield_percent: float | None = None
    purity_percent: float | None = None
    purification_method: str | None = None
    batch_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ValidateSynthesisRouteCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SetPreferredRouteCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class DeprecateSynthesisRouteCommand(Command):
    workspace_id: uuid.UUID
    route_id: uuid.UUID
    reason: str | None = None


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetSynthesisRouteQuery(Query):
    workspace_id: uuid.UUID
    route_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListSynthesisRoutesByMoleculeQuery(Query):
    workspace_id: uuid.UUID
    target_molecule_id: uuid.UUID


# ---------------------------------------------------------------------------
# Use Cases
# ---------------------------------------------------------------------------


class CreateSynthesisRoute:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        molecule_repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._molecule_repo = molecule_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateSynthesisRouteCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            molecule = await self._molecule_repo.find_by_id_in_workspace(
                input.workspace_id, input.target_molecule_id
            )
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.target_molecule_id)))

            route = SynthesisRoute.create(
                workspace_id=input.workspace_id,
                target_molecule_id=input.target_molecule_id,
                name=input.name,
                description=input.description,
                route_type=RouteType(input.route_type),
                scale=RouteScale(input.scale) if input.scale else None,
                source=RouteSource(input.source),
                source_reference=input.source_reference,
                created_by=auth.user_id,
            )
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class GetSynthesisRoute:
    def __init__(self, uow: UnitOfWork, route_repo: SynthesisRouteRepository) -> None:
        self._uow = uow
        self._route_repo = route_repo

    async def __call__(
        self, input: GetSynthesisRouteQuery, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))
            return Success(route)


class ListSynthesisRoutesByMolecule:
    def __init__(self, uow: UnitOfWork, route_repo: SynthesisRouteRepository) -> None:
        self._uow = uow
        self._route_repo = route_repo

    async def __call__(
        self, input: ListSynthesisRoutesByMoleculeQuery, auth: AuthContext | None = None
    ) -> Result[list[SynthesisRoute], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            routes = await self._route_repo.find_by_target_molecule(
                input.workspace_id, input.target_molecule_id
            )
            return Success(routes)


class AddReactionStep:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddReactionStepCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))

            conditions = None
            if input.conditions:
                conditions = ReactionConditions(**input.conditions)

            reagents = [
                ReactionReagent(
                    role=ReagentRole(r["role"]),
                    molecule_id=uuid.UUID(r["molecule_id"]) if r.get("molecule_id") else None,
                    name=r.get("name", ""),
                    cas_number=r.get("cas_number"),
                    catalog_number=r.get("catalog_number"),
                    supplier=r.get("supplier"),
                    equivalents=r.get("equivalents"),
                )
                for r in input.reagents
            ]

            step = ReactionStep(
                route_id=route.id,
                step_number=input.step_number,
                branch_label=input.branch_label,
                name=input.name,
                named_reaction=input.named_reaction,
                reaction_smiles=input.reaction_smiles,
                reaction_smarts=input.reaction_smarts,
                product_molecule_id=input.product_molecule_id,
                product_description=input.product_description,
                conditions=conditions,
                reagents=reagents,
                preceding_step_ids=input.preceding_step_ids,
                notes=input.notes,
            )
            route.add_step(step)
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class RecordStepOutcome:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RecordStepOutcomeCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))

            outcome = ReactionOutcome(
                yield_percent=input.yield_percent,
                crude_yield_percent=input.crude_yield_percent,
                purity_percent=input.purity_percent,
                purification_method=input.purification_method,
            )
            route.record_step_outcome(input.step_id, outcome, batch_id=input.batch_id)
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class ValidateSynthesisRoute:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ValidateSynthesisRouteCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))
            route.validate_route()
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class SetPreferredRoute:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: SetPreferredRouteCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))

            # Demote current preferred (if any)
            current_preferred = await self._route_repo.find_preferred(
                route.workspace_id, route.target_molecule_id
            )
            previous_id = None
            if current_preferred is not None and current_preferred.id != route.id:
                previous_id = current_preferred.id
                current_preferred.deprecate(reason="Superseded by new preferred route")
                await self._route_repo.save(current_preferred)

            route.set_preferred(previous_preferred_id=previous_id)
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class DeprecateSynthesisRoute:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeprecateSynthesisRouteCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))
            route.deprecate(reason=input.reason)
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class UpdateSynthesisRoute:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: UpdateSynthesisRouteCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))

            if route.status != RouteStatus.DRAFT:
                return Failure(ValidationError("Can only update draft synthesis routes"))

            if input.name is not UNSET:
                route.name = input.name
            if input.description is not UNSET:
                route.description = input.description
            if input.scale is not UNSET:
                route.scale = RouteScale(input.scale) if input.scale else None

            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)


class DeleteSynthesisRoute:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteSynthesisRouteCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))

            if route.status != RouteStatus.DRAFT:
                return Failure(ValidationError("Can only delete draft synthesis routes"))

            await self._route_repo.delete(route.workspace_id, route.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveReactionStep:
    def __init__(
        self,
        uow: UnitOfWork,
        route_repo: SynthesisRouteRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._route_repo = route_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveReactionStepCommand, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            route = await self._route_repo.find_by_id_in_workspace(
                input.workspace_id, input.route_id
            )
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))

            if route.status != RouteStatus.DRAFT:
                return Failure(
                    ValidationError("Can only remove steps from draft synthesis routes")
                )

            route.remove_step(input.step_id)
            await self._route_repo.save(route)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(route)
