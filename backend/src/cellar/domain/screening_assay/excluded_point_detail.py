"""Value object representing one entry in DoseResponseCurve.excluded_points.

The enriched JSONB shape (post-migration 041) carries audit metadata for both
user-driven exclusions and auto-detected outlier suggestions. Legacy entries
(written before Sprint 2) have idx=None and preserve concentration+response so
the chart can still render X markers; Sprint 2-era entries have idx set and
derive concentration/response from raw_data[idx] at render time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from cellar.domain.shared.errors import ValidationError


class ExclusionSource(StrEnum):
    MANUAL = "manual"
    AUTO_3SIGMA = "auto_3sigma"


class ExclusionReason(StrEnum):
    OUTLIER = "outlier"
    INSTRUMENT_ARTIFACT = "instrument_artifact"
    CONCENTRATION_ERROR = "concentration_error"
    CONTAMINATION = "contamination"
    QC_FAILURE = "qc_failure"
    OTHER = "other"
    AUTO_3SIGMA = "auto_3sigma"  # only valid when source == AUTO_3SIGMA


@dataclass(frozen=True)
class ExcludedPointDetail:
    """One entry in DoseResponseCurve.excluded_points.

    A "suggestion" (auto-detected but not yet acted on by a chemist) is
    modelled as ``source=AUTO_3SIGMA`` + ``excluded=False``. A confirmed
    exclusion has ``excluded=True``.
    """

    idx: int | None
    source: ExclusionSource
    excluded: bool
    reason: ExclusionReason
    author_id: uuid.UUID | None
    ts: datetime
    note: str | None = None
    concentration: float | None = None
    response: float | None = None

    def __post_init__(self) -> None:
        if self.source == ExclusionSource.MANUAL and self.author_id is None:
            raise ValidationError("author_id required for manual exclusions")
        if self.source == ExclusionSource.MANUAL and self.reason == ExclusionReason.AUTO_3SIGMA:
            raise ValidationError("AUTO_3SIGMA reason only valid for AUTO source")

    @property
    def is_suggestion(self) -> bool:
        """Auto-detected outlier that a chemist has not yet acted on."""
        return self.source == ExclusionSource.AUTO_3SIGMA and not self.excluded

    def to_jsonb(self) -> dict[str, Any]:
        return {
            "idx": self.idx,
            "concentration": self.concentration,
            "response": self.response,
            "source": self.source.value,
            "excluded": self.excluded,
            "reason": self.reason.value,
            "note": self.note,
            "author_id": str(self.author_id) if self.author_id else None,
            "ts": self.ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @classmethod
    def from_jsonb(cls, raw: dict[str, Any]) -> ExcludedPointDetail:
        ts_raw = raw["ts"]
        # Tolerate "...Z" suffix (UTC) and bare ISO-8601 forms alike.
        ts = datetime.fromisoformat(ts_raw.rstrip("Z")) if isinstance(ts_raw, str) else ts_raw
        return cls(
            idx=raw.get("idx"),
            source=ExclusionSource(raw["source"]),
            excluded=bool(raw["excluded"]),
            reason=ExclusionReason(raw["reason"]),
            note=raw.get("note"),
            author_id=uuid.UUID(raw["author_id"]) if raw.get("author_id") else None,
            ts=ts,
            concentration=raw.get("concentration"),
            response=raw.get("response"),
        )
