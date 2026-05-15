"""PreviewRunImport — read-only query for the multi-run import dialog (B6).

Given a campaign + a set of run_ids + per-readout channel configs (with
hit criteria), this resolves every molecule × channel cell that *would*
be added, applies the user's filter mode (ANY/ALL), and returns a
DAIKON-shaped preview document for the FE to render — without mutating
the campaign.

DRY: hit-call computation reuses ``_compute_hit_call``; candidate
fetching reuses ``ChannelResolutionQuery.fetch_candidates_for_runs``.
Selection-rule application is inlined here (the close-time
``ChannelResolver`` has near-identical logic — to be shared via a common
helper in a follow-up refactor).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.research_organization.channel_resolution import (
    ChannelResolutionQuery,
    ResolvedCandidate,
    _build_curve_snapshot,
    _compute_hit_call,
    _intercept_scalar,
    _resolve_intercept,
)
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.repository import RunRepository
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

    Maps to a (protocol_id, readout_definition_id) tuple within the
    selected runs. If a campaign channel already exists for the same
    (protocol, readout), the preview marks it as `reused`.

    ``allowed_curve_classes`` is only meaningful when source_kind is
    ``DOSE_RESPONSE_CURVE`` — restricts candidates to curves whose
    ``curve_class`` is in the supplied set (e.g. ``["full"]``).
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


# ---------------------------------------------------------------------------
# Selection-rule inline (matches ChannelResolver.resolve; see module docstring)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Picked:
    #: The channel's value for this molecule — the curve's primary fitted
    #: value when ``intercept_key`` is None, or the matching intercept's
    #: scalar otherwise. After Option A, channel identity is on the
    #: channel itself; this single field IS the cell value and the input
    #: to the hit-call comparison.
    value: float | None
    qualifier: ValueQualifier
    unit: str
    source_run_id: uuid.UUID | None
    source_curve_id: uuid.UUID | None
    source_readout_id: uuid.UUID | None
    protocol_name: str
    protocol_version: int
    run_date: date | None
    contributing_run_ids: list[uuid.UUID]
    replicate_count: int
    #: Frozen curve shape (DR-curve picks only). Built from the
    #: representative candidate so the campaign cell can render the
    #: dose-response figure without a live FK lookup.
    curve_snapshot: dict | None = None


def _apply_selection_rule(
    candidates: list[ResolvedCandidate],
    rule: SelectionRule,
    intercept_key: InterceptKey | None = None,
) -> _Picked | None:
    """Apply a selection rule to a pre-filtered candidate list.

    Returns None for ND (empty candidates, MANUAL_PICK, or — for
    GEOMETRIC_MEAN — when no candidate has a strictly positive value).

    ``intercept_key`` identifies which value to extract per candidate
    before aggregating: ``None`` reads ``c.value`` (primary fit or raw
    readout), otherwise looks up the matching intercept on
    ``c.intercept_values``. For MEAN / GEOMETRIC_MEAN, the aggregate is
    computed over each candidate's intercept-specific value (so the mean
    EC90 is the average of three EC90 numbers, not the EC90 lookup on the
    average curve).
    """
    if not candidates:
        return None
    contributing = [c.run_id for c in candidates]
    n = len(candidates)
    unit_seed = candidates[0].unit or "-"
    pname_seed = candidates[0].protocol_name
    pver_seed = candidates[0].protocol_version

    # Representative candidate for curve-shape snapshot (latest run by date).
    # No-op for readout_data sources — _build_curve_snapshot returns None
    # when the candidate carries no curve_top/bottom/hill_slope.
    rep = max(candidates, key=lambda c: c.run_date or date.min)
    snapshot = _build_curve_snapshot(rep)

    if rule == SelectionRule.LATEST_APPROVED_RUN:
        pick = rep
        value, resolved_qualifier = _resolve_intercept(pick, intercept_key)
        # Resolver-derived qualifier (ND / GT-from-at-bound) overrides the
        # candidate's wire-level qualifier; see the matching note in
        # channel_resolution.resolve().
        qualifier = (
            resolved_qualifier
            if resolved_qualifier != ValueQualifier.EQ
            else pick.qualifier
        )
        return _Picked(
            value=value,
            qualifier=qualifier,
            unit=pick.unit or "-",
            source_run_id=pick.run_id,
            source_curve_id=pick.curve_id,
            source_readout_id=pick.readout_id,
            protocol_name=pick.protocol_name,
            protocol_version=pick.protocol_version,
            run_date=pick.run_date,
            contributing_run_ids=contributing,
            replicate_count=n,
            curve_snapshot=snapshot,
        )
    if rule == SelectionRule.MEAN_ACROSS_RUNS:
        # _intercept_scalar already drops non-EQ candidates (Inactive,
        # at_bound, missing intercept) — aggregates only the healthy ones.
        ik_vals = [
            v
            for v in (_intercept_scalar(c, intercept_key) for c in candidates)
            if v is not None
        ]
        value: float | None = sum(ik_vals) / len(ik_vals) if ik_vals else None
        return _Picked(
            value=value,
            qualifier=ValueQualifier.EQ,
            unit=unit_seed,
            source_run_id=None,
            source_curve_id=None,
            source_readout_id=None,
            protocol_name=pname_seed,
            protocol_version=pver_seed,
            run_date=None,
            contributing_run_ids=contributing,
            replicate_count=n,
            curve_snapshot=snapshot,
        )
    if rule == SelectionRule.GEOMETRIC_MEAN:
        positives = [
            v
            for v in (_intercept_scalar(c, intercept_key) for c in candidates)
            if v is not None and v > 0
        ]
        if not positives:
            return None
        return _Picked(
            value=math.exp(sum(math.log(v) for v in positives) / len(positives)),
            qualifier=ValueQualifier.EQ,
            unit=unit_seed,
            source_run_id=None,
            source_curve_id=None,
            source_readout_id=None,
            protocol_name=pname_seed,
            protocol_version=pver_seed,
            run_date=None,
            contributing_run_ids=contributing,
            replicate_count=n,
            curve_snapshot=snapshot,
        )
    # MANUAL_PICK — ND placeholder
    return None


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class PreviewRunImport:
    """Resolves every molecule x channel cell from a candidate run set."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        run_repo: RunRepository,
        molecule_repo: MoleculeRepository,
        channel_query: ChannelResolutionQuery,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._run_repo = run_repo
        self._molecule_repo = molecule_repo
        self._query = channel_query

    async def __call__(
        self,
        input: PreviewRunImportQuery,
        auth: AuthContext | None = None,
    ) -> Result[dict[str, Any], DomainError]:
        require_editor(auth)
        async with self._uow:
            return await self._execute(input)

    async def _execute(self, q: PreviewRunImportQuery) -> Result[dict[str, Any], DomainError]:
        # Step 1 — load campaign (preview is read-only; DRAFT not required).
        campaign = await self._campaign_repo.find_by_id_in_workspace(q.workspace_id, q.campaign_id)
        if campaign is None:
            return Failure(NotFoundError("Campaign", str(q.campaign_id)))

        if not q.run_ids:
            return Failure(ValidationError("At least one run_id is required"))
        if not q.channel_configs:
            return Failure(ValidationError("At least one channel_config is required"))

        # Step 2 — channel meta (new vs reused). Reuse key is
        # (protocol, readout, normalization_applied, intercept_key) so the
        # same readout exposed through different intercepts (e.g. Resazurin
        # EC50 + Resazurin EC90) becomes distinct channels — they each
        # display their own intercept's value and have independent hit
        # decisions. After Option A the intercept_key lives on the channel
        # / config directly, not under hit_threshold, so a display-only
        # channel (no threshold) still keeps its intercept identity.
        def _cfg_norm(cfg: ChannelImportConfig) -> str | None:
            return (
                cfg.normalization_applied
                if cfg.source_kind == ChannelSourceKind.READOUT_DATA
                else None
            )

        existing_by_key: dict[tuple[Any, ...], Any] = {
            (
                ch.protocol_id,
                ch.readout_definition_id,
                ch.normalization_applied,
                ch.intercept_key,
            ): ch
            for ch in campaign.channels
        }
        channels_meta: list[dict[str, Any]] = []

        def _channel_key(cfg: ChannelImportConfig) -> str:
            norm = _cfg_norm(cfg)
            norm_suffix = f":{norm}" if norm else ""
            ik = cfg.intercept_key
            ik_suffix = f":{ik.kind}{ik.level}" if ik else ""
            return f"{cfg.protocol_id}/{cfg.readout_definition_id}{norm_suffix}{ik_suffix}"

        for cfg in q.channel_configs:
            key = (
                cfg.protocol_id,
                cfg.readout_definition_id,
                _cfg_norm(cfg),
                cfg.intercept_key,
            )
            existing = existing_by_key.get(key)
            channels_meta.append(
                {
                    "channel_key": _channel_key(cfg),
                    "label": cfg.label,
                    "source": "reused" if existing else "new",
                    "reuse_of_channel_id": str(existing.id) if existing else None,
                    "selection_rule": cfg.selection_rule.value,
                    "hit_threshold": (cfg.hit_threshold.to_dict() if cfg.hit_threshold else None),
                    "use_for_filter": cfg.use_for_filter,
                }
            )

        # Step 3 — resolve cells per channel.
        rows_by_molecule: dict[uuid.UUID, dict[str, Any]] = {}
        active_keys: set[str] = set()
        for cfg in q.channel_configs:
            key = _channel_key(cfg)
            if cfg.use_for_filter and cfg.hit_threshold is not None:
                active_keys.add(key)
            candidates_by_mol = await self._query.fetch_candidates_for_runs(
                workspace_id=q.workspace_id,
                run_ids=q.run_ids,
                protocol_id=cfg.protocol_id,
                readout_definition_id=cfg.readout_definition_id,
                source_kind=cfg.source_kind,
                normalization_applied=cfg.normalization_applied,
            )
            for molecule_id, candidates in candidates_by_mol.items():
                # B6: optional curve_class filter (DR-curve sources only).
                if cfg.allowed_curve_classes:
                    allowed = set(cfg.allowed_curve_classes)
                    candidates = [
                        c
                        for c in candidates
                        if c.curve_class is not None and c.curve_class in allowed
                    ]
                    if not candidates:
                        continue
                picked = _apply_selection_rule(
                    candidates, cfg.selection_rule, cfg.intercept_key
                )
                if picked is None:
                    cell = _nd_cell(key)
                else:
                    # After Option A, picked.value already IS the channel's
                    # intercept value (primary if intercept_key is None,
                    # intercept-specific otherwise). Threshold compares
                    # against that value directly.
                    hit = (
                        _compute_hit_call(picked.value, cfg.hit_threshold)
                        if cfg.hit_threshold
                        else None
                    )
                    qc_pass_all = all(_qc_pass(c) for c in candidates)
                    qc_reason = _aggregate_qc_reason(candidates) if not qc_pass_all else None
                    cell = {
                        "channel_key": key,
                        "value": picked.value,
                        "value_qualifier": picked.qualifier.value,
                        "unit": picked.unit,
                        "test_concentration_value": None,
                        "test_concentration_unit": None,
                        "replicate_count": picked.replicate_count,
                        "qc_pass": qc_pass_all,
                        "qc_reason": qc_reason,
                        "hit_call": hit.value if hit else None,
                        "source_run_id": (
                            str(picked.source_run_id) if picked.source_run_id else None
                        ),
                        "source_run_date": (
                            picked.run_date.isoformat() if picked.run_date else None
                        ),
                        "protocol_name": picked.protocol_name,
                        "protocol_version": picked.protocol_version,
                        "contributing_run_ids": [str(rid) for rid in picked.contributing_run_ids],
                    }
                row = rows_by_molecule.setdefault(molecule_id, {"cells": []})
                row["cells"].append(cell)

        # Step 4 — is_hit per molecule.
        in_campaign = {r.molecule_id for r in campaign.results}
        for mid, row in rows_by_molecule.items():
            active_cells = [c for c in row["cells"] if c["channel_key"] in active_keys]
            if not active_cells:
                row["is_hit"] = False
            else:
                hits = [c["hit_call"] == "hit" for c in active_cells]
                row["is_hit"] = any(hits) if q.filter_mode == "any" else all(hits)
            row["already_in_campaign"] = mid in in_campaign

        # Step 5 — hydrate molecules.
        mol_ids = list(rows_by_molecule.keys())
        molecules = await self._molecule_repo.find_by_ids(q.workspace_id, mol_ids)
        mol_lookup = {m.id: m for m in molecules}

        rows_response: list[dict[str, Any]] = []
        hits_count = non_hits_count = already_count = 0
        for mid, row in rows_by_molecule.items():
            mol = mol_lookup.get(mid)
            if mol is None:
                continue
            if row["already_in_campaign"]:
                already_count += 1
            if row["is_hit"]:
                hits_count += 1
            else:
                non_hits_count += 1
            smiles = mol.structure.smiles if mol.structure else None
            rows_response.append(
                {
                    "molecule": {
                        "id": str(mol.id),
                        "registration_number": mol.registration_number.value,
                        "name": mol.name,
                        "smiles": smiles,
                    },
                    "is_hit": row["is_hit"],
                    "already_in_campaign": row["already_in_campaign"],
                    "cells": row["cells"],
                }
            )

        return Success(
            {
                "summary": {
                    "runs": len(q.run_ids),
                    "channels_new": sum(1 for c in channels_meta if c["source"] == "new"),
                    "channels_reused": sum(1 for c in channels_meta if c["source"] == "reused"),
                    "molecules_total": len(rows_response),
                    "hits": hits_count,
                    "non_hits": non_hits_count,
                    "molecules_already_in_campaign": already_count,
                },
                "channels": channels_meta,
                "rows": rows_response,
            }
        )


def _nd_cell(channel_key: str) -> dict[str, Any]:
    return {
        "channel_key": channel_key,
        "value": None,
        "value_qualifier": ValueQualifier.ND.value,
        "unit": "-",
        "test_concentration_value": None,
        "test_concentration_unit": None,
        "replicate_count": 0,
        "qc_pass": None,
        "qc_reason": None,
        "hit_call": None,
        "source_run_id": None,
        "source_run_date": None,
        "protocol_name": None,
        "protocol_version": None,
        "contributing_run_ids": [],
    }


def _qc_pass(c: ResolvedCandidate) -> bool:
    """Default QC heuristic: run must be approved + z_prime, when present, >= 0.5."""
    if not c.run_approved:
        return False
    if c.z_prime is not None and c.z_prime < 0.5:
        return False
    return True


def _qc_reason(c: ResolvedCandidate) -> str | None:
    """Chemist-facing reason a candidate failed QC, or None if it passed.

    Returns the first failing condition only (run-approval beats z'). Used
    by preview cells to populate a tooltip on the destructive-by-default
    QC badge so chemists know whether to ignore the warning or chase it.
    """
    if not c.run_approved:
        return "Source run not approved"
    if c.z_prime is not None and c.z_prime < 0.5:
        return f"z' = {c.z_prime:.2f} (below 0.5)"
    return None


def _aggregate_qc_reason(candidates: list[ResolvedCandidate]) -> str | None:
    """Aggregate per-candidate QC reasons into one short summary.

    Single-candidate (LATEST_APPROVED_RUN): the candidate's reason directly.
    Multi-candidate (MEAN_ACROSS_RUNS, GEOMETRIC_MEAN): summarize as
    ``"{N}/{M} runs failed QC: {first reason}"`` so the chemist sees the
    scope without a wall of text.
    """
    if not candidates:
        return None
    reasons = [r for c in candidates if (r := _qc_reason(c)) is not None]
    if not reasons:
        return None
    if len(candidates) == 1:
        return reasons[0]
    return f"{len(reasons)}/{len(candidates)} runs failed QC: {reasons[0]}"
