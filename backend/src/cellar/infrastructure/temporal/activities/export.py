"""ExportActivities — Temporal activity that delegates to RenderExport.

A single ``run_export`` activity drives the full pipeline:
  row_stream → renderer → fsspec upload → job state transitions.

``RenderExport`` is injected at worker boot time so the activity class
is just a thin adapter — all business logic lives in the application layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from temporalio import activity

from cellar.application.export.render_export import RenderExport


@dataclass
class RunExportInput:
    job_id: str
    workspace_id: str


class ExportActivities:
    def __init__(self, render_export: RenderExport) -> None:
        self._run = render_export

    @activity.defn
    async def run_export(self, input: RunExportInput) -> None:
        await self._run(uuid.UUID(input.job_id), uuid.UUID(input.workspace_id))
