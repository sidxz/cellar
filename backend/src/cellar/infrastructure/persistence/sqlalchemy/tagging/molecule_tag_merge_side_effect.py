"""MoleculeTagMergeSideEffect — carry tag assignments across a molecule merge.

Tags live in the ``molecule_tags`` link table. When two molecules are merged,
the source's tag links must move to the target; otherwise the survivor silently
loses every tag the source carried (and the links are CASCADE-deleted with the
tombstone). If both molecules already carry the same tag, the source row is
deleted to avoid a composite-PK violation on re-point.

Mirrors :class:`CollectionMergeSideEffect`.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.application.shared.unit_of_work import UnitOfWork


class MoleculeTagMergeSideEffect:
    """Re-point molecule_tags rows from source to target molecule."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = uow.session  # type: ignore[attr-defined]
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Step 1: DELETE source links for tags the target already carries
        # (dedup — avoids a composite-PK violation on re-point).
        await session.execute(
            sa.text(
                "DELETE FROM molecule_tags mt1 "
                "WHERE mt1.molecule_id = :source "
                "AND EXISTS ("
                "SELECT 1 FROM molecule_tags mt2 "
                "WHERE mt2.molecule_id = :target "
                "AND mt2.tag_id = mt1.tag_id"
                ")"
            ),
            params,
        )

        # Step 2: UPDATE remaining source → target.
        await session.execute(
            sa.text(
                "UPDATE molecule_tags SET molecule_id = :target WHERE molecule_id = :source"
            ),
            params,
        )
