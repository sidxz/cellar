"""Per-row inputs + outcomes for the BulkAddToCollection use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


class RowStatus(str, Enum):
    RESOLVED = "resolved"
    ALREADY_PRESENT = "already_present"
    UNREGISTERED = "unregistered"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass(frozen=True, kw_only=True)
class BulkAddRow:
    """One CSV row, after the FE has applied the chemist's column mapping."""

    row_index: int
    registration_number: str | None = None
    external_id: str | None = None
    inchi_key: str | None = None
    smiles: str | None = None
    name: str | None = None
    notes: str | None = None

    def has_identifier(self) -> bool:
        return any(
            (
                self.registration_number,
                self.external_id,
                self.inchi_key,
                self.smiles,
                self.name,
            )
        )


@dataclass(frozen=True, kw_only=True)
class RowOutcome:
    row_index: int
    status: RowStatus
    molecule_id: uuid.UUID | None = None
    molecule_name: str | None = None
    candidates: tuple[uuid.UUID, ...] = ()
    message: str | None = None


@dataclass(frozen=True, kw_only=True)
class BulkAddResult:
    outcomes: list[RowOutcome]
    resolved_count: int
    already_present_count: int
    unregistered_count: int
    ambiguous_count: int
    error_count: int
    preview_id: uuid.UUID | None = None

    @classmethod
    def from_outcomes(
        cls,
        outcomes: list[RowOutcome],
        *,
        preview_id: uuid.UUID | None = None,
    ) -> BulkAddResult:
        counts = {s: 0 for s in RowStatus}
        for o in outcomes:
            counts[o.status] += 1
        return cls(
            outcomes=outcomes,
            resolved_count=counts[RowStatus.RESOLVED],
            already_present_count=counts[RowStatus.ALREADY_PRESENT],
            unregistered_count=counts[RowStatus.UNREGISTERED],
            ambiguous_count=counts[RowStatus.AMBIGUOUS],
            error_count=counts[RowStatus.ERROR],
            preview_id=preview_id,
        )
