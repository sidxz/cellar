"""Add-from-runs: the one computation behind the import dialog's preview and commit (B6).

``apply_run_import`` applies a request to the loaded campaign (spec §6.3, §10):

1. The runs join the target stage: ``stage_id``, else the ``stage_name`` upsert, else
   none (campaign runs feeding campaign columns).
2. Each config's column on that stage is reused or created, keyed
   ``(stage, protocol, readout, normalization, intercept)``.
3. Configs carrying thresholds replace the stage's criteria; without thresholds the
   criteria are left alone.
4. The compounds of the request's runs become rows. ``allowed_curve_classes`` is a row
   filter only, never applied to values.
5. Every target column is recomputed for every row by ``recompute_columns``, over all
   of the stage's runs, so ``scope: hits_only`` judges the values the commit writes.

``AddResultsFromRuns`` saves the result. ``PreviewRunImport`` reads it and never saves,
so the preview shows exactly the cells the commit would write.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.column_resolution import ColumnCandidateQuery
from cellar.application.research_organization.recompute_columns import recompute_columns
from cellar.application.research_organization.stage_upsert import (
    get_or_create_stage,
    set_stage_criteria,
)
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import StageCriterion
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.source_ref import RunRef, SeedRun
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ChannelImportConfig:
    """One row in the import dialog's channel-configuration section.

    Maps to a (protocol_id, readout_definition_id) tuple within the selected runs.
    If the target stage already has a column for it, the preview marks it `reused`.

    ``hit_threshold`` and ``allowed_curve_classes`` decide which compounds are added
    (``allowed_curve_classes`` only for ``DOSE_RESPONSE_CURVE``: a compound whose
    every curve in the runs is out of class is skipped). Neither is saved on the
    column, and neither is ever applied to a value.
    """

    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    label: str
    source_kind: ChannelSourceKind
    selection_rule: SelectionRule
    hit_threshold: HitCriterion | None = None
    use_for_filter: bool = True
    allowed_curve_classes: list[str] | None = None
    #: Normalization layer when source_kind is READOUT_DATA (None = raw,
    #: "percent_inhibition" / "z_score" / … select that computed layer).
    #: Ignored for dose-response curve channels.
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces
    #: (e.g. EC90). ``None`` means the curve's primary intercept (legacy
    #: single-intercept channels). Lives on the config — NOT inside
    #: ``hit_threshold`` — so a display-only channel without a threshold
    #: still carries its intercept identity end-to-end.
    intercept_key: InterceptKey | None = None


@dataclass(frozen=True, kw_only=True)
class PreviewRunImportQuery(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfig]
    filter_mode: Literal["any", "all"] = "all"
    #: The stage the runs would join; None previews them as campaign runs.
    stage_id: uuid.UUID | None = None


def _cfg_norm(cfg: ChannelImportConfig) -> str | None:
    """The normalization layer a config's candidates live on.

    Dose-response channels carry no normalization — their value comes from a
    fitted curve, not a formula layer.
    """
    return cfg.normalization_applied if cfg.source_kind == ChannelSourceKind.READOUT_DATA else None


# ---------------------------------------------------------------------------
# The import
# ---------------------------------------------------------------------------


@dataclass
class RunImport:
    """What one add-from-runs request did to the loaded campaign."""

    #: The target column of each config, in config order.
    columns: list[CampaignChannel]
    reused: list[bool]
    stage_created: bool
    #: Every compound of the request's runs that passed the row filter, with its
    #: row: an existing one, or a new one whose cells are resolved (on the campaign
    #: only when it was added).
    rows: dict[uuid.UUID, CampaignResult]
    is_hit: dict[uuid.UUID, bool]
    added: int
    skipped: int


async def apply_run_import(
    campaign: Campaign,
    *,
    query: ColumnCandidateQuery,
    runs: Mapping[uuid.UUID, Run],
    run_ids: list[uuid.UUID],
    configs: list[ChannelImportConfig],
    filter_mode: Literal["any", "all"],
    scope: Literal["hits_only", "all"],
    description: str | None = None,
    stage_id: uuid.UUID | None = None,
    stage_name: str | None = None,
    parent_stage_id: uuid.UUID | None = None,
) -> RunImport:
    """Apply an add-from-runs request to ``campaign`` (see the module docstring).

    ``runs`` are the request's runs found in the workspace. Raises the domain's
    ``NotFoundError`` (unknown stage) and ``ValidationError``.
    """
    run_ids = [r for r in run_ids if r in runs]

    stage = None
    stage_created = False
    if stage_id is not None:
        stage = campaign.find_stage(stage_id)
        if stage is None:
            raise NotFoundError("CampaignStage", str(stage_id))
    elif stage_name:
        stage, stage_created = get_or_create_stage(
            campaign, name=stage_name, parent_stage_id=parent_stage_id
        )
    target = stage.id if stage else None
    campaign.add_runs_to_stage((SeedRun(r, runs[r].protocol_id) for r in run_ids), target)

    by_key = {
        (
            c.stage_id,
            c.protocol_id,
            c.readout_definition_id,
            c.normalization_applied,
            c.intercept_key,
        ): c
        for c in campaign.channels
    }
    order = max((c.display_order for c in campaign.channels), default=-1) + 1
    columns: list[CampaignChannel] = []
    reused: list[bool] = []
    for cfg in configs:
        key = (
            target,
            cfg.protocol_id,
            cfg.readout_definition_id,
            _cfg_norm(cfg),
            cfg.intercept_key,
        )
        column = by_key.get(key)
        reused.append(column is not None)
        if column is None:
            column = CampaignChannel(
                campaign_id=campaign.id,
                label=cfg.label,
                protocol_id=cfg.protocol_id,
                readout_definition_id=cfg.readout_definition_id,
                source_kind=cfg.source_kind,
                selection_rule=cfg.selection_rule,
                qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                display_order=order,
                normalization_applied=_cfg_norm(cfg),
                intercept_key=cfg.intercept_key,
                stage_id=target,
            )
            campaign.add_channel(column)
            by_key[key] = column
            order += 1
        else:
            # The chemist's rule applies; intercept identity is locked at creation.
            column.selection_rule = cfg.selection_rule
        columns.append(column)

    # Numeric only: StageCriterion has no string-based ``in``.
    criteria = [
        StageCriterion(
            channel_id=col.id,
            operator=cfg.hit_threshold.operator,
            value=cfg.hit_threshold.value,  # type: ignore[arg-type]  # numeric once "in" is out
        )
        for cfg, col in zip(configs, columns, strict=True)
        if cfg.use_for_filter and cfg.hit_threshold and cfg.hit_threshold.operator != "in"
    ]
    if stage is not None and criteria:
        set_stage_criteria(campaign, stage, criteria)

    # The request's compounds, with the earliest run each was measured in (its RunRef).
    first_run: dict[uuid.UUID, tuple[date, uuid.UUID]] = {}
    out_of_class: set[uuid.UUID] = set()
    for cfg, column in zip(configs, columns, strict=True):
        found = await query.fetch(
            workspace_id=campaign.workspace_id, channel=column, run_ids=run_ids, molecule_ids=None
        )
        allowed = set(cfg.allowed_curve_classes or ())
        for mid, candidates in found.items():
            classes = {c.run.curve_class for c in candidates if c.run.curve_id is not None}
            if allowed and classes and not classes & allowed:
                out_of_class.add(mid)
            earliest = min((c.run.run_date or date.max, c.run.run_id) for c in candidates)
            first_run[mid] = min(first_run.get(mid, earliest), earliest)
    compounds = [m for m in first_run if m not in out_of_class]

    rows = {r.molecule_id: r for r in campaign.results if r.molecule_id in first_run}
    new_rows = [
        CampaignResult(
            campaign_id=campaign.id,
            molecule_id=m,
            added_from=RunRef(run_id=first_run[m][1], description=description),
        )
        for m in compounds
        if m not in rows
    ]
    rows.update((r.molecule_id, r) for r in new_rows)
    rows = {m: rows[m] for m in compounds}
    await recompute_columns(
        query=query,
        campaign=campaign,
        channels={c.id: c for c in columns}.values(),
        extra_rows=new_rows,
    )

    is_hit = {m: _is_hit(rows[m], configs, columns, filter_mode) for m in compounds}
    kept = [r for r in new_rows if scope == "all" or is_hit[r.molecule_id]]
    campaign.add_results(kept)
    passing = sum(1 for m in compounds if scope == "all" or is_hit[m])
    return RunImport(
        columns=columns,
        reused=reused,
        stage_created=stage_created,
        rows=rows,
        is_hit=is_hit,
        added=len(kept),
        skipped=passing - len(kept),
    )


def _hit_call(cfg: ChannelImportConfig, m: CampaignMeasurement) -> str | None:
    if cfg.hit_threshold is None or m.value is None:
        return None
    met = cfg.hit_threshold.is_met(m.value, m.value_qualifier)
    return None if met is None else ("hit" if met else "miss")


def _is_hit(
    row: CampaignResult,
    configs: list[ChannelImportConfig],
    columns: list[CampaignChannel],
    filter_mode: Literal["any", "all"],
) -> bool:
    """The request's filter over the row's cells. A cell with no reading behind it
    is skipped; no filtering cell at all is never a hit."""
    calls = [
        _hit_call(cfg, m) == "hit"
        for cfg, column in zip(configs, columns, strict=True)
        if cfg.use_for_filter
        and cfg.hit_threshold is not None
        and (m := row.find_measurement(column.id)) is not None
        and (m.value is not None or m.contributing_run_ids)
    ]
    return bool(calls) and (any(calls) if filter_mode == "any" else all(calls))


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class PreviewRunImport:
    """The would-be cells of an add-from-runs request, computed by the commit's own
    path against the loaded campaign, which is never saved."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        run_repo: RunRepository,
        molecule_repo: MoleculeRepository,
        query: ColumnCandidateQuery,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._run_repo = run_repo
        self._molecule_repo = molecule_repo
        self._query = query

    async def __call__(
        self,
        input: PreviewRunImportQuery,
        auth: AuthContext | None = None,
    ) -> Result[dict[str, Any], DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        # Never committed: the import below only mutates the loaded aggregate.
        async with self._uow:
            return await self._execute(input)

    async def _execute(self, q: PreviewRunImportQuery) -> Result[dict[str, Any], DomainError]:
        campaign = await self._campaign_repo.find_by_id_in_workspace(q.workspace_id, q.campaign_id)
        if campaign is None:
            return Failure(NotFoundError("Campaign", str(q.campaign_id)))
        if not q.run_ids:
            return Failure(ValidationError("At least one run_id is required"))
        if not q.channel_configs:
            return Failure(ValidationError("At least one channel_config is required"))

        in_campaign = {r.molecule_id for r in campaign.results}
        runs = await self._run_repo.find_by_ids(q.workspace_id, q.run_ids)
        try:
            imp = await apply_run_import(
                campaign,
                query=self._query,
                runs=runs,
                run_ids=q.run_ids,
                configs=q.channel_configs,
                filter_mode=q.filter_mode,
                scope="all",
                stage_id=q.stage_id,
            )
        except (NotFoundError, ValidationError) as e:
            return Failure(e)

        keys = [_channel_key(cfg) for cfg in q.channel_configs]
        channels_meta = [
            {
                "channel_key": key,
                "label": cfg.label,
                "source": "reused" if was_reused else "new",
                "reuse_of_channel_id": str(column.id) if was_reused else None,
                "selection_rule": cfg.selection_rule.value,
                "hit_threshold": cfg.hit_threshold.to_dict() if cfg.hit_threshold else None,
                "use_for_filter": cfg.use_for_filter,
            }
            for cfg, key, column, was_reused in zip(
                q.channel_configs, keys, imp.columns, imp.reused, strict=True
            )
        ]

        molecules = await self._molecule_repo.find_by_ids(q.workspace_id, list(imp.rows))
        mol_lookup = {m.id: m for m in molecules}
        rows_response: list[dict[str, Any]] = []
        for mid, row in imp.rows.items():
            mol = mol_lookup.get(mid)
            if mol is None:
                continue
            rows_response.append(
                {
                    "molecule": {
                        "id": str(mol.id),
                        "registration_number": mol.registration_number.value,
                        "name": mol.name,
                        "smiles": mol.structure.smiles if mol.structure else None,
                    },
                    "is_hit": imp.is_hit[mid],
                    "already_in_campaign": mid in in_campaign,
                    "cells": [
                        _cell(key, cfg, m)
                        for cfg, key, column in zip(
                            q.channel_configs, keys, imp.columns, strict=True
                        )
                        if (m := row.find_measurement(column.id)) is not None
                    ],
                }
            )

        hits = sum(1 for r in rows_response if r["is_hit"])
        return Success(
            {
                "summary": {
                    "runs": len(q.run_ids),
                    "channels_new": imp.reused.count(False),
                    "channels_reused": imp.reused.count(True),
                    "molecules_total": len(rows_response),
                    "hits": hits,
                    "non_hits": len(rows_response) - hits,
                    "molecules_already_in_campaign": sum(
                        1 for r in rows_response if r["already_in_campaign"]
                    ),
                },
                "channels": channels_meta,
                "rows": rows_response,
            }
        )


def _channel_key(cfg: ChannelImportConfig) -> str:
    norm = _cfg_norm(cfg)
    ik = cfg.intercept_key
    return (
        f"{cfg.protocol_id}/{cfg.readout_definition_id}"
        f"{f':{norm}' if norm else ''}{f':{ik.kind}{ik.level}' if ik else ''}"
    )


def _cell(key: str, cfg: ChannelImportConfig, m: CampaignMeasurement) -> dict[str, Any]:
    """A preview cell: the measurement the commit writes, plus the request's hit call."""
    return {
        "channel_key": key,
        "value": m.value,
        "value_qualifier": m.value_qualifier.value,
        "unit": m.unit,
        "test_concentration_value": m.test_concentration_value,
        "test_concentration_unit": m.test_concentration_unit,
        "replicate_count": m.replicate_count,
        "qc_pass": m.qc_pass,
        # The import-time QC heuristic is gone: the column's own QC filter decides
        # which readings count, and no reason is recorded on the value.
        "qc_reason": None,
        "hit_call": _hit_call(cfg, m),
        "source_run_id": str(m.source_run_id) if m.source_run_id else None,
        "source_run_date": m.run_date_snapshot.isoformat() if m.run_date_snapshot else None,
        "protocol_name": m.protocol_name_snapshot,
        "protocol_version": m.protocol_version_snapshot,
        "contributing_run_ids": [str(r) for r in m.contributing_run_ids or []],
        "basis": m.basis.value if m.basis else None,
        "batch_ids": [str(b) for b in m.batch_ids or []],
        "concentration_series": m.concentration_series,
        "unresolved_reason": m.unresolved_reason.value if m.unresolved_reason else None,
        "concentrations_found": (
            [{"value": c.value, "unit": c.unit} for c in m.concentrations_found]
            if m.concentrations_found is not None
            else None
        ),
    }
