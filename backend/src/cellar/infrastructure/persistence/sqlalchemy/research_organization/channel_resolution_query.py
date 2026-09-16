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


def _readout_stmt(
    *,
    workspace_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    normalization_applied: str | None,
    wellless_only: bool = False,
):
    """Base SELECT over readout_data candidates; callers add the scoping clause.

    Shared by the single-molecule and run-scoped endpoint queries so the two
    can't drift on which rows count as a candidate.
    """
    return (
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
            ReadoutDefinitionModel.dose_response_config,
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
            # Skip rows with no numeric value — qualitative-only text
            # readouts can't be averaged or compared to numeric hit
            # thresholds.
            ReadoutDataModel.value_numeric.is_not(None),
            # Skip outliers — they would otherwise corrupt MEAN / GEOMEAN
            # aggregations.
            ReadoutDataModel.is_outlier.is_(False),
            # Control / blank wells carry molecule_id=NULL on readout_data —
            # they're not attributable to a compound and would crash the
            # downstream CampaignResult insert (campaign_result.molecule_id
            # is NOT NULL).
            ReadoutDataModel.molecule_id.is_not(None),
            # Restrict to one normalization layer so a raw readout's computed
            # siblings (percent_inhibition / z_score) don't bleed into the
            # aggregate.
            _normalization_clause(normalization_applied),
            # Reported endpoints are well-less by construction (a summary
            # import records no plate position). Per-well response readings on
            # the same definition must never be averaged into an endpoint.
            *([ReadoutDataModel.well_id.is_(None)] if wellless_only else []),
        )
    )


def _readout_candidate(row, normalization_applied: str | None) -> ResolvedCandidate:
    """Map one ``_readout_stmt`` row onto a candidate."""
    # ponytail: the summary import accepts ">=" / "<=", campaigns only know
    # ">" / "<". Read them as the strict form so ">=40" stays censored instead
    # of falling through to an exact 40. Only a criterion cut at exactly that
    # number can differ; add inclusive qualifiers if that ever matters.
    raw = {">=": ">", "<=": "<"}.get(row.value_qualifier, row.value_qualifier)
    try:
        qualifier = ValueQualifier(raw or "=")
    except ValueError:
        qualifier = ValueQualifier.EQ
    value = float(row.value_numeric)
    # A reported endpoint on a dose-response readout is the value at the
    # readout's primary (first) intercept — a CRO's IC50 column. Tagging it
    # lets a channel keyed to that intercept find it and every other
    # intercept channel skip it (see ``resolve_intercept``).
    intercepts = (row.dose_response_config or {}).get("intercepts") or []
    return ResolvedCandidate(
        value=value,
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
        intercept_values=[{"spec": intercepts[0], "value": value}] if intercepts else None,
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
        run_ids: list[uuid.UUID] | None = None,
    ) -> list[ResolvedCandidate]:
        """``run_ids`` narrows the sweep to those runs; ``None`` = every run
        of the protocol."""
        if channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
            return await self._fetch_curve_candidates(workspace_id, channel, molecule_id, run_ids)
        return await self.fetch_endpoint_candidates(
            workspace_id=workspace_id,
            channel=channel,
            molecule_id=molecule_id,
            run_ids=run_ids,
        )

    async def _fetch_curve_candidates(
        self,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
        run_ids: list[uuid.UUID] | None = None,
    ) -> list[ResolvedCandidate]:
        stmt = (
            select(
                DoseResponseCurveModel.id,
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
                DoseResponseCurveModel.molecule_id == molecule_id,
                DoseResponseCurveModel.protocol_id == channel.protocol_id,
                # Disambiguate among DR readouts on a multi-DR protocol.
                # A protocol can declare N dose-response readouts (target
                # IC50 vs counter-screen IC50, primary vs cytotoxicity, ...).
                # Without this predicate, two DR readouts that happen to
                # share a curve_type would both surface here and the
                # selection rule below would silently pick the wrong one.
                DoseResponseCurveModel.readout_definition_id == channel.readout_definition_id,
                # Campaign run scope (spec D4) — None leaves the sweep
                # protocol-wide.
                *([DoseResponseCurveModel.run_id.in_(run_ids)] if run_ids is not None else []),
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
                intercept_values=row.intercept_values,
                curve_type=row.curve_type,
                curve_confidence_interval_low=row.confidence_interval_low,
                curve_confidence_interval_high=row.confidence_interval_high,
                curve_fit_quality_warnings=row.fit_quality_warnings,
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
                # Pin to the channel's readout-def — see _fetch_curve_candidates
                # for why this matters on multi-DR protocols.
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

        ``wellless_only`` is the dose-response fallback's guard — see the
        sibling method.
        """
        if not run_ids:
            return {}
        stmt = _readout_stmt(
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

    async def fetch_endpoint_candidates(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
        wellless_only: bool = False,
        run_ids: list[uuid.UUID] | None = None,
    ) -> list[ResolvedCandidate]:
        """readout_data candidates for the channel's readout definition.

        The READOUT_DATA implementation of ``fetch_candidates``, and — on a
        dose-response channel — the reported-endpoint fallback the resolver
        reaches for when no curve survives QC. A DR channel carries no
        ``normalization_applied``, so it lands on the raw layer, which is
        where a summary-imported reported IC50 lives.

        ``wellless_only`` narrows to ``well_id IS NULL``: the dose-response
        fallback passes it so a plate column mapped onto a DR definition —
        per-well response readings, which carry a well_id — can never be
        averaged into a fake endpoint. A numeric readout channel legitimately
        reads per-well rows and leaves it off.

        ``run_ids`` narrows the sweep to the campaign's run scope (spec D4);
        ``None`` = every run of the protocol.
        """
        stmt = _readout_stmt(
            workspace_id=workspace_id,
            readout_definition_id=channel.readout_definition_id,
            normalization_applied=channel.normalization_applied,
            wellless_only=wellless_only,
        ).where(
            ReadoutDataModel.molecule_id == molecule_id,
            *([ReadoutDataModel.run_id.in_(run_ids)] if run_ids is not None else []),
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [_readout_candidate(row, channel.normalization_applied) for row in rows]
