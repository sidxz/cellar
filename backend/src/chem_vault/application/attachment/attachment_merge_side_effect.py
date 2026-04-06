"""AttachmentMergeSideEffect — re-point attachments on molecule merge.

When molecules are merged, attachments on the source must be moved to the
target. If a file with the same name already exists on the target, the
source attachment is deleted (dedup). Orphaned blobs are cleaned up
best-effort.
"""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.attachment.storage import StorageClient

logger = logging.getLogger(__name__)


class AttachmentMergeSideEffect:
    """Re-point attachment rows from source to target molecule."""

    def __init__(self, storage: StorageClient) -> None:
        self._storage = storage

    async def on_merge(
        self,
        session: AsyncSession,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Step 1: Find storage keys for attachments that will be deduped
        result = await session.execute(
            sa.text(
                "SELECT a1.storage_key FROM attachments a1 "
                "WHERE a1.attachable_id = :source "
                "AND a1.attachable_type = 'molecule' "
                "AND EXISTS ("
                "SELECT 1 FROM attachments a2 "
                "WHERE a2.attachable_id = :target "
                "AND a2.attachable_type = 'molecule' "
                "AND a2.workspace_id = a1.workspace_id "
                "AND a2.file_name = a1.file_name"
                ")"
            ),
            params,
        )
        orphaned_keys = [row[0] for row in result.fetchall()]

        # Step 2: DELETE duplicate attachment rows
        await session.execute(
            sa.text(
                "DELETE FROM attachments a1 "
                "WHERE a1.attachable_id = :source "
                "AND a1.attachable_type = 'molecule' "
                "AND EXISTS ("
                "SELECT 1 FROM attachments a2 "
                "WHERE a2.attachable_id = :target "
                "AND a2.attachable_type = 'molecule' "
                "AND a2.workspace_id = a1.workspace_id "
                "AND a2.file_name = a1.file_name"
                ")"
            ),
            params,
        )

        # Step 3: Re-point remaining source → target
        await session.execute(
            sa.text(
                "UPDATE attachments "
                "SET attachable_id = :target "
                "WHERE attachable_id = :source "
                "AND attachable_type = 'molecule'"
            ),
            params,
        )

        # Step 4: Best-effort blob cleanup
        for key in orphaned_keys:
            try:
                await self._storage.delete(key)
            except Exception:
                logger.warning("Failed to clean up orphaned blob: %s", key)
