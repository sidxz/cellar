"""SQL implementation of ChannelResolutionQuery: the run-scoped reads of add-from-runs.

Joins dose_response_curves (or readout_data) -> runs -> protocols and
yields ``ResolvedCandidate`` rows per molecule. Workspace scoping is
enforced on the leaf table (curves / readouts) — runs and protocols are
reached only via FK so are transitively scoped. The readout rows share
``_base_readout_stmt`` with ``SQLAlchemyColumnCandidateQuery``.

The unit for dose-response curves comes from ``Protocol.dose_unit``
(curves don't denormalize their unit); the unit for readouts comes
from ``ReadoutDefinition.unit``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.research_organization.channel_resolution import (
    ResolvedCandidate,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    ValueQualifier,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.column_candidate_query import (  # noqa: E501
    _base_readout_stmt,
    _extract_min_z_prime,
    _readout_candidate,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
    ReadoutDataModel,
    RunModel,
)


class SQLAlchemyChannelResolutionQuery:
    """Production implementation of ChannelResolutionQuery."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def fetch_candidates_for_runs(
        self,
        *,
        workspace_id: uuid.UUID,
        run_ids: list[uuid.UUID],
        protocol_id: uuid.UUID,
        readout_definition_id: uuid.UUID,
        source_kind: ChannelSourceKind,
        normalization_applied: str | None = None,
    ) -> dict[uuid.UUID, list[ResolvedCandidate]]:
        """Per-molecule candidates restricted to a set of run_ids.

        Used by PreviewRunImport / AddResultsFromRuns when the user selects a
        subset of runs to import from — the SELECTION rule then operates over
        only this candidate set, not all runs of the protocol.
        """
        if not run_ids:
            return {}
        if source_kind != ChannelSourceKind.DOSE_RESPONSE_CURVE:
            return await self.fetch_endpoint_candidates_for_runs(
                workspace_id=workspace_id,
                run_ids=run_ids,
                readout_definition_id=readout_definition_id,
                normalization_applied=normalization_applied,
            )

        stmt = (
            select(
                DoseResponseCurveModel.id,
                DoseResponseCurveModel.molecule_id,
                DoseResponseCurveModel.fitted_value,
                DoseResponseCurveModel.curve_class,
                DoseResponseCurveModel.curve_type,
                DoseResponseCurveModel.top,
                DoseResponseCurveModel.bottom,
                DoseResponseCurveModel.hill_slope,
                DoseResponseCurveModel.r_squared,
                DoseResponseCurveModel.confidence_interval_low,
                DoseResponseCurveModel.confidence_interval_high,
                DoseResponseCurveModel.fit_quality_warnings,
                DoseResponseCurveModel.raw_data,
                DoseResponseCurveModel.excluded_points,
                DoseResponseCurveModel.intercept_values,
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
                DoseResponseCurveModel.protocol_id == protocol_id,
                DoseResponseCurveModel.run_id.in_(run_ids),
                # Pin to the channel's readout-def: a protocol can declare
                # several DR readouts (target vs counter-screen IC50).
                DoseResponseCurveModel.readout_definition_id == readout_definition_id,
            )
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()

        out: dict[uuid.UUID, list[ResolvedCandidate]] = defaultdict(list)
        for row in rows:
            out[row.molecule_id].append(
                ResolvedCandidate(
                    value=row.fitted_value,
                    qualifier=ValueQualifier.EQ,
                    unit=row.dose_unit or "",
                    run_id=row.run_id,
                    run_date=row.run_date,
                    run_approved=row.status == "approved",
                    z_prime=_extract_min_z_prime(row.qc_metrics),
                    protocol_name=row.name,
                    protocol_version=row.protocol_version,
                    curve_id=row.id,
                    readout_id=None,
                    curve_class=row.curve_class,
                    curve_top=row.top,
                    curve_bottom=row.bottom,
                    curve_hill_slope=row.hill_slope,
                    curve_r_squared=row.r_squared,
                    curve_raw_data=row.raw_data,
                    curve_excluded_points=row.excluded_points,
                    intercept_values=row.intercept_values,
                    curve_type=row.curve_type,
                    curve_confidence_interval_low=row.confidence_interval_low,
                    curve_confidence_interval_high=row.confidence_interval_high,
                    curve_fit_quality_warnings=row.fit_quality_warnings,
                )
            )
        return dict(out)

    async def fetch_endpoint_candidates_for_runs(
        self,
        *,
        workspace_id: uuid.UUID,
        run_ids: list[uuid.UUID],
        readout_definition_id: uuid.UUID,
        normalization_applied: str | None = None,
        wellless_only: bool = False,
    ) -> dict[uuid.UUID, list[ResolvedCandidate]]:
        """Per-molecule readout_data candidates restricted to a set of run_ids.

        Serves both the READOUT_DATA branch of ``fetch_candidates_for_runs``
        and the dose-response reported-endpoint fallback shared by the
        add-from-runs preview and commit. The readout definition already pins
        the protocol, so no ``protocol_id`` is taken.

        ``wellless_only`` narrows to ``well_id IS NULL``, the dose-response
        fallback's guard: per-well response readings on a DR definition are
        never a reported endpoint.
        """
        if not run_ids:
            return {}
        stmt = _base_readout_stmt(
            workspace_id=workspace_id,
            readout_definition_id=readout_definition_id,
            normalization_applied=normalization_applied,
            wellless_only=wellless_only,
        ).where(ReadoutDataModel.run_id.in_(run_ids))
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()

        out: dict[uuid.UUID, list[ResolvedCandidate]] = defaultdict(list)
        for row in rows:
            out[row.molecule_id].append(_readout_candidate(row, normalization_applied))
        return dict(out)
