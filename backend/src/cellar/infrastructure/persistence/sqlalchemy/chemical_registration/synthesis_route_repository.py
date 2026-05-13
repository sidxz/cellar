"""SQLAlchemy repository for SynthesisRoute aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete, select

from cellar.domain.chemical_registration.enums import (
    ReagentRole,
    RouteScale,
    RouteSource,
    RouteStatus,
    RouteType,
)
from cellar.domain.chemical_registration.synthesis_route import (
    ReactionReagent,
    ReactionStep,
    SynthesisRoute,
)
from cellar.domain.shared.enums import AmountUnit
from cellar.domain.shared.value_objects import Amount, ReactionConditions, ReactionOutcome
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.synthesis_route_models import (
    ReactionStepModel,
    SynthesisRouteModel,
)


class SQLAlchemySynthesisRouteRepository(
    SQLAlchemyRepository[SynthesisRoute, SynthesisRouteModel]
):
    model_class = SynthesisRouteModel

    # ------------------------------------------------------------------
    # Custom query methods
    # ------------------------------------------------------------------

    async def find_by_target_molecule(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> list[SynthesisRoute]:
        stmt = (
            select(SynthesisRouteModel)
            .where(
                SynthesisRouteModel.workspace_id == workspace_id,
                SynthesisRouteModel.target_molecule_id == target_molecule_id,
            )
            .order_by(SynthesisRouteModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = sa_delete(SynthesisRouteModel).where(
            SynthesisRouteModel.workspace_id == workspace_id,
            SynthesisRouteModel.id == id,
        )
        await self._session.execute(stmt)

    async def find_preferred(
        self, workspace_id: uuid.UUID, target_molecule_id: uuid.UUID
    ) -> SynthesisRoute | None:
        stmt = select(SynthesisRouteModel).where(
            SynthesisRouteModel.workspace_id == workspace_id,
            SynthesisRouteModel.target_molecule_id == target_molecule_id,
            SynthesisRouteModel.status == RouteStatus.PREFERRED.value,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    # ------------------------------------------------------------------
    # Mapping: SA model <-> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: SynthesisRouteModel) -> SynthesisRoute:
        steps = [self._step_to_domain(sm) for sm in model.steps]

        estimated_cost = None
        if model.estimated_cost_value is not None and model.estimated_cost_unit is not None:
            estimated_cost = Amount(
                value=model.estimated_cost_value,
                unit=AmountUnit(model.estimated_cost_unit),
            )

        return SynthesisRoute(
            id=model.id,
            workspace_id=model.workspace_id,
            target_molecule_id=model.target_molecule_id,
            name=model.name,
            description=model.description,
            route_type=RouteType(model.route_type),
            status=RouteStatus(model.status),
            total_steps=model.total_steps,
            overall_yield=model.overall_yield,
            estimated_cost=estimated_cost,
            scale=RouteScale(model.scale) if model.scale else None,
            source=RouteSource(model.source),
            source_reference=model.source_reference,
            created_by=model.created_by,
            steps=steps,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: SynthesisRoute) -> SynthesisRouteModel:
        model = SynthesisRouteModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            target_molecule_id=aggregate.target_molecule_id,
            name=aggregate.name,
            description=aggregate.description,
            route_type=aggregate.route_type.value,
            status=aggregate.status.value,
            total_steps=aggregate.total_steps,
            overall_yield=aggregate.overall_yield,
            estimated_cost_value=aggregate.estimated_cost.value
            if aggregate.estimated_cost
            else None,
            estimated_cost_unit=aggregate.estimated_cost.unit.value
            if aggregate.estimated_cost
            else None,
            scale=aggregate.scale.value if aggregate.scale else None,
            source=aggregate.source.value,
            source_reference=aggregate.source_reference,
            created_by=aggregate.created_by,
            version=aggregate.version,
        )
        model.steps = [self._step_to_model(s) for s in aggregate.steps]
        return model

    def _update_model(self, model: SynthesisRouteModel, aggregate: SynthesisRoute) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.route_type = aggregate.route_type.value
        model.status = aggregate.status.value
        model.total_steps = aggregate.total_steps
        model.overall_yield = aggregate.overall_yield
        model.estimated_cost_value = (
            aggregate.estimated_cost.value if aggregate.estimated_cost else None
        )
        model.estimated_cost_unit = (
            aggregate.estimated_cost.unit.value if aggregate.estimated_cost else None
        )
        model.scale = aggregate.scale.value if aggregate.scale else None
        model.source = aggregate.source.value
        model.source_reference = aggregate.source_reference

        # Replace owned step collection
        model.steps = [self._step_to_model(s) for s in aggregate.steps]

    # ------------------------------------------------------------------
    # Step mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _step_to_domain(sm: ReactionStepModel) -> ReactionStep:
        conditions = None
        cond_fields = [
            sm.condition_solvent,
            sm.condition_temperature,
            sm.condition_pressure,
            sm.condition_catalyst,
            sm.condition_atmosphere,
            sm.condition_time,
            sm.condition_additional,
        ]
        if any(f is not None for f in cond_fields):
            conditions = ReactionConditions(
                solvent=sm.condition_solvent,
                temperature=sm.condition_temperature,
                pressure=sm.condition_pressure,
                catalyst=sm.condition_catalyst,
                atmosphere=sm.condition_atmosphere,
                time=sm.condition_time,
                additional_conditions=sm.condition_additional,
            )

        outcome = None
        outcome_fields = [
            sm.outcome_yield_percent,
            sm.outcome_crude_yield_percent,
            sm.outcome_purity_percent,
            sm.outcome_actual_scale_value,
            sm.outcome_purification_method,
        ]
        if any(f is not None for f in outcome_fields):
            actual_scale = None
            if (
                sm.outcome_actual_scale_value is not None
                and sm.outcome_actual_scale_unit is not None
            ):
                actual_scale = Amount(
                    value=sm.outcome_actual_scale_value,
                    unit=AmountUnit(sm.outcome_actual_scale_unit),
                )
            outcome = ReactionOutcome(
                yield_percent=sm.outcome_yield_percent,
                crude_yield_percent=sm.outcome_crude_yield_percent,
                purity_percent=sm.outcome_purity_percent,
                actual_scale=actual_scale,
                purification_method=sm.outcome_purification_method,
            )

        reagents = [
            ReactionReagent(
                role=ReagentRole(r["role"]),
                molecule_id=uuid.UUID(r["molecule_id"]) if r.get("molecule_id") else None,
                name=r.get("name", ""),
                cas_number=r.get("cas_number"),
                catalog_number=r.get("catalog_number"),
                supplier=r.get("supplier"),
                amount=Amount(value=r["amount"]["value"], unit=AmountUnit(r["amount"]["unit"]))
                if r.get("amount")
                else None,
                equivalents=r.get("equivalents"),
            )
            for r in (sm.reagents or [])
        ]

        preceding = [uuid.UUID(pid) for pid in (sm.preceding_step_ids or [])]

        return ReactionStep(
            id=sm.id,
            route_id=sm.route_id,
            step_number=sm.step_number,
            branch_label=sm.branch_label,
            name=sm.name,
            named_reaction=sm.named_reaction,
            reaction_smiles=sm.reaction_smiles,
            reaction_smarts=sm.reaction_smarts,
            product_molecule_id=sm.product_molecule_id,
            product_description=sm.product_description,
            conditions=conditions,
            outcome=outcome,
            reagents=reagents,
            preceding_step_ids=preceding,
            eln_entry_id=sm.eln_entry_id,
            batch_id=sm.batch_id,
            notes=sm.notes,
            created_at=sm.created_at,
            updated_at=sm.updated_at,
        )

    @staticmethod
    def _step_to_model(step: ReactionStep) -> ReactionStepModel:
        reagent_dicts = [
            {
                "role": r.role.value,
                "molecule_id": str(r.molecule_id) if r.molecule_id else None,
                "name": r.name,
                "cas_number": r.cas_number,
                "catalog_number": r.catalog_number,
                "supplier": r.supplier,
                "amount": {"value": r.amount.value, "unit": r.amount.unit.value}
                if r.amount
                else None,
                "equivalents": r.equivalents,
            }
            for r in step.reagents
        ]

        return ReactionStepModel(
            id=step.id,
            route_id=step.route_id,
            step_number=step.step_number,
            branch_label=step.branch_label,
            name=step.name,
            named_reaction=step.named_reaction,
            reaction_smiles=step.reaction_smiles,
            reaction_smarts=step.reaction_smarts,
            product_molecule_id=step.product_molecule_id,
            product_description=step.product_description,
            condition_solvent=step.conditions.solvent if step.conditions else None,
            condition_temperature=step.conditions.temperature if step.conditions else None,
            condition_pressure=step.conditions.pressure if step.conditions else None,
            condition_catalyst=step.conditions.catalyst if step.conditions else None,
            condition_atmosphere=step.conditions.atmosphere if step.conditions else None,
            condition_time=step.conditions.time if step.conditions else None,
            condition_additional=step.conditions.additional_conditions
            if step.conditions
            else None,
            outcome_yield_percent=step.outcome.yield_percent if step.outcome else None,
            outcome_crude_yield_percent=step.outcome.crude_yield_percent if step.outcome else None,
            outcome_purity_percent=step.outcome.purity_percent if step.outcome else None,
            outcome_actual_scale_value=step.outcome.actual_scale.value
            if step.outcome and step.outcome.actual_scale
            else None,
            outcome_actual_scale_unit=step.outcome.actual_scale.unit.value
            if step.outcome and step.outcome.actual_scale
            else None,
            outcome_purification_method=step.outcome.purification_method if step.outcome else None,
            reagents=reagent_dicts,
            preceding_step_ids=[str(pid) for pid in step.preceding_step_ids],
            eln_entry_id=step.eln_entry_id,
            batch_id=step.batch_id,
            notes=step.notes,
        )
