"""SQLAlchemy repository for ProtocolForm aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from chem_vault.domain.workspace_config.protocol_form import (
    ProtocolForm,
    ProtocolFormCondition,
    ProtocolFormOntologyDefault,
    ProtocolFormReadout,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    ProtocolFormModel,
)


class SQLAlchemyProtocolFormRepository(
    SQLAlchemyRepository[ProtocolForm, ProtocolFormModel]
):
    model_class = ProtocolFormModel

    # ------------------------------------------------------------------
    # JSONB <-> domain VO helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _readouts_to_domain(raw: list | None) -> list[ProtocolFormReadout]:
        if not raw:
            return []
        return [
            ProtocolFormReadout(
                name=r["name"],
                data_type=r["data_type"],
                unit=r.get("unit"),
                aggregation=r.get("aggregation", "none"),
                normalization=r.get("normalization", "none"),
                is_calculated=r.get("is_calculated", False),
                calculation_formula=r.get("calculation_formula"),
                pick_list_values=r.get("pick_list_values"),
                dose_response_config=r.get("dose_response_config"),
            )
            for r in raw
        ]

    @staticmethod
    def _conditions_to_domain(raw: list | None) -> list[ProtocolFormCondition]:
        if not raw:
            return []
        return [
            ProtocolFormCondition(
                name=c["name"],
                data_type=c["data_type"],
                unit=c.get("unit"),
                pick_list_values=c.get("pick_list_values"),
            )
            for c in raw
        ]

    @staticmethod
    def _ontology_defaults_to_domain(raw: list | None) -> list[ProtocolFormOntologyDefault]:
        if not raw:
            return []
        return [
            ProtocolFormOntologyDefault(
                slot_name=o["slot_name"],
                terms=o.get("terms", []),
            )
            for o in raw
        ]

    @staticmethod
    def _readouts_to_json(readouts: list[ProtocolFormReadout]) -> list[dict]:
        from dataclasses import asdict
        return [asdict(r) for r in readouts]

    @staticmethod
    def _conditions_to_json(conditions: list[ProtocolFormCondition]) -> list[dict] | None:
        if not conditions:
            return None
        from dataclasses import asdict
        return [asdict(c) for c in conditions]

    @staticmethod
    def _ontology_defaults_to_json(defaults: list[ProtocolFormOntologyDefault]) -> list[dict] | None:
        if not defaults:
            return None
        from dataclasses import asdict
        return [asdict(d) for d in defaults]

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: ProtocolFormModel) -> ProtocolForm:
        return ProtocolForm(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            protocol_type=model.protocol_type,
            is_default=model.is_default,
            readout_templates=self._readouts_to_domain(model.readout_templates),
            condition_templates=self._conditions_to_domain(model.condition_templates),
            ontology_defaults=self._ontology_defaults_to_domain(model.ontology_defaults),
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: ProtocolForm) -> ProtocolFormModel:
        return ProtocolFormModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            description=aggregate.description,
            protocol_type=aggregate.protocol_type,
            is_default=aggregate.is_default,
            readout_templates=self._readouts_to_json(aggregate.readout_templates),
            condition_templates=self._conditions_to_json(aggregate.condition_templates),
            ontology_defaults=self._ontology_defaults_to_json(aggregate.ontology_defaults),
            version=aggregate.version,
        )

    def _update_model(self, model: ProtocolFormModel, aggregate: ProtocolForm) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.protocol_type = aggregate.protocol_type
        model.is_default = aggregate.is_default
        model.readout_templates = self._readouts_to_json(aggregate.readout_templates)
        model.condition_templates = self._conditions_to_json(aggregate.condition_templates)
        model.ontology_defaults = self._ontology_defaults_to_json(aggregate.ontology_defaults)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
    ) -> list[ProtocolForm]:
        stmt = (
            select(ProtocolFormModel)
            .where(ProtocolFormModel.workspace_id == workspace_id)
            .order_by(ProtocolFormModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(ProtocolFormModel).where(
            ProtocolFormModel.workspace_id == workspace_id,
            ProtocolFormModel.id == id,
        )
        await self._session.execute(stmt)
