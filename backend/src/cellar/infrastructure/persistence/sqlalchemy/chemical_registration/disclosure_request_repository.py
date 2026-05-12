"""SQLAlchemy repository for DisclosureRequest aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.enums import (
    DisclosureResolutionType,
    DisclosureStatus,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_models import (
    DisclosureRequestModel,
)


class SQLAlchemyDisclosureRequestRepository(
    SQLAlchemyRepository[DisclosureRequest, DisclosureRequestModel]
):
    model_class = DisclosureRequestModel

    # ------------------------------------------------------------------
    # Mapping: SA model -> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: DisclosureRequestModel) -> DisclosureRequest:
        return DisclosureRequest(
            id=model.id,
            workspace_id=model.workspace_id,
            bulk_disclosure_id=model.bulk_disclosure_id,
            molecule_id=model.molecule_id,
            disclosed_smiles=model.disclosed_smiles,
            canonical_smiles=model.canonical_smiles,
            inchi_key=model.inchi_key,
            status=DisclosureStatus(model.status),
            resolution_type=(
                DisclosureResolutionType(model.resolution_type) if model.resolution_type else None
            ),
            resolved_to_molecule_id=model.resolved_to_molecule_id,
            matched_molecule_id=model.matched_molecule_id,
            scientist_name=model.scientist_name,
            disclosing_org_id=model.disclosing_org_id,
            requested_by=model.requested_by,
            requested_at=model.requested_at,
            resolved_at=model.resolved_at,
            conflict_reason=model.conflict_reason,
            notes=model.notes,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (INSERT)
    # ------------------------------------------------------------------

    def _to_model(self, aggregate: DisclosureRequest) -> DisclosureRequestModel:
        return DisclosureRequestModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            bulk_disclosure_id=aggregate.bulk_disclosure_id,
            molecule_id=aggregate.molecule_id,
            disclosed_smiles=aggregate.disclosed_smiles,
            canonical_smiles=aggregate.canonical_smiles,
            inchi_key=aggregate.inchi_key,
            status=aggregate.status.value,
            resolution_type=(
                aggregate.resolution_type.value if aggregate.resolution_type else None
            ),
            resolved_to_molecule_id=aggregate.resolved_to_molecule_id,
            matched_molecule_id=aggregate.matched_molecule_id,
            scientist_name=aggregate.scientist_name,
            disclosing_org_id=aggregate.disclosing_org_id,
            requested_by=aggregate.requested_by,
            requested_at=aggregate.requested_at,
            resolved_at=aggregate.resolved_at,
            conflict_reason=aggregate.conflict_reason,
            notes=aggregate.notes,
            version=aggregate.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (UPDATE)
    # ------------------------------------------------------------------

    def _update_model(self, model: DisclosureRequestModel, aggregate: DisclosureRequest) -> None:
        model.status = aggregate.status.value
        model.canonical_smiles = aggregate.canonical_smiles
        model.inchi_key = aggregate.inchi_key
        model.resolution_type = (
            aggregate.resolution_type.value if aggregate.resolution_type else None
        )
        model.resolved_to_molecule_id = aggregate.resolved_to_molecule_id
        model.matched_molecule_id = aggregate.matched_molecule_id
        model.scientist_name = aggregate.scientist_name
        model.resolved_at = aggregate.resolved_at
        model.conflict_reason = aggregate.conflict_reason
        model.notes = aggregate.notes

    # ------------------------------------------------------------------
    # Additional query methods
    # ------------------------------------------------------------------

    async def find_by_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[DisclosureRequest]:
        stmt = select(DisclosureRequestModel).where(
            DisclosureRequestModel.workspace_id == workspace_id,
            DisclosureRequestModel.molecule_id == molecule_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_bulk_disclosure(
        self, workspace_id: uuid.UUID, bulk_disclosure_id: uuid.UUID
    ) -> list[DisclosureRequest]:
        stmt = select(DisclosureRequestModel).where(
            DisclosureRequestModel.workspace_id == workspace_id,
            DisclosureRequestModel.bulk_disclosure_id == bulk_disclosure_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, status: str | None = None
    ) -> list[DisclosureRequest]:
        stmt = select(DisclosureRequestModel).where(
            DisclosureRequestModel.workspace_id == workspace_id
        )
        if status:
            stmt = stmt.where(DisclosureRequestModel.status == status)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]
