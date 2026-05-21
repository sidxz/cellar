"""resolve_batch_ref — single source of truth for batch identifier resolution.

Tries canonical batch_number first (the common case), then falls back to
external identifier (alias) lookup. Returns None on complete miss.

Every import path should use this instead of calling find_by_batch_number
directly, so external/foreign batch references resolve cleanly.
"""

from __future__ import annotations

import uuid

from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.repository import BatchRepository


async def resolve_batch_ref(
    repo: BatchRepository, workspace_id: uuid.UUID, ref: str
) -> Batch | None:
    """Resolve a batch reference string to a Batch aggregate.

    Order:
      1. find_by_batch_number(ws, ref) — canonical Cellar name
      2. find_by_external_identifier(ws, ref) — registered alias
      3. None
    """
    batch = await repo.find_by_batch_number(workspace_id, ref)
    if batch is not None:
        return batch
    return await repo.find_by_external_identifier(workspace_id, ref)
