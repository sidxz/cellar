"""CollectionMergeSideEffect — re-point collection membership on molecule merge.

When two molecules are merged, any collection membership referencing the source
molecule must be moved to the target. If both already exist in the same
collection, the source row is deleted to avoid a unique constraint violation.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.application.shared.unit_of_work import UnitOfWork


class CollectionMergeSideEffect:
    """Re-point collection_molecules rows from source to target molecule."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = uow.session  # type: ignore[attr-defined]
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Step 1: DELETE rows where both source and target exist in the same
        # collection (dedup — avoids unique constraint violation on re-point).
        await session.execute(
            sa.text(
                "DELETE FROM collection_molecules cm1 "
                "WHERE cm1.molecule_id = :source "
                "AND EXISTS ("
                "SELECT 1 FROM collection_molecules cm2 "
                "WHERE cm2.collection_id = cm1.collection_id "
                "AND cm2.molecule_id = :target"
                ")"
            ),
            params,
        )

        # Step 2: UPDATE remaining source → target.
        await session.execute(
            sa.text(
                "UPDATE collection_molecules SET molecule_id = :target WHERE molecule_id = :source"
            ),
            params,
        )
