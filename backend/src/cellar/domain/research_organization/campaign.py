"""Campaign aggregate root — research_organization context.

Owns CampaignChannel[], CampaignResult[] (and CampaignMeasurement[] via results).
Lifecycle: draft -> closed -> superseded.

Campaigns are curated workspaces. Compounds are added incrementally via
add_results (bulk) or add_result (single). Each CampaignResult carries its
own ``added_from: SourceRef | None`` attribution. No compound_source on the
aggregate — provenance is per-row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import (
    MAX_STAGE_CRITERIA,
    UNSET,
    CampaignStage,
    StageCriterion,
    normalize_stage_name,
)
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.events import (
    CampaignClosed,
    CampaignCreated,
    CampaignSuperseded,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError


class Campaign(AggregateRoot):
    """A curated, immutable per-compound result snapshot.

    Owns channels and results (results own their measurements).
    Lifecycle: draft -> closed -> superseded. Closed and superseded
    campaigns reject all mutating operations on the aggregate.

    Empty campaigns (no results) are first-class — valid until close, which
    requires at least one result and one channel.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str | None = None,
        status: CampaignStatus = CampaignStatus.DRAFT,
        publishes_collection: bool = True,
        source_protocols: list[dict[str, Any]] | None = None,
        closed_at: datetime | None = None,
        closed_by: uuid.UUID | None = None,
        signature_id: uuid.UUID | None = None,
        supersedes_campaign_id: uuid.UUID | None = None,
        superseded_by_campaign_id: uuid.UUID | None = None,
        published_collection_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
        channels: list[CampaignChannel] | None = None,
        results: list[CampaignResult] | None = None,
        stages: list[CampaignStage] | None = None,
        close_note: str | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Campaign.name must not be empty")
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.name = name.strip()
        self.description = description
        self.status = status
        self.publishes_collection = publishes_collection
        self.source_protocols: list[dict[str, Any]] = source_protocols or []
        self.closed_at = closed_at
        self.closed_by = closed_by
        self.signature_id = signature_id
        self.supersedes_campaign_id = supersedes_campaign_id
        self.superseded_by_campaign_id = superseded_by_campaign_id
        self.published_collection_id = published_collection_id
        self.created_by = created_by
        self.channels: list[CampaignChannel] = channels or []
        self.results: list[CampaignResult] = results or []
        self.stages: list[CampaignStage] = stages or []
        self.close_note = close_note

    # ----- factory -----

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str | None,
        publishes_collection: bool,
        created_by: uuid.UUID,
        supersedes_campaign_id: uuid.UUID | None = None,
    ) -> Campaign:
        c = cls(
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            description=description,
            publishes_collection=publishes_collection,
            supersedes_campaign_id=supersedes_campaign_id,
            created_by=created_by,
        )
        c.register_event(
            CampaignCreated(
                aggregate_id=c.id,
                aggregate_type="Campaign",
                workspace_id=workspace_id,
                project_id=project_id,
                name=c.name,
            )
        )
        return c

    # ----- mutation guards -----

    def _ensure_draft(self, action: str) -> None:
        if self.status != CampaignStatus.DRAFT:
            raise ValidationError(f"Cannot {action}: campaign is {self.status.value}")

    # ----- channels -----

    def add_channel(self, channel: CampaignChannel) -> None:
        self._ensure_draft("add channel")
        if channel.campaign_id != self.id:
            raise ValidationError(
                f"channel.campaign_id ({channel.campaign_id}) does not match "
                f"Campaign.id ({self.id})"
            )
        if any(c.id == channel.id for c in self.channels):
            raise ValidationError(f"Channel {channel.id} already on campaign")
        self.channels.append(channel)
        self.updated_at = datetime.now(UTC)

    def remove_channel(self, channel_id: uuid.UUID) -> None:
        self._ensure_draft("remove channel")
        self.channels = [c for c in self.channels if c.id != channel_id]
        for r in self.results:
            r.remove_measurement_for_channel(channel_id)
        for stage in self.stages:
            stage.criteria = [c for c in stage.criteria if c.channel_id != channel_id]
        self.updated_at = datetime.now(UTC)

    # ----- results -----

    def add_result(self, result: CampaignResult) -> None:
        self._ensure_draft("add result")
        if result.campaign_id != self.id:
            raise ValidationError(
                f"result.campaign_id ({result.campaign_id}) does not match Campaign.id ({self.id})"
            )
        if any(r.molecule_id == result.molecule_id for r in self.results):
            raise ValidationError(f"Campaign already contains molecule {result.molecule_id}")
        self.results.append(result)
        self.updated_at = datetime.now(UTC)

    def remove_result_by_molecule(self, molecule_id: uuid.UUID) -> None:
        self._ensure_draft("remove result")
        self.results = [r for r in self.results if r.molecule_id != molecule_id]
        self.updated_at = datetime.now(UTC)

    def add_results(self, results: list[CampaignResult]) -> tuple[int, int]:
        """Bulk add. Idempotent on (campaign_id, molecule_id).

        Returns (added_count, skipped_count). Existing rows are not touched.
        Raises ValidationError if any result's campaign_id doesn't match self.id.
        """
        self._ensure_draft("add results")
        existing_molecule_ids = {r.molecule_id for r in self.results}
        added = 0
        skipped = 0
        for r in results:
            if r.campaign_id != self.id:
                raise ValidationError("result.campaign_id mismatch")
            if r.molecule_id in existing_molecule_ids:
                skipped += 1
                continue
            self.results.append(r)
            existing_molecule_ids.add(r.molecule_id)
            added += 1
        if added > 0:
            self.updated_at = datetime.now(UTC)
        return added, skipped

    # ----- stages -----

    def find_stage(self, stage_id: uuid.UUID) -> CampaignStage | None:
        for s in self.stages:
            if s.id == stage_id:
                return s
        return None

    def _check_stage_name_available(
        self, name: str, *, exclude_stage_id: uuid.UUID | None
    ) -> None:
        normalized = name.casefold()
        for other in self.stages:
            if other.id == exclude_stage_id:
                continue
            if other.name.casefold() == normalized:
                raise ValidationError(f"CampaignStage name '{name}' already used on this campaign")

    def _check_stage_parent(
        self, parent_stage_id: uuid.UUID | None, *, stage_id: uuid.UUID
    ) -> None:
        if parent_stage_id is None:
            return
        if parent_stage_id == stage_id:
            raise ValidationError("CampaignStage cannot be its own parent")
        parent = self.find_stage(parent_stage_id)
        if parent is None:
            raise ValidationError(
                f"CampaignStage parent {parent_stage_id} not found on this campaign"
            )
        # Walk the parent chain upward from the proposed parent; if it leads
        # back to stage_id, attaching here would create a cycle.
        current: CampaignStage | None = parent
        while current is not None:
            if current.id == stage_id:
                raise ValidationError("stage parent would create a cycle")
            current = self.find_stage(current.parent_stage_id) if current.parent_stage_id else None

    def _check_stage_criteria_channels(self, criteria: list[StageCriterion]) -> None:
        channel_ids = {c.id for c in self.channels}
        for criterion in criteria:
            if criterion.channel_id not in channel_ids:
                raise ValidationError(
                    f"StageCriterion channel {criterion.channel_id} is not a channel "
                    "of this campaign"
                )

    def add_stage(self, stage: CampaignStage) -> None:
        self._ensure_draft("add stage")
        if stage.campaign_id != self.id:
            raise ValidationError(
                f"stage.campaign_id ({stage.campaign_id}) does not match Campaign.id ({self.id})"
            )
        if any(s.id == stage.id for s in self.stages):
            raise ValidationError(f"CampaignStage {stage.id} already on campaign")
        self._check_stage_name_available(stage.name, exclude_stage_id=None)
        self._check_stage_parent(stage.parent_stage_id, stage_id=stage.id)
        self._check_stage_criteria_channels(stage.criteria)
        self.stages.append(stage)
        self.updated_at = datetime.now(UTC)

    def update_stage(
        self,
        stage_id: uuid.UUID,
        *,
        name: str | object = UNSET,
        parent_stage_id: uuid.UUID | object | None = UNSET,
        criteria: list[StageCriterion] | object = UNSET,
        display_order: int | object = UNSET,
    ) -> CampaignStage:
        """Update a stage's mutable fields. `criteria` is replaced whole — never
        patched per item. Unsupplied (UNSET) fields are left as-is; `None` is a
        meaningful value only for `parent_stage_id` (clears it)."""
        self._ensure_draft("update stage")
        stage = self.find_stage(stage_id)
        if stage is None:
            raise NotFoundError("CampaignStage", str(stage_id))

        new_name = stage.name if name is UNSET else normalize_stage_name(name)  # type: ignore[arg-type]
        new_parent = stage.parent_stage_id if parent_stage_id is UNSET else parent_stage_id
        new_criteria = stage.criteria if criteria is UNSET else criteria
        new_display_order = stage.display_order if display_order is UNSET else display_order

        if new_display_order < 0:  # type: ignore[operator]
            raise ValidationError("CampaignStage.display_order must be >= 0")
        if len(new_criteria) > MAX_STAGE_CRITERIA:  # type: ignore[arg-type]
            raise ValidationError(
                f"Maximum {MAX_STAGE_CRITERIA} stage criteria allowed, got {len(new_criteria)}"  # type: ignore[arg-type]
            )
        self._check_stage_name_available(new_name, exclude_stage_id=stage.id)
        self._check_stage_parent(new_parent, stage_id=stage.id)  # type: ignore[arg-type]
        self._check_stage_criteria_channels(new_criteria)  # type: ignore[arg-type]

        stage.name = new_name
        stage.parent_stage_id = new_parent  # type: ignore[assignment]
        stage.criteria = new_criteria  # type: ignore[assignment]
        stage.display_order = new_display_order  # type: ignore[assignment]
        self.updated_at = datetime.now(UTC)
        return stage

    def remove_stage(self, stage_id: uuid.UUID) -> None:
        self._ensure_draft("remove stage")
        stage = self.find_stage(stage_id)
        if stage is None:
            raise NotFoundError("CampaignStage", str(stage_id))
        if any(s.parent_stage_id == stage_id for s in self.stages):
            raise ConflictError(f"CampaignStage {stage_id} has child stages; remove them first")
        self.stages = [s for s in self.stages if s.id != stage_id]
        for result in self.results:
            result.clear_stage_override(stage_id)
        self.updated_at = datetime.now(UTC)

    # ----- maintenance helpers -----

    def repair_placeholder_units(
        self,
        readout_unit_by_channel: dict[uuid.UUID, str],
    ) -> None:
        """Replace ``"-"`` placeholder units on non-override measurements.

        Used at close-time after re-resolution: if the resolver wrote a
        placeholder unit ("-") because the upstream source didn't carry
        one, swap in the protocol's readout-definition unit. Manual
        overrides are left alone.

        Parameters
        ----------
        readout_unit_by_channel
            Channel id -> resolved unit string. Channels with no mapping or
            an empty/whitespace unit are skipped.
        """
        for result in self.results:
            for channel in self.channels:
                measurement = result.find_measurement(channel.id)
                if measurement is None or measurement.is_manual_override:
                    continue
                if measurement.unit != "-":
                    continue
                unit = readout_unit_by_channel.get(channel.id)
                if not unit or not unit.strip():
                    continue
                measurement.unit = unit.strip()

    # ----- close / publish / supersede -----

    def close(
        self,
        *,
        closed_by: uuid.UUID,
        signature_id: uuid.UUID,
        source_protocols: list[dict[str, Any]],
    ) -> None:
        self._ensure_draft("close")
        if not self.results:
            raise ValidationError("Cannot close campaign with no results")
        if not self.channels:
            raise ValidationError("Cannot close campaign with no channels")
        self.status = CampaignStatus.CLOSED
        self.closed_at = datetime.now(UTC)
        self.closed_by = closed_by
        self.signature_id = signature_id
        self.source_protocols = source_protocols
        self.updated_at = self.closed_at
        self.register_event(
            CampaignClosed(
                aggregate_id=self.id,
                aggregate_type="Campaign",
                workspace_id=self.workspace_id,
                closed_by=closed_by,
                signature_id=signature_id,
            )
        )

    def set_published_collection(self, collection_id: uuid.UUID) -> None:
        if self.status != CampaignStatus.CLOSED:
            raise ValidationError("Published collection can only be set on closed campaigns")
        self.published_collection_id = collection_id

    def mark_superseded_by(self, new_campaign_id: uuid.UUID) -> None:
        if self.status != CampaignStatus.CLOSED:
            raise ValidationError(
                f"Only closed campaigns can be superseded — current status is {self.status.value}"
            )
        self.status = CampaignStatus.SUPERSEDED
        self.superseded_by_campaign_id = new_campaign_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CampaignSuperseded(
                aggregate_id=self.id,
                aggregate_type="Campaign",
                workspace_id=self.workspace_id,
                superseded_by_campaign_id=new_campaign_id,
            )
        )
