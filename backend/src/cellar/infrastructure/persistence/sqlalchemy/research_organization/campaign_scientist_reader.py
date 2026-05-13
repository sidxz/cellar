"""SQLAlchemy implementation of CampaignScientistReader."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.application.research_organization.campaign_scientist_reader import (
    CampaignScientistReader,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
    ReadoutDefinitionModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyCampaignScientistReader(CampaignScientistReader):
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def find_scientist_by_run_ids(
        self,
        workspace_id: uuid.UUID,
        run_ids: set[uuid.UUID],
    ) -> dict[uuid.UUID, str]:
        if not run_ids:
            return {}
        stmt = (
            select(
                ReadoutDataModel.run_id,
                func.min(ReadoutDataModel.value_text).label("scientist"),
            )
            .join(
                ReadoutDefinitionModel,
                ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.run_id.in_(run_ids),
                func.lower(ReadoutDefinitionModel.name) == "scientist",
                ReadoutDataModel.value_text.is_not(None),
                func.length(ReadoutDataModel.value_text) > 0,
            )
            .group_by(ReadoutDataModel.run_id)
        )
        rows = (await self._uow.session.execute(stmt)).all()
        return {row.run_id: row.scientist for row in rows if row.scientist}
