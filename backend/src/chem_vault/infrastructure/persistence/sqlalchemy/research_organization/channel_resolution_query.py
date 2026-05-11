"""SQL implementation of ChannelResolutionQuery.

Joins dose_response_curves (or readout_data) -> runs -> protocols and
yields ``ResolvedCandidate`` rows for the resolver to apply selection
rules over. Workspace scoping is enforced on the leaf table (curves /
readouts) — runs and protocols are reached only via FK so are
transitively scoped.

The unit for dose-response curves comes from ``Protocol.dose_unit``
(curves don't denormalize their unit); the unit for readouts comes
from ``ReadoutDefinition.unit``.

Deep correctness of the join is exercised indirectly by the
close-campaign integration tests in Phase 5; this query is shipped with
an empty-result smoke only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.research_organization.channel_resolution import (
    ResolvedCandidate,
)
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    ValueQualifier,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
)


class SQLAlchemyChannelResolutionQuery:
    """Production implementation of ChannelResolutionQuery."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def fetch_candidates(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
    ) -> list[ResolvedCandidate]:
        if channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
            return await self._fetch_curve_candidates(
                workspace_id, channel, molecule_id
            )
        return await self._fetch_readout_candidates(
            workspace_id, channel, molecule_id
        )

    async def _fetch_curve_candidates(
        self,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
    ) -> list[ResolvedCandidate]:
        stmt = (
            select(
                DoseResponseCurveModel.id,
                DoseResponseCurveModel.fitted_value,
                DoseResponseCurveModel.run_id,
                RunModel.run_date,
                RunModel.status,
                RunModel.qc_metrics,
                ProtocolModel.name,
                ProtocolModel.protocol_version,
                ProtocolModel.dose_unit,
            )
            .join(RunModel, DoseResponseCurveModel.run_id == RunModel.id)
            .join(
                ProtocolModel,
                DoseResponseCurveModel.protocol_id == ProtocolModel.id,
            )
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.molecule_id == molecule_id,
                DoseResponseCurveModel.protocol_id == channel.protocol_id,
            )
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ResolvedCandidate(
                value=row.fitted_value,
                qualifier=ValueQualifier.EQ,
                unit=row.dose_unit or "",
                run_id=row.run_id,
                run_date=row.run_date,
                run_approved=row.status == "approved",
                z_prime=(row.qc_metrics or {}).get("z_prime"),
                protocol_name=row.name,
                protocol_version=row.protocol_version,
                curve_id=row.id,
                readout_id=None,
            )
            for row in rows
        ]

    async def _fetch_readout_candidates(
        self,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
    ) -> list[ResolvedCandidate]:
        stmt = (
            select(
                ReadoutDataModel.id,
                ReadoutDataModel.value_numeric,
                ReadoutDataModel.value_qualifier,
                RunModel.id.label("run_id"),
                RunModel.run_date,
                RunModel.status,
                RunModel.qc_metrics,
                ProtocolModel.name,
                ProtocolModel.protocol_version,
                ReadoutDefinitionModel.unit,
            )
            .join(RunModel, ReadoutDataModel.run_id == RunModel.id)
            .join(ProtocolModel, RunModel.protocol_id == ProtocolModel.id)
            .join(
                ReadoutDefinitionModel,
                ReadoutDataModel.readout_definition_id
                == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id == molecule_id,
                ReadoutDataModel.readout_definition_id
                == channel.readout_definition_id,
                # Skip rows with no numeric value — qualitative-only
                # text readouts can't be averaged or compared to
                # numeric hit thresholds.
                ReadoutDataModel.value_numeric.is_not(None),
                # Skip outliers — they would otherwise corrupt MEAN/
                # GEOMEAN aggregations.
                ReadoutDataModel.is_outlier.is_(False),
            )
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        candidates: list[ResolvedCandidate] = []
        for row in rows:
            qualifier_str = row.value_qualifier or "="
            try:
                qualifier = ValueQualifier(qualifier_str)
            except ValueError:
                qualifier = ValueQualifier.EQ
            candidates.append(
                ResolvedCandidate(
                    value=float(row.value_numeric),
                    qualifier=qualifier,
                    unit=row.unit or "",
                    run_id=row.run_id,
                    run_date=row.run_date,
                    run_approved=row.status == "approved",
                    z_prime=(row.qc_metrics or {}).get("z_prime"),
                    protocol_name=row.name,
                    protocol_version=row.protocol_version,
                    curve_id=None,
                    readout_id=row.id,
                )
            )
        return candidates
