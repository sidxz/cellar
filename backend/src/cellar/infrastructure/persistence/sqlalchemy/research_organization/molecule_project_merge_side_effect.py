"""MoleculeProjectMergeSideEffect — carry project membership across a molecule merge.

``molecule_projects`` rows of the merged-away (source) molecule move to the
survivor; otherwise a confirmed merge silently drops the compound from every
project it was registered to. If both are already in a project, the source row
is deleted first to avoid a composite-PK violation on re-point.

Mirrors :class:`MoleculeTagMergeSideEffect`.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.application.shared.unit_of_work import UnitOfWork


class MoleculeProjectMergeSideEffect:
    """Re-point molecule_projects rows from source to target molecule."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = uow.session  # type: ignore[attr-defined]
        params = {"source": source_molecule_id, "target": target_molecule_id}
        await session.execute(
            sa.text(
                "DELETE FROM molecule_projects mp1 "
                "WHERE mp1.molecule_id = :source "
                "AND EXISTS ("
                "SELECT 1 FROM molecule_projects mp2 "
                "WHERE mp2.project_id = mp1.project_id "
                "AND mp2.molecule_id = :target"
                ")"
            ),
            params,
        )
        await session.execute(
            sa.text(
                "UPDATE molecule_projects SET molecule_id = :target WHERE molecule_id = :source"
            ),
            params,
        )
