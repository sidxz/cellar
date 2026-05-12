"""SourceRef — per-result attribution for campaign compound sourcing.

A CampaignResult carries its own ``added_from: SourceRef | None`` field.
``None`` means the result was added manually via ``AddResultRow`` without
an explicit attribution (equivalent to ``ManualRef``).

Discriminants:
- ``ManualRef``      — manual / one-at-a-time addition via AddResultRow.
- ``CollectionRef``  — pulled from a Collection's membership.
- ``SavedSearchRef`` — pulled from a SavedSearch execution (deferred).
- ``CampaignRef``    — pulled from another campaign's results filtered
                        by decision (draft / closed / superseded all OK).
- ``RunRef``         — pulled from a protocol run's molecule set.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cellar.domain.research_organization.enums import CampaignDecision
from cellar.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class SourceRef:
    """Base class for per-result source attribution. Use concrete subclasses."""

    kind: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SourceRef:
        kind = data.get("kind")
        if kind is None:
            raise ValidationError("SourceRef dict missing 'kind'")
        if kind == "manual":
            return ManualRef(description=data.get("description"))
        if kind == "collection":
            return CollectionRef(
                collection_id=uuid.UUID(data["collection_id"]), description=data.get("description")
            )
        if kind == "saved_search":
            return SavedSearchRef(
                saved_search_id=uuid.UUID(data["saved_search_id"]),
                description=data.get("description"),
            )
        if kind == "campaign":
            decisions = data.get("decision_filter") or ["selected"]
            return CampaignRef(
                campaign_id=uuid.UUID(data["campaign_id"]),
                decision_filter=[CampaignDecision(v) for v in decisions],
                description=data.get("description"),
            )
        if kind == "run":
            return RunRef(
                run_id=uuid.UUID(data["run_id"]),
                description=data.get("description"),
            )
        raise ValidationError(f"Unknown SourceRef kind: {kind!r}")


@dataclass(frozen=True)
class ManualRef(SourceRef):
    """No bulk source — compound added one-at-a-time via AddResultRow.

    In the DAIKON published view, manual results group as
    ``{"kind": "manual", "ref": {}, "count": N}``.
    """

    kind: ClassVar[str] = "manual"
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "description": self.description}


@dataclass(frozen=True)
class CollectionRef(SourceRef):
    """Result was pulled from a Collection's membership."""

    kind: ClassVar[str] = "collection"
    collection_id: uuid.UUID = None  # type: ignore[assignment]
    description: str | None = None

    def __post_init__(self) -> None:
        if self.collection_id is None:
            raise ValidationError("CollectionRef requires collection_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "collection_id": str(self.collection_id),
            "description": self.description,
        }


@dataclass(frozen=True)
class SavedSearchRef(SourceRef):
    """Result was pulled from a SavedSearch execution (deferred feature)."""

    kind: ClassVar[str] = "saved_search"
    saved_search_id: uuid.UUID = None  # type: ignore[assignment]
    description: str | None = None

    def __post_init__(self) -> None:
        if self.saved_search_id is None:
            raise ValidationError("SavedSearchRef requires saved_search_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "saved_search_id": str(self.saved_search_id),
            "description": self.description,
        }


@dataclass(frozen=True)
class CampaignRef(SourceRef):
    """Result was pulled from another campaign's results filtered by decision.

    Accepts any campaign status (draft / closed / superseded) — the
    curator decides what's valid.
    """

    kind: ClassVar[str] = "campaign"
    campaign_id: uuid.UUID = None  # type: ignore[assignment]
    decision_filter: list[CampaignDecision] = field(
        default_factory=lambda: [CampaignDecision.SELECTED]
    )
    description: str | None = None

    def __post_init__(self) -> None:
        if self.campaign_id is None:
            raise ValidationError("CampaignRef requires campaign_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "campaign_id": str(self.campaign_id),
            "decision_filter": [d.value for d in self.decision_filter],
            "description": self.description,
        }


@dataclass(frozen=True)
class RunRef(SourceRef):
    """Result was pulled from the molecule set of a protocol run."""

    kind: ClassVar[str] = "run"
    run_id: uuid.UUID = None  # type: ignore[assignment]
    description: str | None = None

    def __post_init__(self) -> None:
        if self.run_id is None:
            raise ValidationError("RunRef requires run_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "run_id": str(self.run_id),
            "description": self.description,
        }
