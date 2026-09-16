"""Read-model protocol for "which runs used this physical plate" (S15 §5.4).

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.inventory.plate_runs_reader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PlateRunRow:
    """One run plate linked to an inventory plate, joined to its run + protocol.

    Runs carry no name — ``run_date`` is their display identity (the run page
    titles itself ``Run {run_date}``), so it travels here typed, not as a string.
    """

    run_id: uuid.UUID
    run_date: date
    run_status: str
    protocol_id: uuid.UUID
    protocol_name: str
    plate_number: int
    created_at: datetime


@runtime_checkable
class PlateRunsReader(Protocol):
    """Application-layer protocol for the plate → runs read model."""

    async def runs_for_plate(
        self, workspace_id: uuid.UUID, plate_id: uuid.UUID
    ) -> list[PlateRunRow]: ...
