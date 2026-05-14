"""AddResultsFromRuns — multi-run import with channel reuse + hit-criteria filter (B6).

Replaces the single-run ``AddResultsFromRun`` use case. The same pipeline now
accepts a list of run_ids plus per-readout ``ChannelImportConfig`` entries.
Either reuses an existing campaign channel (when ``(protocol_id, readout_def_id)``
already matches one) or creates a new one. Cells are computed by the same
``_compute_hit_call`` + selection-rule path that powers PreviewRunImport, so
the values committed match what the user saw in the preview.

Behavioral notes:
- DRAFT-only (campaign lock guard).
- ``scope='hits_only'`` filters molecules out at commit time per ``filter_mode``.
- ``default_decision`` controls the initial decision on NEW results only.
- ``refresh_existing_cells`` updates non-override cells for molecules already in
  the campaign; override cells are preserved (matches RefreshFromSources).
- Reusing a channel **applies the user's updated rule/threshold** to the
  channel record. Existing cells against that channel are NOT auto-refreshed
  (the screener can hit "Refresh from sources" if they want to).
- Snapshot fields populated on every new/updated measurement:
  ``replicate_count``, ``qc_pass``, ``contributing_run_ids``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.research_organization.add_results_from_collection import (
    AddResultsOutcome,
)
from cellar.application.research_organization.channel_resolution import (
    ChannelResolutionQuery,
    _compute_hit_call,
)
from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
    _apply_selection_rule,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    CampaignDecision,
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.research_organization.source_ref import RunRef
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class AddResultsFromRunsCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfig]
    filter_mode: Literal["any", "all"] = "all"
    scope: Literal["hits_only", "all"] = "hits_only"
    default_decision: CampaignDecision = CampaignDecision.SELECTED
    description: str | None = None
    refresh_existing_cells: bool = False


@dataclass
class AddFromRunsOutcome(AddResultsOutcome):
    """Extends the shared AddResultsOutcome with channel counts."""

    channels_created: int = 0
    channels_reused: int = 0


class AddResultsFromRuns:
    """Multi-run import: creates/reuses channels and adds filtered hits.

    Pipeline (inside one UoW):
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check.
      4. Resolve channels:
         - For each config, look up existing channel by
           ``(protocol_id, readout_definition_id)``.
         - If exists: apply updated selection_rule + hit_threshold.
         - If new: ``campaign.add_channel(...)``.
      5. For each (channel, run set): fetch per-molecule candidate lists.
      6. Apply selection_rule to pick a value per molecule; compute hit_call.
      7. Aggregate per-molecule cells; decide is_hit per filter_mode +
         active filter set (channels with ``use_for_filter=True`` AND a
         hit_threshold).
      8. ``scope == 'hits_only'`` drops non-hits.
      9. For new molecules: create CampaignResult with default_decision +
         RunRef attribution; ``campaign.add_results`` (idempotent).
     10. For each result × channel: persist a CampaignMeasurement carrying
         all snapshot fields.
     11. ``refresh_existing_cells=True`` updates non-override cells for
         already-in-campaign molecules.
     12. Save + commit + dispatch.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        run_repo: RunRepository,
        channel_query: ChannelResolutionQuery,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._run_repo = run_repo
        self._query = channel_query
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: AddResultsFromRunsCommand,
        auth: AuthContext | None = None,
    ) -> Result[AddFromRunsOutcome, DomainError]:
        require_editor(auth)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot add results: campaign is {campaign.status.value}")
                )

            if not input.run_ids:
                return Failure(ValidationError("At least one run_id is required"))
            if not input.channel_configs:
                return Failure(ValidationError("At least one channel_config is required"))

            # Step 1 — channel resolution: reuse or create.
            # Reuse key is (protocol, readout, normalization, intercept_key)
            # so a single readout can expose multiple distinct channels for
            # different intercepts (e.g. Resazurin EC50 + Resazurin EC90).
            # After Option A, the intercept_key lives on the channel /
            # config directly, not under hit_threshold — so a display-only
            # channel (no threshold) still keeps its intercept identity
            # and doesn't collide with the threshold-bearing primary.
            channels_created = 0
            channels_reused = 0
            # The intercept-key fourth element uses the frozen InterceptKey VO
            # directly (hashable by `@dataclass(frozen=True)`); None means
            # the channel targets the primary intercept.
            ChannelKey = tuple[uuid.UUID, uuid.UUID, str | None, object]

            channel_by_config: dict[ChannelKey, CampaignChannel] = {}
            existing_by_key: dict[ChannelKey, CampaignChannel] = {
                (
                    ch.protocol_id,
                    ch.readout_definition_id,
                    ch.normalization_applied,
                    ch.intercept_key,
                ): ch
                for ch in campaign.channels
            }
            next_display_order = (
                max((ch.display_order for ch in campaign.channels), default=-1) + 1
            )

            for cfg in input.channel_configs:
                norm = (
                    cfg.normalization_applied
                    if cfg.source_kind == ChannelSourceKind.READOUT_DATA
                    else None
                )
                key: ChannelKey = (
                    cfg.protocol_id,
                    cfg.readout_definition_id,
                    norm,
                    cfg.intercept_key,
                )
                existing = existing_by_key.get(key)
                if existing:
                    # Reuse — apply updated selection rule + threshold.
                    # Intercept identity is locked at creation; chemist
                    # editing the threshold doesn't move the channel.
                    existing.selection_rule = cfg.selection_rule
                    existing.hit_threshold = cfg.hit_threshold
                    channel_by_config[key] = existing
                    channels_reused += 1
                else:
                    new_ch = CampaignChannel(
                        campaign_id=campaign.id,
                        label=cfg.label,
                        protocol_id=cfg.protocol_id,
                        readout_definition_id=cfg.readout_definition_id,
                        source_kind=cfg.source_kind,
                        selection_rule=cfg.selection_rule,
                        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                        display_order=next_display_order,
                        hit_threshold=cfg.hit_threshold,
                        normalization_applied=norm,
                        intercept_key=cfg.intercept_key,
                    )
                    next_display_order += 1
                    try:
                        campaign.add_channel(new_ch)
                    except ValidationError as e:
                        return Failure(e)
                    channel_by_config[key] = new_ch
                    channels_created += 1

            # Step 2 — fetch candidates per channel
            cells_by_mol_channel: dict[
                tuple[uuid.UUID, uuid.UUID], _CellData
            ] = {}  # (molecule_id, channel_id) -> cell data
            active_channel_ids: set[uuid.UUID] = set()

            for cfg in input.channel_configs:
                norm = (
                    cfg.normalization_applied
                    if cfg.source_kind == ChannelSourceKind.READOUT_DATA
                    else None
                )
                key = (
                    cfg.protocol_id,
                    cfg.readout_definition_id,
                    norm,
                    cfg.intercept_key,
                )
                channel = channel_by_config[key]
                if cfg.use_for_filter and cfg.hit_threshold is not None:
                    active_channel_ids.add(channel.id)
                candidates_by_mol = await self._query.fetch_candidates_for_runs(
                    workspace_id=input.workspace_id,
                    run_ids=input.run_ids,
                    protocol_id=cfg.protocol_id,
                    readout_definition_id=cfg.readout_definition_id,
                    source_kind=cfg.source_kind,
                    normalization_applied=norm,
                )
                for mol_id, candidates in candidates_by_mol.items():
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
                        continue  # Skip ND cells — don't add a measurement
                    # picked.value IS the channel's intercept value (primary
                    # if intercept_key=None, intercept-specific otherwise);
                    # threshold compares directly against it.
                    hit = (
                        _compute_hit_call(picked.value, cfg.hit_threshold)
                        if cfg.hit_threshold
                        else None
                    )
                    qc_pass_all = all(_qc_pass(c) for c in candidates)
                    cells_by_mol_channel[(mol_id, channel.id)] = _CellData(
                        picked=picked,
                        hit_call_str=hit.value if hit else None,
                        qc_pass=qc_pass_all,
                    )

            # Step 3 — group cells by molecule, decide is_hit
            cells_by_mol: dict[uuid.UUID, dict[uuid.UUID, _CellData]] = {}
            for (mol_id, ch_id), cell in cells_by_mol_channel.items():
                cells_by_mol.setdefault(mol_id, {})[ch_id] = cell

            mol_is_hit: dict[uuid.UUID, bool] = {}
            for mol_id, ch_cells in cells_by_mol.items():
                active_hits = [
                    ch_cells[ch_id].hit_call_str == "hit"
                    for ch_id in ch_cells
                    if ch_id in active_channel_ids
                ]
                if not active_hits:
                    mol_is_hit[mol_id] = False
                else:
                    mol_is_hit[mol_id] = (
                        any(active_hits) if input.filter_mode == "any" else all(active_hits)
                    )

            # Step 4 — scope filter
            if input.scope == "hits_only":
                mols_to_add = {mid for mid, hit in mol_is_hit.items() if hit}
            else:
                mols_to_add = set(cells_by_mol.keys())

            # Step 5 — separate new vs already-in-campaign
            existing_mol_ids = {r.molecule_id for r in campaign.results}
            new_mols = mols_to_add - existing_mol_ids
            existing_mols_in_scope = mols_to_add & existing_mol_ids

            # Step 6 — build new CampaignResults
            source_ref_by_mol: dict[uuid.UUID, RunRef] = {}
            for mol_id in new_mols:
                # Pick the "first contributing run" — earliest by run_date
                # across all this molecule's cells.
                first_run_id: uuid.UUID | None = None
                earliest_date = None
                for ch_id, cell in cells_by_mol[mol_id].items():
                    if cell.picked.source_run_id is None:
                        continue
                    if (
                        earliest_date is None
                        or (cell.picked.run_date or datetime.max.date()) < earliest_date
                    ):
                        earliest_date = cell.picked.run_date
                        first_run_id = cell.picked.source_run_id
                if first_run_id is None and input.run_ids:
                    first_run_id = input.run_ids[0]
                source_ref_by_mol[mol_id] = RunRef(
                    run_id=first_run_id or input.run_ids[0],
                    description=input.description,
                )

            new_results = [
                CampaignResult(
                    campaign_id=campaign.id,
                    molecule_id=mol_id,
                    decision=input.default_decision,
                    added_from=source_ref_by_mol[mol_id],
                )
                for mol_id in new_mols
            ]

            try:
                added, _skipped = campaign.add_results(new_results)
            except ValidationError as e:
                return Failure(e)

            # Step 7 — persist measurements for newly added results
            mol_to_result_id: dict[uuid.UUID, uuid.UUID] = {
                r.molecule_id: r.id for r in campaign.results
            }

            for mol_id in new_mols:
                result_id = mol_to_result_id[mol_id]
                result = next(r for r in campaign.results if r.id == result_id)
                for ch_id, cell in cells_by_mol[mol_id].items():
                    m = _build_measurement(
                        result_id=result_id,
                        channel_id=ch_id,
                        cell=cell,
                    )
                    result.add_measurement(m)

            # Step 8 — optionally refresh non-override cells for existing molecules
            refreshed_existing = 0
            if input.refresh_existing_cells:
                for mol_id in existing_mols_in_scope:
                    result_id = mol_to_result_id[mol_id]
                    result = next(r for r in campaign.results if r.id == result_id)
                    for ch_id, cell in cells_by_mol[mol_id].items():
                        old = result.find_measurement(ch_id)
                        if old is not None and old.is_manual_override:
                            continue  # preserve override
                        new_m = _build_measurement(
                            result_id=result_id,
                            channel_id=ch_id,
                            cell=cell,
                            preserve_id=old.id if old else None,
                        )
                        if old is not None:
                            result.remove_measurement_for_channel(ch_id)
                        result.add_measurement(new_m)
                        refreshed_existing += 1

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        outcome = AddFromRunsOutcome(
            campaign=campaign,
            added=added,
            skipped=len(mols_to_add) - added,
            channels_created=channels_created,
            channels_reused=channels_reused,
        )
        return Success(outcome)


@dataclass(frozen=True)
class _CellData:
    """Internal carrier — bundles a selection-rule pick with hit_call and qc_pass."""

    picked: object  # _Picked from preview_run_import
    hit_call_str: str | None
    qc_pass: bool


def _build_measurement(
    *,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    cell: _CellData,
    preserve_id: uuid.UUID | None = None,
) -> CampaignMeasurement:
    """Construct a CampaignMeasurement carrying every snapshot field."""
    picked = cell.picked
    from cellar.domain.research_organization.enums import HitCall

    hit_call: HitCall | None = None
    if cell.hit_call_str is not None:
        hit_call = HitCall(cell.hit_call_str)

    kwargs = dict(
        result_id=result_id,
        channel_id=channel_id,
        # Persisted value IS the channel's intercept value (primary if
        # no intercept_key, intercept-specific otherwise). Matches the
        # chemist's mental model: a channel "is for" EC90 → its
        # measurement value IS the EC90.
        value=picked.value,
        value_qualifier=picked.qualifier,
        unit=picked.unit,
        protocol_name_snapshot=picked.protocol_name,
        protocol_version_snapshot=picked.protocol_version,
        hit_call=hit_call,
        source_run_id=picked.source_run_id,
        source_curve_id=picked.source_curve_id,
        source_readout_id=picked.source_readout_id,
        run_date_snapshot=picked.run_date,
        replicate_count=picked.replicate_count,
        qc_pass=cell.qc_pass,
        contributing_run_ids=picked.contributing_run_ids,
        curve_snapshot=picked.curve_snapshot,
    )
    if preserve_id is not None:
        kwargs["id"] = preserve_id
    return CampaignMeasurement(**kwargs)


def _qc_pass(c) -> bool:
    """Default QC heuristic: run must be approved + z_prime, when present, >= 0.5."""
    if not c.run_approved:
        return False
    if c.z_prime is not None and c.z_prime < 0.5:
        return False
    return True
