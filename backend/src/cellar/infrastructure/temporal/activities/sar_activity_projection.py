"""SarActivityProjectionActivities — Temporal activity delegating to
RunActivityProjection. The source (collection_id XOR molecule_ids) crosses the
boundary as strings; the channel spec crosses as a JSON dict."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

from cellar.application.sar_analysis.mark_activity_projection_failed import (
    MarkActivityProjectionFailed,
    MarkActivityProjectionFailedInput,
)
from cellar.application.sar_analysis.run_activity_projection import RunActivityProjection


@dataclass
class RunActivityProjectionInput:
    projection_id: str
    workspace_id: str
    channel_spec: dict[str, Any]
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


@dataclass
class MarkProjectionFailedInput:
    projection_id: str
    workspace_id: str
    error: str


class SarActivityProjectionActivities:
    def __init__(
        self,
        run_activity_projection: RunActivityProjection,
        mark_failed: MarkActivityProjectionFailed,
    ) -> None:
        self._run = run_activity_projection
        self._mark_failed = mark_failed

    @activity.defn
    async def run_sar_activity_projection(self, input: RunActivityProjectionInput) -> None:
        collection_id = uuid.UUID(input.collection_id) if input.collection_id else None
        molecule_ids = [uuid.UUID(m) for m in input.molecule_ids] if input.molecule_ids else None
        await self._run.run(
            run_id=uuid.UUID(input.projection_id),
            workspace_id=uuid.UUID(input.workspace_id),
            channel_spec=input.channel_spec,
            collection_id=collection_id,
            molecule_ids=molecule_ids,
        )

    @activity.defn
    async def mark_sar_activity_projection_failed(self, input: MarkProjectionFailedInput) -> None:
        # Invoked by the workflow once run retries are exhausted, so the row is
        # never left orphaned in RUNNING. Guarded + idempotent in the use case.
        await self._mark_failed.execute(
            MarkActivityProjectionFailedInput(
                projection_id=uuid.UUID(input.projection_id),
                workspace_id=uuid.UUID(input.workspace_id),
                error=input.error,
                now=datetime.now(UTC),
            )
        )
