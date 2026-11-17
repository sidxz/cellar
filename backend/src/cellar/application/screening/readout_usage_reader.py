"""Port: what outside a protocol still uses its readouts.

The protocol sees its own references (formulas, dose-response axes, its recommended
hit rule; ``Protocol.readout_usage``). This port answers for the rest: stored values,
fitted curves, plate QC, assigned peaks, run hit rules, campaign columns, import
templates, saved searches, saved views and other protocols' formulas.

The concrete implementation lives in
``infrastructure.persistence.sqlalchemy.screening_assay.readout_usage_reader``.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from cellar.domain.screening_assay.protocol import ReadoutUsage


class ReadoutUsageReader(Protocol):
    async def for_readout(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, definition_id: uuid.UUID
    ) -> ReadoutUsage:
        """One readout's usage; unused when it is not the workspace's protocol's."""
        ...

    async def for_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> dict[uuid.UUID, ReadoutUsage]:
        """Usage of the protocol's readouts that are in use; the rest are absent."""
        ...
