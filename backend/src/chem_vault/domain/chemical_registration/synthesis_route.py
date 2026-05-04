"""SynthesisRoute aggregate — ordered plan for producing a target molecule.

Contains ReactionStep owned entities and ReactionReagent value objects.
Includes DAG validation for step ordering and convergent route support.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.chemical_registration.enums import (
    ReagentRole,
    RouteScale,
    RouteSource,
    RouteStatus,
    RouteType,
)
from chem_vault.domain.chemical_registration.events import (
    ReactionStepOutcomeRecorded,
    SynthesisRouteCreated,
    SynthesisRouteDeprecated,
    SynthesisRoutePreferred,
    SynthesisRouteValidated,
)
from chem_vault.domain.shared.entity import AggregateRoot, Entity
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Amount, ReactionConditions, ReactionOutcome


# ---------------------------------------------------------------------------
# ReactionReagent — value object (frozen dataclass)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ReactionReagent:
    """A material used in a reaction step."""

    role: ReagentRole
    molecule_id: uuid.UUID | None = None
    name: str = ""
    cas_number: str | None = None
    catalog_number: str | None = None
    supplier: str | None = None
    amount: Amount | None = None
    equivalents: float | None = None


# ---------------------------------------------------------------------------
# ReactionStep — owned entity
# ---------------------------------------------------------------------------


class ReactionStep(Entity):
    """A single chemical transformation within a synthesis route."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        route_id: uuid.UUID,
        step_number: int,
        branch_label: str | None = None,
        name: str | None = None,
        named_reaction: str | None = None,
        reaction_smiles: str | None = None,
        reaction_smarts: str | None = None,
        product_molecule_id: uuid.UUID | None = None,
        product_description: str | None = None,
        conditions: ReactionConditions | None = None,
        outcome: ReactionOutcome | None = None,
        reagents: list[ReactionReagent] | None = None,
        preceding_step_ids: list[uuid.UUID] | None = None,
        eln_entry_id: uuid.UUID | None = None,
        batch_id: uuid.UUID | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)
        self.route_id = route_id
        self.step_number = step_number
        self.branch_label = branch_label
        self.name = name
        self.named_reaction = named_reaction
        self.reaction_smiles = reaction_smiles
        self.reaction_smarts = reaction_smarts
        self.product_molecule_id = product_molecule_id
        self.product_description = product_description
        self.conditions = conditions
        self.outcome = outcome
        self.reagents: list[ReactionReagent] = list(reagents or [])
        self.preceding_step_ids: list[uuid.UUID] = list(preceding_step_ids or [])
        self.eln_entry_id = eln_entry_id
        self.batch_id = batch_id
        self.notes = notes

    def _set_outcome(self, outcome: ReactionOutcome, batch_id: uuid.UUID | None = None) -> None:
        """Record the outcome for this step."""
        self.outcome = outcome
        self.batch_id = batch_id
        self.updated_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# SynthesisRoute — aggregate root
# ---------------------------------------------------------------------------


_VALID_TRANSITIONS: dict[RouteStatus, set[RouteStatus]] = {
    RouteStatus.DRAFT: {RouteStatus.VALIDATED},
    RouteStatus.VALIDATED: {RouteStatus.PREFERRED, RouteStatus.DEPRECATED},
    RouteStatus.PREFERRED: {RouteStatus.DEPRECATED},
    RouteStatus.DEPRECATED: {RouteStatus.VALIDATED},
}


class SynthesisRoute(AggregateRoot):
    """An ordered plan for producing a target molecule from starting materials."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
        name: str,
        description: str | None = None,
        route_type: RouteType = RouteType.LINEAR,
        status: RouteStatus = RouteStatus.DRAFT,
        total_steps: int = 0,
        overall_yield: float | None = None,
        estimated_cost: Amount | None = None,
        scale: RouteScale | None = None,
        source: RouteSource = RouteSource.MANUAL,
        source_reference: str | None = None,
        created_by: uuid.UUID,
        steps: list[ReactionStep] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.target_molecule_id = target_molecule_id
        self.name = name
        self.description = description
        self.route_type = route_type
        self.status = status
        self.total_steps = total_steps
        self.overall_yield = overall_yield
        self.estimated_cost = estimated_cost
        self.scale = scale
        self.source = source
        self.source_reference = source_reference
        self.created_by = created_by
        self._steps: list[ReactionStep] = list(steps or [])

    # -- Properties --

    @property
    def steps(self) -> list[ReactionStep]:
        return list(self._steps)

    @property
    def is_draft(self) -> bool:
        return self.status == RouteStatus.DRAFT

    # -- Factory --

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
        name: str,
        description: str | None = None,
        route_type: RouteType = RouteType.LINEAR,
        scale: RouteScale | None = None,
        source: RouteSource = RouteSource.MANUAL,
        source_reference: str | None = None,
        created_by: uuid.UUID,
    ) -> SynthesisRoute:
        if not name.strip():
            raise ValidationError("Route name cannot be empty")

        route = cls(
            workspace_id=workspace_id,
            target_molecule_id=target_molecule_id,
            name=name,
            description=description,
            route_type=route_type,
            scale=scale,
            source=source,
            source_reference=source_reference,
            created_by=created_by,
        )
        route.register_event(
            SynthesisRouteCreated(
                aggregate_id=route.id,
                aggregate_type="SynthesisRoute",
                workspace_id=workspace_id,
                target_molecule_id=target_molecule_id,
                route_type=route_type.value,
                source=source.value,
            )
        )
        return route

    # -- Step management --

    def add_step(self, step: ReactionStep) -> None:
        if not self.is_draft:
            raise ValidationError("Steps can only be added to draft routes")
        self._steps.append(step)
        self.total_steps = len(self._steps)
        self.updated_at = datetime.now(UTC)

    def remove_step(self, step_id: uuid.UUID) -> None:
        if not self.is_draft:
            raise ValidationError("Steps can only be removed from draft routes")
        self._steps = [s for s in self._steps if s.id != step_id]
        self.total_steps = len(self._steps)
        self.updated_at = datetime.now(UTC)

    def record_step_outcome(
        self, step_id: uuid.UUID, outcome: ReactionOutcome, batch_id: uuid.UUID | None = None
    ) -> None:
        step = next((s for s in self._steps if s.id == step_id), None)
        if step is None:
            raise ValidationError(f"Step {step_id} not found in route")
        step._set_outcome(outcome, batch_id)
        self._recompute_overall_yield()
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ReactionStepOutcomeRecorded(
                aggregate_id=self.id,
                aggregate_type="SynthesisRoute",
                workspace_id=self.workspace_id,
                step_id=step_id,
                yield_percent=outcome.yield_percent,
                batch_id=batch_id,
            )
        )

    # -- State transitions --

    def validate_route(self) -> None:
        self._assert_transition(RouteStatus.VALIDATED)
        self._validate_dag()
        if not self._steps:
            raise ValidationError("Cannot validate a route with no steps")
        self.status = RouteStatus.VALIDATED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRouteValidated(
                aggregate_id=self.id,
                aggregate_type="SynthesisRoute",
                workspace_id=self.workspace_id,
                total_steps=self.total_steps,
                overall_yield=self.overall_yield,
            )
        )

    def set_preferred(self, previous_preferred_id: uuid.UUID | None = None) -> None:
        self._assert_transition(RouteStatus.PREFERRED)
        self.status = RouteStatus.PREFERRED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRoutePreferred(
                aggregate_id=self.id,
                aggregate_type="SynthesisRoute",
                workspace_id=self.workspace_id,
                target_molecule_id=self.target_molecule_id,
                previous_preferred_id=previous_preferred_id,
            )
        )

    def deprecate(self, reason: str | None = None) -> None:
        self._assert_transition(RouteStatus.DEPRECATED)
        self.status = RouteStatus.DEPRECATED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SynthesisRouteDeprecated(
                aggregate_id=self.id,
                aggregate_type="SynthesisRoute",
                workspace_id=self.workspace_id,
                reason=reason,
            )
        )

    def revalidate(self) -> None:
        """Deprecated → Validated (re-activation)."""
        self._assert_transition(RouteStatus.VALIDATED)
        self.status = RouteStatus.VALIDATED
        self.updated_at = datetime.now(UTC)

    # -- DAG validation --

    def _validate_dag(self) -> None:
        """Verify the step graph is a valid DAG with no cycles."""
        step_ids = {s.id for s in self._steps}

        for step in self._steps:
            for pred_id in step.preceding_step_ids:
                if pred_id not in step_ids:
                    raise ValidationError(
                        f"Step {step.id} references unknown preceding step {pred_id}"
                    )

        # Topological sort to detect cycles (Kahn's algorithm)
        in_degree: dict[uuid.UUID, int] = {s.id: 0 for s in self._steps}
        adjacency: dict[uuid.UUID, list[uuid.UUID]] = {s.id: [] for s in self._steps}

        for step in self._steps:
            for pred_id in step.preceding_step_ids:
                adjacency[pred_id].append(step.id)
                in_degree[step.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited = 0

        while queue:
            current = queue.pop(0)
            visited += 1
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(self._steps):
            raise ValidationError("Step graph contains a cycle")

        # Convergent route check
        if self.route_type == RouteType.LINEAR:
            for step in self._steps:
                if len(step.preceding_step_ids) > 1:
                    raise ValidationError(
                        "Linear routes cannot have steps with multiple predecessors"
                    )

    # -- Internal helpers --

    def _assert_transition(self, target: RouteStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition from {self.status.value} to {target.value}"
            )

    def _recompute_overall_yield(self) -> None:
        """Recompute overall_yield as product of step yields along longest linear path."""
        yields = [
            s.outcome.yield_percent
            for s in self._steps
            if s.outcome and s.outcome.yield_percent is not None
        ]
        if yields:
            result = 1.0
            for y in yields:
                result *= y / 100.0
            self.overall_yield = round(result * 100.0, 2)
        else:
            self.overall_yield = None
