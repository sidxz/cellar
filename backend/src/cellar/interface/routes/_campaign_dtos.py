"""Shared Pydantic DTOs + serialization helpers for the Campaign routes.

Split out of ``campaigns.py`` so the lifecycle module + the per-group route
modules (channels, results, publishing) can import the same request/response
shapes without circular imports.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    SelectionRule,
)
from cellar.domain.research_organization.source_ref import ManualRef
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey


# ---------------------------------------------------------------------------
# DTOs — requests
# ---------------------------------------------------------------------------


class InterceptKeyDTO(BaseModel):
    kind: str  # "ec" | "ic"
    level: float  # (0, 100)

    def to_domain(self) -> InterceptKey:
        return InterceptKey(kind=self.kind, level=self.level)

    @classmethod
    def from_domain(cls, ik: InterceptKey) -> InterceptKeyDTO:
        return cls(kind=ik.kind, level=ik.level)


class HitCriterionDTO(BaseModel):
    readout_name: str
    operator: str
    # gt/lt/gte/lte → float; in → list[str]; between → list[float] (length 2).
    value: float | list[float] | list[str]
    #: Targets a specific dose-response intercept (e.g. EC90). ``None`` means
    #: "use the channel cell value as-is" — preserves legacy criteria, which
    #: for a DR channel equals the curve's primary fitted value.
    intercept_key: InterceptKeyDTO | None = None

    def to_domain(self) -> HitCriterion:
        return HitCriterion(
            readout_name=self.readout_name,
            operator=self.operator,
            value=self.value,
            intercept_key=self.intercept_key.to_domain() if self.intercept_key else None,
        )

    @classmethod
    def from_domain(cls, hc: HitCriterion) -> HitCriterionDTO:
        return cls(
            readout_name=hc.readout_name,
            operator=hc.operator,
            value=hc.value,
            intercept_key=(
                InterceptKeyDTO.from_domain(hc.intercept_key)
                if hc.intercept_key
                else None
            ),
        )


class CreateCampaignRequest(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID
    publishes_collection: bool = True
    supersedes_campaign_id: uuid.UUID | None = None


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


class AddFromCollectionRequest(BaseModel):
    collection_id: uuid.UUID
    description: str | None = None


class AddFromCampaignRequest(BaseModel):
    source_campaign_id: uuid.UUID
    decision_filter: list[str] = ["selected"]
    description: str | None = None


class ChannelImportConfigDTO(BaseModel):
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    label: str
    source_kind: str
    selection_rule: str
    hit_threshold: HitCriterionDTO | None = None
    use_for_filter: bool = True
    allowed_curve_classes: list[str] | None = None
    #: Normalization layer for ``readout_data`` source: None=raw,
    #: "percent_inhibition"=computed, etc. Ignored for dose-response curves.
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept (legacy behavior). Top-level field — not
    #: nested under hit_threshold — so display-only channels (no threshold)
    #: keep their intercept identity on the wire.
    intercept_key: InterceptKeyDTO | None = None

    def to_domain(self) -> ChannelImportConfig:
        return ChannelImportConfig(
            protocol_id=self.protocol_id,
            readout_definition_id=self.readout_definition_id,
            label=self.label,
            source_kind=ChannelSourceKind(self.source_kind),
            selection_rule=SelectionRule(self.selection_rule),
            hit_threshold=self.hit_threshold.to_domain() if self.hit_threshold else None,
            use_for_filter=self.use_for_filter,
            allowed_curve_classes=self.allowed_curve_classes,
            normalization_applied=self.normalization_applied,
            intercept_key=self.intercept_key.to_domain() if self.intercept_key else None,
        )


class PreviewRunImportRequest(BaseModel):
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfigDTO]
    filter_mode: str = "all"  # "any" | "all"


class AddFromRunsRequest(PreviewRunImportRequest):
    scope: str = "hits_only"  # "hits_only" | "all"
    default_decision: str = "selected"
    description: str | None = None
    refresh_existing_cells: bool = False


class AddChannelRequest(BaseModel):
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: str
    selection_rule: str
    qualifier_handling: str
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterionDTO | None = None
    display_order: int = 0
    #: Normalization layer for ``readout_data`` source. Ignored for dose-response.
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept. Set-on-create; ``UpdateChannelRequest``
    #: does not accept this field (a chemist wanting a different intercept
    #: creates a new channel).
    intercept_key: InterceptKeyDTO | None = None


class UpdateChannelRequest(BaseModel):
    """Partial update — omitted fields are not changed; null clears the value.

    The UC uses an UNSET sentinel to distinguish "omit" from None. We map
    Pydantic's model_fields_set to thread the sentinel through correctly.
    """

    label: str | None = None
    selection_rule: str | None = None
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterionDTO | None = None

    model_config = {"extra": "forbid"}


class SetResultDecisionRequest(BaseModel):
    decision: str
    reason: str | None = None
    notes: str | None = None

    model_config = {"extra": "forbid"}


class BulkSetResultDecisionsRequest(BaseModel):
    """Bulk-set decision for many CampaignResult rows in one transaction.

    ``result_ids`` is typically the frontend's currently-filtered subset so a
    chemist can "Mark all visible as Selected" / "Reject all non-hits" / etc.
    """

    result_ids: list[uuid.UUID]
    decision: str
    reason: str | None = None

    model_config = {"extra": "forbid"}


class OverrideCellRequest(BaseModel):
    value: float | None = None
    value_qualifier: str
    unit: str
    hit_call: str | None = None
    reason: str | None = None  # B8 — required when value differs from auto-resolved


class AddResultRowRequest(BaseModel):
    molecule_id: uuid.UUID


class CloseCampaignRequest(BaseModel):
    signature_id: uuid.UUID
    signature_meaning: str | None = None
    #: Override the campaign's stored publishes_collection at close time.
    #: None ⇒ keep the create-time value (default behaviour).
    publishes_collection: bool | None = None


class MirrorProtocolRequest(BaseModel):
    protocol_id: uuid.UUID


class MirrorProtocolOutcomeResponse(BaseModel):
    """Counts the bulk-create produced + the up-to-date campaign."""

    channels_created: int
    channels_skipped: int
    campaign: CampaignResponse


class SupersedeRequest(BaseModel):
    new_campaign_id: uuid.UUID


# ---------------------------------------------------------------------------
# DTOs — responses
# ---------------------------------------------------------------------------


class CampaignMeasurementResponse(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    value: float | None = None
    value_qualifier: str
    unit: str
    hit_call: str | None = None
    is_manual_override: bool
    source_run_id: uuid.UUID | None = None
    source_curve_id: uuid.UUID | None = None
    source_readout_id: uuid.UUID | None = None
    protocol_name_snapshot: str
    protocol_version_snapshot: int
    run_date_snapshot: str | None = None
    # Migration 029 — snapshot + audit fields (B6 + B8). Nullable for backwards
    # compat — existing closed campaigns serialize these as null.
    override_reason: str | None = None
    test_concentration_value: float | None = None
    test_concentration_unit: str | None = None
    replicate_count: int | None = None
    qc_pass: bool | None = None
    contributing_run_ids: list[uuid.UUID] | None = None
    # Migration 031 — frozen copy of the upstream dose-response curve.
    # Populated for source_kind=dose_response_curve cells; ReadoutData
    # cells serialize this as null.
    curve_snapshot: dict[str, Any] | None = None

    @classmethod
    def from_domain(cls, m: CampaignMeasurement) -> CampaignMeasurementResponse:
        return cls(
            id=m.id,
            channel_id=m.channel_id,
            value=m.value,
            value_qualifier=m.value_qualifier.value,
            unit=m.unit,
            hit_call=m.hit_call.value if m.hit_call is not None else None,
            is_manual_override=m.is_manual_override,
            source_run_id=m.source_run_id,
            source_curve_id=m.source_curve_id,
            source_readout_id=m.source_readout_id,
            protocol_name_snapshot=m.protocol_name_snapshot,
            protocol_version_snapshot=m.protocol_version_snapshot,
            run_date_snapshot=m.run_date_snapshot.isoformat()
            if m.run_date_snapshot is not None
            else None,
            override_reason=m.override_reason,
            test_concentration_value=m.test_concentration_value,
            test_concentration_unit=m.test_concentration_unit,
            replicate_count=m.replicate_count,
            qc_pass=m.qc_pass,
            contributing_run_ids=m.contributing_run_ids,
            curve_snapshot=m.curve_snapshot,
        )


class CampaignResultResponse(BaseModel):
    id: uuid.UUID
    molecule_id: uuid.UUID
    representative_batch_id: uuid.UUID | None = None
    decision: str
    decision_reason: str | None = None
    notes: str | None = None
    measurements: list[CampaignMeasurementResponse]

    @classmethod
    def from_domain(cls, r: CampaignResult) -> CampaignResultResponse:
        return cls(
            id=r.id,
            molecule_id=r.molecule_id,
            representative_batch_id=r.representative_batch_id,
            decision=r.decision.value,
            decision_reason=r.decision_reason,
            notes=r.notes,
            measurements=[CampaignMeasurementResponse.from_domain(m) for m in r.measurements],
        )


class CampaignChannelResponse(BaseModel):
    id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: str
    selection_rule: str
    qualifier_handling: str
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterionDTO | None = None
    display_order: int
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept (legacy single-intercept channels).
    intercept_key: InterceptKeyDTO | None = None

    @classmethod
    def from_domain(cls, ch: CampaignChannel) -> CampaignChannelResponse:
        return cls(
            id=ch.id,
            label=ch.label,
            protocol_id=ch.protocol_id,
            readout_definition_id=ch.readout_definition_id,
            source_kind=ch.source_kind.value,
            selection_rule=ch.selection_rule.value,
            qualifier_handling=ch.qualifier_handling.value,
            qc_filter=ch.qc_filter,
            hit_threshold=HitCriterionDTO.from_domain(ch.hit_threshold)
            if ch.hit_threshold is not None
            else None,
            display_order=ch.display_order,
            normalization_applied=ch.normalization_applied,
            intercept_key=InterceptKeyDTO.from_domain(ch.intercept_key)
            if ch.intercept_key is not None
            else None,
        )


def _derive_compound_sources(
    results: list[CampaignResult],
    scientist_by_run_id: dict[uuid.UUID, str] | None = None,
) -> list[dict[str, Any]]:
    """Derive compound_sources summary from per-result added_from attribution.

    Groups results by their source ref. Results with added_from=None are
    treated as ManualRef. Returns a list of {kind, ref, description, count}.

    When ``scientist_by_run_id`` is supplied, run-kind entries are decorated
    with the bench scientist name from the run's "Scientist" readout. The
    map is computed once per response in the GET handler (cheap one-shot
    query) rather than stored on the campaign aggregate, so it works
    retroactively on already-imported campaigns.
    """
    from collections import Counter

    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for r in results:
        ref = r.added_from if r.added_from is not None else ManualRef()
        d = ref.to_dict()
        key = (d.get("kind", "manual"), d.get("description"))
        if key not in groups:
            groups[key] = d
    # Count
    counts: Counter[tuple[str, str | None]] = Counter()
    for r in results:
        ref = r.added_from if r.added_from is not None else ManualRef()
        d = ref.to_dict()
        key = (d.get("kind", "manual"), d.get("description"))
        counts[key] += 1

    out: list[dict[str, Any]] = []
    for k in groups:
        entry = {**groups[k], "count": counts[k]}
        if entry.get("kind") == "run" and scientist_by_run_id is not None and entry.get("run_id"):
            try:
                rid = uuid.UUID(entry["run_id"])
            except (ValueError, TypeError):
                rid = None
            if rid is not None:
                name = scientist_by_run_id.get(rid)
                if name:
                    entry["scientist"] = name
        out.append(entry)
    return out


class CampaignResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    compound_sources: list[dict[str, Any]]
    publishes_collection: bool
    supersedes_campaign_id: uuid.UUID | None = None
    superseded_by_campaign_id: uuid.UUID | None = None
    published_collection_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    signature_id: uuid.UUID | None = None
    source_protocols: list[dict[str, Any]]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    version: int
    channels: list[CampaignChannelResponse]
    results: list[CampaignResultResponse]

    @classmethod
    def from_domain(
        cls,
        c: Campaign,
        scientist_by_run_id: dict[uuid.UUID, str] | None = None,
    ) -> CampaignResponse:
        return cls(
            id=c.id,
            workspace_id=c.workspace_id,
            project_id=c.project_id,
            name=c.name,
            description=c.description,
            status=c.status.value,
            compound_sources=_derive_compound_sources(c.results, scientist_by_run_id),
            publishes_collection=c.publishes_collection,
            supersedes_campaign_id=c.supersedes_campaign_id,
            superseded_by_campaign_id=c.superseded_by_campaign_id,
            published_collection_id=c.published_collection_id,
            closed_at=c.closed_at,
            closed_by=c.closed_by,
            signature_id=c.signature_id,
            source_protocols=c.source_protocols,
            created_by=c.created_by,
            created_at=c.created_at,
            updated_at=c.updated_at,
            version=c.version,
            channels=[CampaignChannelResponse.from_domain(ch) for ch in c.channels],
            results=[CampaignResultResponse.from_domain(r) for r in c.results],
        )


class AddResultsOutcomeResponse(BaseModel):
    added: int
    skipped: int
    campaign: CampaignResponse

    @classmethod
    def from_outcome(cls, outcome: Any) -> AddResultsOutcomeResponse:
        return cls(
            added=outcome.added,
            skipped=outcome.skipped,
            campaign=CampaignResponse.from_domain(outcome.campaign),
        )


class BulkSetResultDecisionsResponse(BaseModel):
    """Bulk-decision outcome: refreshed campaign + applied/missing counts."""

    campaign: CampaignResponse
    updated_count: int
    missing_ids: list[uuid.UUID]
