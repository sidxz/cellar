"""CompoundSource — discriminated value object for campaign seeding.

A Campaign is seeded with a list of compounds drawn from one of four
sources: an explicit list of molecule ids, a Collection's membership,
a SavedSearch's resolved result set, or the `selected` compounds of
another (closed) Campaign — the cascade arrow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class CompoundSource:
    """Base class for compound-source descriptors. Use concrete subclasses."""

    kind: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CompoundSource:
        kind = data.get("kind")
        if kind is None:
            raise ValidationError("CompoundSource dict missing 'kind'")
        if kind == "explicit_list":
            return ExplicitListSource(
                molecule_ids=[uuid.UUID(s) for s in data["molecule_ids"]]
            )
        if kind == "collection":
            return CollectionSource(collection_id=uuid.UUID(data["collection_id"]))
        if kind == "saved_search":
            return SavedSearchSource(
                saved_search_id=uuid.UUID(data["saved_search_id"])
            )
        if kind == "derived_from_campaign":
            decisions = data.get("decision_filter") or ["selected"]
            return DerivedFromCampaignSource(
                campaign_id=uuid.UUID(data["campaign_id"]),
                decision_filter=[CampaignDecision(v) for v in decisions],
            )
        raise ValidationError(f"Unknown CompoundSource kind: {kind!r}")


@dataclass(frozen=True)
class ExplicitListSource(CompoundSource):
    kind: ClassVar[str] = "explicit_list"
    molecule_ids: list[uuid.UUID] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.molecule_ids:
            raise ValidationError(
                "ExplicitListSource requires at least one molecule_id"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "molecule_ids": [str(m) for m in self.molecule_ids],
        }


@dataclass(frozen=True)
class CollectionSource(CompoundSource):
    kind: ClassVar[str] = "collection"
    collection_id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.collection_id is None:
            raise ValidationError("CollectionSource requires collection_id")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "collection_id": str(self.collection_id)}


@dataclass(frozen=True)
class SavedSearchSource(CompoundSource):
    kind: ClassVar[str] = "saved_search"
    saved_search_id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.saved_search_id is None:
            raise ValidationError("SavedSearchSource requires saved_search_id")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "saved_search_id": str(self.saved_search_id)}


@dataclass(frozen=True)
class DerivedFromCampaignSource(CompoundSource):
    """The cascade arrow: seed from another campaign's selected compounds."""

    kind: ClassVar[str] = "derived_from_campaign"
    campaign_id: uuid.UUID = None  # type: ignore[assignment]
    decision_filter: list[CampaignDecision] = field(
        default_factory=lambda: [CampaignDecision.SELECTED]
    )

    def __post_init__(self) -> None:
        if self.campaign_id is None:
            raise ValidationError(
                "DerivedFromCampaignSource requires campaign_id"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "campaign_id": str(self.campaign_id),
            "decision_filter": [d.value for d in self.decision_filter],
        }
