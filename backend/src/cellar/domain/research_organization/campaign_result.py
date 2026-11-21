"""CampaignResult — one snapshot row per compound within a campaign.

Owns N CampaignMeasurements (one per channel). Triage lives entirely in
the stage funnel — see `stage_evaluation.evaluate_stages` and
``stage_overrides`` below; the only free-text field here is ``notes``, which
carries who last saved it and when (``set_notes``). A note can be saved on
any campaign status; earlier versions live in the audit trail.

``added_from`` records how the compound entered the campaign. It is
``None`` for results added manually via ``AddResultRow`` without explicit
attribution (treated as ManualRef in the published view). Immutable after
first write — only set at add time, never updated by reconciliation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_stage import StageOverride
from cellar.domain.research_organization.enums import StageOutcome
from cellar.domain.shared.errors import StaleEditError, ValidationError

if TYPE_CHECKING:
    from cellar.domain.research_organization.source_ref import SourceRef


def normalize_notes(text: str | None) -> str | None:
    """Trimmed text; blank means no note."""
    return (text or "").strip() or None


@dataclass(frozen=True)
class ResultNote:
    """A row's note with who saved it and when (both None when unknown)."""

    notes: str | None
    edited_by: uuid.UUID | None
    edited_at: datetime | None


class StaleNoteError(StaleEditError):
    """A save based on a note someone has since changed. Carries the current note."""

    def __init__(self, current: ResultNote) -> None:
        self.current = current
        super().__init__("Someone changed this note since you opened it. Your text was not saved.")

    def body_extras(self) -> dict[str, Any]:
        c = self.current
        return {
            # Keep the wire name every client already treats as "reload and redo".
            "error": "StaleEditError",
            "current": {
                "notes": c.notes,
                "notes_edited_by": str(c.edited_by) if c.edited_by else None,
                "notes_edited_at": c.edited_at.isoformat() if c.edited_at else None,
            },
        }


@dataclass
class CampaignResult:
    campaign_id: uuid.UUID
    molecule_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    representative_batch_id: uuid.UUID | None = None
    notes: str | None = None
    #: Who last saved ``notes`` and when; None for a note that predates tracking.
    notes_edited_by: uuid.UUID | None = None
    notes_edited_at: datetime | None = None
    added_from: SourceRef | None = None
    measurements: list[CampaignMeasurement] = field(default_factory=list)
    #: Manual per-(result, stage) hit/miss overrides, keyed by stage_id. See
    #: `stage_evaluation.evaluate_stages` for how these are combined with
    #: the computed verdict.
    stage_overrides: dict[uuid.UUID, StageOverride] = field(default_factory=dict)

    @property
    def note(self) -> ResultNote:
        return ResultNote(self.notes, self.notes_edited_by, self.notes_edited_at)

    def set_notes(
        self,
        notes: str | None,
        *,
        expected_notes: str | None,
        by: uuid.UUID,
        at: datetime,
    ) -> bool:
        """Save the note as ``by`` at ``at``; whether it changed.

        The same text as now changes nothing. Otherwise ``expected_notes`` (the
        note as the editor opened it) must still be the current note, or
        ``StaleNoteError`` — a colleague's newer note is never overwritten blind.
        """
        new = normalize_notes(notes)
        if new == self.notes:
            return False
        if normalize_notes(expected_notes) != self.notes:
            raise StaleNoteError(self.note)
        self.notes, self.notes_edited_by, self.notes_edited_at = new, by, at
        return True

    def add_measurement(self, m: CampaignMeasurement) -> None:
        if m.result_id != self.id:
            raise ValidationError(
                f"CampaignMeasurement.result_id ({m.result_id}) does not match "
                f"CampaignResult.id ({self.id})"
            )
        self.measurements.append(m)

    def remove_measurement_for_channel(self, channel_id: uuid.UUID) -> None:
        self.measurements = [m for m in self.measurements if m.channel_id != channel_id]

    def find_measurement(self, channel_id: uuid.UUID) -> CampaignMeasurement | None:
        for m in self.measurements:
            if m.channel_id == channel_id:
                return m
        return None

    def set_stage_override(
        self,
        *,
        stage_id: uuid.UUID,
        forced_outcome: StageOutcome,
        reason: str,
        overridden_by: uuid.UUID,
    ) -> StageOverride:
        """Force this stage's outcome for this result. Replaces any existing
        override for the same stage."""
        override = StageOverride(
            result_id=self.id,
            stage_id=stage_id,
            forced_outcome=forced_outcome,
            reason=reason,
            overridden_by=overridden_by,
            overridden_at=datetime.now(UTC),
        )
        self.stage_overrides[stage_id] = override
        return override

    def clear_stage_override(self, stage_id: uuid.UUID) -> bool:
        """Remove the override for `stage_id`, if any. Returns whether one was removed."""
        return self.stage_overrides.pop(stage_id, None) is not None
