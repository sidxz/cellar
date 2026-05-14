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
from collections import defaultdict

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.research_organization.channel_resolution import (
    ResolvedCandidate,
)
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    ValueQualifier,
)
from cellar.domain.screening_assay.enums import unit_for_normalization
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
)


def _normalization_clause(normalization_applied: str | None) -> ColumnElement[bool]:
    """SQL predicate that pins readout_data to one ``normalization_applied`` layer.

    Without this filter raw rows and their computed siblings
    (percent_inhibition / z_score / …) share a single ``readout_definition_id``
    and would all be returned, mixing absorbance with percentages.
    """
    if normalization_applied is None:
        return ReadoutDataModel.normalization_applied.is_(None)
    return ReadoutDataModel.normalization_applied == normalization_applied


def _extract_min_z_prime(qc_metrics: dict | None) -> float | None:
    """Return the worst-case scalar z' from a Run's qc_metrics JSONB.

    Production shape is nested per-plate:
        {"z_prime": {"<plate_uuid>": {"z_prime": 0.834, ...}, ...}}

    Test fixtures (and some early data) used the flat shape:
        {"z_prime": 0.8}

    We support both, returning the minimum (most conservative) across plates
    when the nested shape is present. Returns None when the value is missing
    or unparseable.
    """
    if not qc_metrics:
        return None
    raw = qc_metrics.get("z_prime")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        values: list[float] = []
        for plate_entry in raw.values():
            if isinstance(plate_entry, (int, float)):
                values.append(float(plate_entry))
            elif isinstance(plate_entry, dict):
                v = plate_entry.get("z_prime")
                if isinstance(v, (int, float)):
                    values.append(float(v))
        return min(values) if values else None
    return None


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
            return await self._fetch_curve_candidates(workspace_id, channel, molecule_id)
        return await self._fetch_readout_candidates(workspace_id, channel, molecule_id)

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
                DoseResponseCurveModel.curve_class,
                DoseResponseCurveModel.top,
                DoseResponseCurveModel.bottom,
                DoseResponseCurveModel.hill_slope,
                DoseResponseCurveModel.r_squared,
                DoseResponseCurveModel.raw_data,
                DoseResponseCurveModel.excluded_points,
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
                # Disambiguate among DR readouts on a multi-DR protocol.
                # A protocol can declare N dose-response readouts (target
                # IC50 vs counter-screen IC50, primary vs cytotoxicity, ...).
                # Without this predicate, two DR readouts that happen to
                # share a curve_type would both surface here and the
                # selection rule below would silently pick the wrong one.
                DoseResponseCurveModel.readout_definition_id
                == channel.readout_definition_id,
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
            )
            for row in rows
        ]

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
        if source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
            stmt = (
                select(
                    DoseResponseCurveModel.id,
                    DoseResponseCurveModel.molecule_id,
                    DoseResponseCurveModel.fitted_value,
                    DoseResponseCurveModel.curve_class,
                    DoseResponseCurveModel.top,
                    DoseResponseCurveModel.bottom,
                    DoseResponseCurveModel.hill_slope,
                    DoseResponseCurveModel.r_squared,
                    DoseResponseCurveModel.raw_data,
                    DoseResponseCurveModel.excluded_points,
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
                    # Pin to the channel's readout-def — see _fetch_curve_candidates
                    # for why this matters on multi-DR protocols.
                    DoseResponseCurveModel.readout_definition_id == readout_definition_id,
                )
            )
        else:
            stmt = (
                select(
                    ReadoutDataModel.id,
                    ReadoutDataModel.molecule_id,
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
                    ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
                )
                .where(
                    ReadoutDataModel.workspace_id == workspace_id,
                    ReadoutDataModel.readout_definition_id == readout_definition_id,
                    ReadoutDataModel.run_id.in_(run_ids),
                    ReadoutDataModel.value_numeric.is_not(None),
                    ReadoutDataModel.is_outlier.is_(False),
                    _normalization_clause(normalization_applied),
                )
            )

        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()

        out: dict[uuid.UUID, list[ResolvedCandidate]] = defaultdict(list)
        for row in rows:
            if source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
                cand = ResolvedCandidate(
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
                )
            else:
                qualifier_str = row.value_qualifier or "="
                try:
                    qualifier = ValueQualifier(qualifier_str)
                except ValueError:
                    qualifier = ValueQualifier.EQ
                cand = ResolvedCandidate(
                    value=float(row.value_numeric),
                    qualifier=qualifier,
                    unit=unit_for_normalization(normalization_applied, row.unit) or "",
                    run_id=row.run_id,
                    run_date=row.run_date,
                    run_approved=row.status == "approved",
                    z_prime=_extract_min_z_prime(row.qc_metrics),
                    protocol_name=row.name,
                    protocol_version=row.protocol_version,
                    curve_id=None,
                    readout_id=row.id,
                )
            out[row.molecule_id].append(cand)
        return dict(out)

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
                ReadoutDataModel.readout_definition_id == ReadoutDefinitionModel.id,
            )
            .where(
                ReadoutDataModel.workspace_id == workspace_id,
                ReadoutDataModel.molecule_id == molecule_id,
                ReadoutDataModel.readout_definition_id == channel.readout_definition_id,
                # Skip rows with no numeric value — qualitative-only
                # text readouts can't be averaged or compared to
                # numeric hit thresholds.
                ReadoutDataModel.value_numeric.is_not(None),
                # Skip outliers — they would otherwise corrupt MEAN/
                # GEOMEAN aggregations.
                ReadoutDataModel.is_outlier.is_(False),
                # Restrict to the channel's normalization layer so a raw
                # readout's computed siblings (percent_inhibition / z_score)
                # don't bleed into the aggregate.
                _normalization_clause(channel.normalization_applied),
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
                    unit=unit_for_normalization(channel.normalization_applied, row.unit) or "",
                    run_id=row.run_id,
                    run_date=row.run_date,
                    run_approved=row.status == "approved",
                    z_prime=_extract_min_z_prime(row.qc_metrics),
                    protocol_name=row.name,
                    protocol_version=row.protocol_version,
                    curve_id=None,
                    readout_id=row.id,
                )
            )
        return candidates
