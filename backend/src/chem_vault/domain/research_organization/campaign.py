"""Campaign aggregate root — research_organization context.

Owns CampaignChannel[], CampaignResult[] (and CampaignMeasurement[] via results).
Lifecycle: draft -> closed -> superseded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import CompoundSource
from chem_vault.domain.research_organization.enums import CampaignStatus
from chem_vault.domain.research_organization.events import (
    CampaignClosed,
    CampaignCreated,
    CampaignSuperseded,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError


class Campaign(AggregateRoot):
    """A curated, immutable per-compound result snapshot.

    Owns channels and results (results own their measurements).
    Lifecycle: draft -> closed -> superseded. Closed and superseded
    campaigns reject all mutating operations on the aggregate.
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
        compound_source: CompoundSource,
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
    ) -> None:
        super().__init__(
            id=id, created_at=created_at, updated_at=updated_at, version=version
        )
        if not name or not name.strip():
            raise ValidationError("Campaign.name must not be empty")
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.name = name.strip()
        self.description = description
        self.status = status
        self.compound_source = compound_source
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

    # ----- factory -----

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str | None,
        compound_source: CompoundSource,
        publishes_collection: bool,
        created_by: uuid.UUID,
        supersedes_campaign_id: uuid.UUID | None = None,
    ) -> Campaign:
        c = cls(
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            description=description,
            compound_source=compound_source,
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
            raise ValidationError(
                f"Cannot {action}: campaign is {self.status.value}"
            )

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
        self.updated_at = datetime.now(UTC)

    # ----- results -----

    def add_result(self, result: CampaignResult) -> None:
        self._ensure_draft("add result")
        if result.campaign_id != self.id:
            raise ValidationError(
                f"result.campaign_id ({result.campaign_id}) does not match "
                f"Campaign.id ({self.id})"
            )
        if any(r.molecule_id == result.molecule_id for r in self.results):
            raise ValidationError(
                f"Campaign already contains molecule {result.molecule_id}"
            )
        self.results.append(result)
        self.updated_at = datetime.now(UTC)

    def remove_result_by_molecule(self, molecule_id: uuid.UUID) -> None:
        self._ensure_draft("remove result")
        self.results = [r for r in self.results if r.molecule_id != molecule_id]
        self.updated_at = datetime.now(UTC)

    def reseed_results(self, results: list[CampaignResult]) -> None:
        self._ensure_draft("re-seed")
        for r in results:
            if r.campaign_id != self.id:
                raise ValidationError("result.campaign_id mismatch")
        self.results = list(results)
        self.updated_at = datetime.now(UTC)

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
            raise ValidationError(
                "Published collection can only be set on closed campaigns"
            )
        self.published_collection_id = collection_id

    def mark_superseded_by(self, new_campaign_id: uuid.UUID) -> None:
        if self.status != CampaignStatus.CLOSED:
            raise ValidationError(
                f"Only closed campaigns can be superseded — current status is "
                f"{self.status.value}"
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
