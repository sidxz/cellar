"""SQLAlchemy repository for SynthesisRequest aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from chem_vault.domain.inventory.enums import (
    FeasibilityStatus,
    RequestPriority,
    SynthesisRequestStatus,
)
from chem_vault.domain.inventory.synthesis_request import SynthesisRequest
from chem_vault.domain.shared.enums import AmountUnit, AssignmentType
from chem_vault.domain.shared.value_objects import Amount, ChemicalStructure, SynthesisAssignment
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_models import (
    SynthesisRequestModel,
)


class SQLAlchemySynthesisRequestRepository(
    SQLAlchemyRepository[SynthesisRequest, SynthesisRequestModel]
):
    model_class = SynthesisRequestModel

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[SynthesisRequest]:
        stmt = select(SynthesisRequestModel).where(
            SynthesisRequestModel.workspace_id == workspace_id
        )
        if status:
            stmt = stmt.where(SynthesisRequestModel.status == status)
        stmt = stmt.order_by(SynthesisRequestModel.created_at.desc())
        result = await self._session.execute(stmt)
        requests = []
        for model in result.scalars().all():
            domain = self._to_domain(model)
            self._uow.track(domain)
            requests.append(domain)
        return requests

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[SynthesisRequest]:
        stmt = (
            select(SynthesisRequestModel)
            .where(
                SynthesisRequestModel.workspace_id == workspace_id,
                SynthesisRequestModel.molecule_id == molecule_id,
            )
            .order_by(SynthesisRequestModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    def _to_domain(self, model: SynthesisRequestModel) -> SynthesisRequest:
        # Reconstruct target_structure VO
        target_structure: ChemicalStructure | None = None
        if model.target_smiles is not None:
            target_structure = ChemicalStructure(
                smiles=model.target_smiles,
                inchi=model.target_inchi,
                inchi_key=model.target_inchi_key,
            )

        # Reconstruct assignment VO
        assignment: SynthesisAssignment | None = None
        if model.assignment_type is not None:
            assignment = SynthesisAssignment(
                assignment_type=AssignmentType(model.assignment_type),
                assigned_to=model.assigned_to,
                assigned_org_id=model.assigned_org_id,
            )

        # Reconstruct cost VOs
        estimated_cost: Amount | None = None
        if model.estimated_cost_value is not None:
            estimated_cost = Amount(
                value=model.estimated_cost_value,
                unit=AmountUnit(model.estimated_cost_unit),  # type: ignore[arg-type]
            )

        actual_cost: Amount | None = None
        if model.actual_cost_value is not None:
            actual_cost = Amount(
                value=model.actual_cost_value,
                unit=AmountUnit(model.actual_cost_unit),  # type: ignore[arg-type]
            )

        return SynthesisRequest(
            id=model.id,
            workspace_id=model.workspace_id,
            requester_id=model.requester_id,
            molecule_id=model.molecule_id,
            target_structure=target_structure,
            requested_amount=Amount(
                value=model.requested_amount_value,
                unit=AmountUnit(model.requested_amount_unit),
            ),
            target_purity=model.target_purity,
            purpose=model.purpose,
            priority=RequestPriority(model.priority),
            status=SynthesisRequestStatus(model.status),
            project_id=model.project_id,
            parent_request_id=model.parent_request_id,
            bulk_request_id=model.bulk_request_id,
            approved_by=model.approved_by,
            approved_at=model.approved_at,
            rejection_reason=model.rejection_reason,
            assignment=assignment,
            proposed_route_id=model.proposed_route_id,
            feasibility_notes=model.feasibility_notes,
            feasibility_status=FeasibilityStatus(model.feasibility_status) if model.feasibility_status else None,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            estimated_completion_date=model.estimated_completion_date,
            actual_completion_date=model.actual_completion_date,
            fulfilled_batch_id=model.fulfilled_batch_id,
            failure_reason=model.failure_reason,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: SynthesisRequest) -> SynthesisRequestModel:
        return SynthesisRequestModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            requester_id=aggregate.requester_id,
            molecule_id=aggregate.molecule_id,
            target_smiles=aggregate.target_structure.smiles if aggregate.target_structure else None,
            target_inchi=aggregate.target_structure.inchi if aggregate.target_structure else None,
            target_inchi_key=aggregate.target_structure.inchi_key if aggregate.target_structure else None,
            requested_amount_value=aggregate.requested_amount.value,
            requested_amount_unit=aggregate.requested_amount.unit.value,
            target_purity=aggregate.target_purity,
            purpose=aggregate.purpose,
            priority=aggregate.priority.value,
            status=aggregate.status.value,
            project_id=aggregate.project_id,
            parent_request_id=aggregate.parent_request_id,
            bulk_request_id=aggregate.bulk_request_id,
            approved_by=aggregate.approved_by,
            approved_at=aggregate.approved_at,
            rejection_reason=aggregate.rejection_reason,
            assignment_type=aggregate.assignment.assignment_type.value if aggregate.assignment else None,
            assigned_to=aggregate.assignment.assigned_to if aggregate.assignment else None,
            assigned_org_id=aggregate.assignment.assigned_org_id if aggregate.assignment else None,
            proposed_route_id=aggregate.proposed_route_id,
            feasibility_notes=aggregate.feasibility_notes,
            feasibility_status=aggregate.feasibility_status.value if aggregate.feasibility_status else None,
            estimated_cost_value=aggregate.estimated_cost.value if aggregate.estimated_cost else None,
            estimated_cost_unit=aggregate.estimated_cost.unit.value if aggregate.estimated_cost else None,
            actual_cost_value=aggregate.actual_cost.value if aggregate.actual_cost else None,
            actual_cost_unit=aggregate.actual_cost.unit.value if aggregate.actual_cost else None,
            estimated_completion_date=aggregate.estimated_completion_date,
            actual_completion_date=aggregate.actual_completion_date,
            fulfilled_batch_id=aggregate.fulfilled_batch_id,
            failure_reason=aggregate.failure_reason,
            version=aggregate.version,
        )

    def _update_model(self, model: SynthesisRequestModel, aggregate: SynthesisRequest) -> None:
        model.target_smiles = aggregate.target_structure.smiles if aggregate.target_structure else None
        model.target_inchi = aggregate.target_structure.inchi if aggregate.target_structure else None
        model.target_inchi_key = aggregate.target_structure.inchi_key if aggregate.target_structure else None
        model.requested_amount_value = aggregate.requested_amount.value
        model.requested_amount_unit = aggregate.requested_amount.unit.value
        model.target_purity = aggregate.target_purity
        model.purpose = aggregate.purpose
        model.priority = aggregate.priority.value
        model.status = aggregate.status.value
        model.project_id = aggregate.project_id
        model.parent_request_id = aggregate.parent_request_id
        model.bulk_request_id = aggregate.bulk_request_id
        model.approved_by = aggregate.approved_by
        model.approved_at = aggregate.approved_at
        model.rejection_reason = aggregate.rejection_reason
        model.assignment_type = aggregate.assignment.assignment_type.value if aggregate.assignment else None
        model.assigned_to = aggregate.assignment.assigned_to if aggregate.assignment else None
        model.assigned_org_id = aggregate.assignment.assigned_org_id if aggregate.assignment else None
        model.proposed_route_id = aggregate.proposed_route_id
        model.feasibility_notes = aggregate.feasibility_notes
        model.feasibility_status = aggregate.feasibility_status.value if aggregate.feasibility_status else None
        model.estimated_cost_value = aggregate.estimated_cost.value if aggregate.estimated_cost else None
        model.estimated_cost_unit = aggregate.estimated_cost.unit.value if aggregate.estimated_cost else None
        model.actual_cost_value = aggregate.actual_cost.value if aggregate.actual_cost else None
        model.actual_cost_unit = aggregate.actual_cost.unit.value if aggregate.actual_cost else None
        model.estimated_completion_date = aggregate.estimated_completion_date
        model.actual_completion_date = aggregate.actual_completion_date
        model.fulfilled_batch_id = aggregate.fulfilled_batch_id
        model.failure_reason = aggregate.failure_reason
