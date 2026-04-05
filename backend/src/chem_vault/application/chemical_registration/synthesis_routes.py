"""Synthesis route use cases — CRUD + state transitions + step management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor, require_same_workspace
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.enums import (
    ReagentRole,
    RouteScale,
    RouteSource,
    RouteStatus,
    RouteType,
)
from chem_vault.domain.chemical_registration.repository import (
    MoleculeRepository,
    SynthesisRouteRepository,
)
from chem_vault.domain.chemical_registration.synthesis_route import (
    ReactionReagent,
    ReactionStep,
    SynthesisRoute,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.value_objects import ReactionConditions, ReactionOutcome


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
    conditions: dict | None = None
    reagents: list[dict] = field(default_factory=list)
    preceding_step_ids: list[uuid.UUID] = field(default_factory=list)
    notes: str | None = None


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


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetSynthesisRouteQuery(Query):
    route_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class ListSynthesisRoutesByMoleculeQuery(Query):
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
        require_editor(auth)
        async with self._uow:
            molecule = await self._molecule_repo.find_by_id(input.target_molecule_id)
            if molecule is None:
                return Failure(NotFoundError("Molecule", str(input.target_molecule_id)))
            require_same_workspace(auth, molecule.workspace_id)

            route = SynthesisRoute.create(
                workspace_id=input.workspace_id,
                target_molecule_id=input.target_molecule_id,
                name=input.name,
                description=input.description,
                route_type=RouteType(input.route_type),
                scale=RouteScale(input.scale) if input.scale else None,
                source=RouteSource(input.source),
                source_reference=input.source_reference,
                created_by=auth.user_id if auth else uuid.uuid4(),
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
        async with self._uow:
            route = await self._route_repo.find_by_id(input.route_id)
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))
            require_same_workspace(auth, route.workspace_id)
            return Success(route)


class ListSynthesisRoutesByMolecule:
    def __init__(self, uow: UnitOfWork, route_repo: SynthesisRouteRepository) -> None:
        self._uow = uow
        self._route_repo = route_repo

    async def __call__(
        self, input: ListSynthesisRoutesByMoleculeQuery, auth: AuthContext | None = None
    ) -> Result[list[SynthesisRoute], DomainError]:
        async with self._uow:
            routes = await self._route_repo.find_by_target_molecule(input.target_molecule_id)
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
        async with self._uow:
            route = await self._route_repo.find_by_id(input.route_id)
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))
            require_same_workspace(auth, route.workspace_id)

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
        async with self._uow:
            route = await self._route_repo.find_by_id(input.route_id)
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(input.route_id)))
            require_same_workspace(auth, route.workspace_id)

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
        self, route_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        async with self._uow:
            route = await self._route_repo.find_by_id(route_id)
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(route_id)))
            require_same_workspace(auth, route.workspace_id)
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
        self, route_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        async with self._uow:
            route = await self._route_repo.find_by_id(route_id)
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(route_id)))
            require_same_workspace(auth, route.workspace_id)

            # Demote current preferred (if any)
            current_preferred = await self._route_repo.find_preferred(route.target_molecule_id)
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
        self, route_id: uuid.UUID, reason: str | None = None, auth: AuthContext | None = None
    ) -> Result[SynthesisRoute, DomainError]:
        require_editor(auth)
        async with self._uow:
            route = await self._route_repo.find_by_id(route_id)
            if route is None:
                return Failure(NotFoundError("SynthesisRoute", str(route_id)))
            require_same_workspace(auth, route.workspace_id)
            route.deprecate(reason=reason)
            await self._route_repo.save(route)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)
            return Success(route)
