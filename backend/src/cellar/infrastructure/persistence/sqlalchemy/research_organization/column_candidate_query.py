"""SQL implementation of ColumnCandidateQuery: every candidate of one column at once.

Readout rows reuse ``_base_readout_stmt`` (workspace, numeric, non-outlier, molecule present,
compound result, one normalization layer) and add what the resolver groups on: the
well's dose (a well on a plate of the row's own run, as ``COMPOUND_RESULT`` reads it),
the run's Test concentration condition, batch and recorded replicate count. A
dose-response column reads its curves plus the well-less endpoints (D1) on the same
definition.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, join, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.research_organization.column_resolution import Candidate
from cellar.application.screening.run_aggregation import ResolvedRun
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import ChannelSourceKind, ValueQualifier
from cellar.domain.research_organization.measurement_facts import (
    TEST_CONCENTRATION,
    Concentration,
    parse_concentration,
)
from cellar.domain.screening_assay.enums import unit_for_normalization
from cellar.domain.shared.units import MICRO, canonical_unit
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.screening_assay._compound_rows_sql import (
    COMPOUND_RESULT,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ConditionDefinitionModel,
    DoseResponseCurveModel,
    PlateModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
    WellModel,
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


def _extract_min_z_prime(qc_metrics: dict[str, Any] | None) -> float | None:
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


def _base_readout_stmt(
    *,
    workspace_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    normalization_applied: str | None,
    wellless_only: bool = False,
) -> Select[Any]:
    """Base SELECT over readout_data candidates; callers add the scoping clause.

    Shared by the column query and the run-scoped add-from-runs queries so they
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
            # A row with no compound would crash the downstream CampaignResult
            # insert (campaign_result.molecule_id is NOT NULL).
            ReadoutDataModel.molecule_id.is_not(None),
            # Sample wells and well-less rows only: control and reference wells
            # that name a compound are plate QC, never one of its picks.
            COMPOUND_RESULT,
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


def _readout_candidate(row: Any, normalization_applied: str | None) -> ResolvedRun:
    """Map one ``_base_readout_stmt`` row onto a candidate."""
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
    return ResolvedRun(
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


def _scope(
    run_col: Any,
    mol_col: Any,
    run_ids: list[uuid.UUID] | None,
    molecule_ids: list[uuid.UUID] | None,
) -> list[ColumnElement[bool]]:
    return [
        *([any_id(run_col, run_ids)] if run_ids is not None else []),
        *([any_id(mol_col, molecule_ids)] if molecule_ids is not None else []),
    ]


def _dose(row: Any) -> Concentration | None:
    """The well's dose (stored in the protocol's dose unit), else the run's Test
    concentration (a bare number in the protocol definition's unit, µM by default)."""
    if row.dose is not None:
        return Concentration(float(row.dose), canonical_unit(row.dose_unit) or row.dose_unit)
    return parse_concentration(row.test_concentration, row.condition_unit or f"{MICRO}M")


class SQLAlchemyColumnCandidateQuery:
    """Production implementation of ColumnCandidateQuery."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def fetch(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        run_ids: list[uuid.UUID] | None,
        molecule_ids: list[uuid.UUID] | None,
    ) -> dict[uuid.UUID, list[Candidate]]:
        if run_ids == [] or molecule_ids == []:
            return {}
        dr = channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE
        out: dict[uuid.UUID, list[Candidate]] = defaultdict(list)
        async with self._sf() as session:
            if dr:
                curves = self._curve_stmt(workspace_id, channel, run_ids, molecule_ids)
                for row in (await session.execute(curves)).all():
                    out[row.molecule_id].append(_curve_candidate(row))
            # A dose-response column's readout rows are its reported endpoints:
            # well-less by construction, so per-well responses never average in.
            readings = self._readout_stmt(workspace_id, channel, run_ids, molecule_ids, dr)
            for row in (await session.execute(readings)).all():
                out[row.molecule_id].append(
                    Candidate(
                        run=_readout_candidate(row, channel.normalization_applied),
                        molecule_id=row.molecule_id,
                        batch_id=row.batch_id,
                        well_id=row.well_id,
                        dose=_dose(row),
                        replicate_count=row.replicate_count,
                        aggregation=row.aggregation or "none",
                    )
                )
        return dict(out)

    @staticmethod
    def _readout_stmt(
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        run_ids: list[uuid.UUID] | None,
        molecule_ids: list[uuid.UUID] | None,
        wellless_only: bool,
    ) -> Select[Any]:
        rd = ReadoutDataModel
        condition_unit = (
            select(ConditionDefinitionModel.unit)
            .where(
                ConditionDefinitionModel.protocol_id == channel.protocol_id,
                ConditionDefinitionModel.name == TEST_CONCENTRATION,
            )
            .limit(1)
            .scalar_subquery()
        )
        well_on_plate = join(WellModel, PlateModel, PlateModel.id == WellModel.plate_id)
        base: Select[Any] = _base_readout_stmt(
            workspace_id=workspace_id,
            readout_definition_id=channel.readout_definition_id,
            normalization_applied=channel.normalization_applied,
            wellless_only=wellless_only,
        )
        return (
            base.outerjoin(
                well_on_plate,
                and_(WellModel.id == rd.well_id, PlateModel.run_id == rd.run_id),
            )
            .add_columns(
                rd.well_id,
                func.coalesce(rd.batch_id, WellModel.batch_id).label("batch_id"),
                rd.replicate_count,
                WellModel.dose,
                ProtocolModel.dose_unit,
                RunModel.conditions[TEST_CONCENTRATION].label("test_concentration"),
                condition_unit.label("condition_unit"),
                ReadoutDefinitionModel.aggregation,
            )
            .where(*_scope(rd.run_id, rd.molecule_id, run_ids, molecule_ids))
        )

    @staticmethod
    def _curve_stmt(
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        run_ids: list[uuid.UUID] | None,
        molecule_ids: list[uuid.UUID] | None,
    ) -> Select[Any]:
        drc = DoseResponseCurveModel
        return (
            select(
                drc.id,
                drc.molecule_id,
                drc.batch_id,
                drc.fitted_value,
                drc.curve_class,
                drc.curve_type,
                drc.top,
                drc.bottom,
                drc.hill_slope,
                drc.r_squared,
                drc.confidence_interval_low,
                drc.confidence_interval_high,
                drc.fit_quality_warnings,
                drc.raw_data,
                drc.excluded_points,
                drc.intercept_values,
                drc.run_id,
                RunModel.run_date,
                RunModel.status,
                RunModel.qc_metrics,
                ProtocolModel.name,
                ProtocolModel.protocol_version,
                ProtocolModel.dose_unit,
            )
            .join(RunModel, drc.run_id == RunModel.id)
            .join(ProtocolModel, drc.protocol_id == ProtocolModel.id)
            .where(
                drc.workspace_id == workspace_id,
                drc.protocol_id == channel.protocol_id,
                # One DR readout of a multi-DR protocol (target vs counter-screen IC50).
                drc.readout_definition_id == channel.readout_definition_id,
                *_scope(drc.run_id, drc.molecule_id, run_ids, molecule_ids),
            )
        )


def _curve_candidate(row: Any) -> Candidate:
    return Candidate(
        run=ResolvedRun(
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
        ),
        molecule_id=row.molecule_id,
        batch_id=row.batch_id,
        well_id=None,
        dose=None,
        replicate_count=None,
    )
