"""Run-scoped candidate port of add-from-runs and its preview.

What is left of the per-cell channel resolution: every other campaign value is
written by ``recompute_columns`` through ``column_resolution.ColumnResolver``.
Add-from-runs and preview still read through this port until they move onto
the column resolver too. The SQL implementation lives in
``cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query``.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.application.screening.run_aggregation import ResolvedRun
from cellar.domain.research_organization.enums import ChannelSourceKind

# Back-compat alias — channel_resolution callers still type ResolvedCandidate.
# Remove in a follow-up commit once consumers migrate.
ResolvedCandidate = ResolvedRun


@runtime_checkable
class ChannelResolutionQuery(Protocol):
    """Port: the raw candidate rows of a set of runs, per molecule."""

    async def fetch_candidates_for_runs(
        self,
        *,
        workspace_id: uuid.UUID,
        run_ids: list[uuid.UUID],
        protocol_id: uuid.UUID,
        readout_definition_id: uuid.UUID,
        source_kind: ChannelSourceKind,
        normalization_applied: str | None = None,
    ) -> dict[uuid.UUID, list[ResolvedCandidate]]:
        """Per-molecule candidates restricted to a specific set of runs.

        Used by PreviewRunImport / AddResultsFromRuns to enumerate all molecules
        tested in the selected runs for a given (protocol, readout) pair.
        ``normalization_applied`` filters readout_data rows by their formula
        layer (None = raw; "percent_inhibition" = computed); ignored for
        dose-response curve channels. Returns
        ``dict[molecule_id, list[ResolvedCandidate]]``.
        """
        ...

    async def fetch_endpoint_candidates_for_runs(
        self,
        *,
        workspace_id: uuid.UUID,
        run_ids: list[uuid.UUID],
        readout_definition_id: uuid.UUID,
        normalization_applied: str | None = None,
        wellless_only: bool = False,
    ) -> dict[uuid.UUID, list[ResolvedCandidate]]:
        """``readout_data`` rows of the runs for one readout definition.

        ``wellless_only`` keeps only rows with no ``well_id``: the dose-response
        reported-endpoint fallback (D1), so per-well response readings on the
        same definition never average into a fake endpoint. Also the READOUT_DATA implementation of
        :meth:`fetch_candidates_for_runs`. The readout definition already pins
        the protocol, so no ``protocol_id`` is taken. Returns
        ``dict[molecule_id, list[ResolvedCandidate]]``.
        """
        ...
