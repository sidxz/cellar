"""Live collection-coverage read model.

Joins ``run_collections`` + ``readout_data`` (screening) with
``collection_molecules`` + ``collections`` (research-org). Read-only reporting;
the write side (collection membership) stays in research-org. Every query is
workspace-scoped on both the run and the collection. See
``docs/superpowers/specs/2026-06-07-run-collection-coverage-design.md`` §4.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select

from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    CollectionRef,
    EffectiveCollectionCoverage,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDataModel,
    RunModel,
    run_collections,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyCollectionCoverageQuery:
    """Implements ``CollectionCoverageReader`` against PostgreSQL."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def _collection_sizes(self, collection_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not collection_ids:
            return {}
        stmt = (
            select(CollectionMoleculeModel.collection_id, func.count())
            .where(CollectionMoleculeModel.collection_id.in_(collection_ids))
            .group_by(CollectionMoleculeModel.collection_id)
        )
        rows = await self._uow.session.execute(stmt)
        return {row[0]: row[1] for row in rows.all()}

    async def run_coverage(
        self, workspace_id: uuid.UUID, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[CollectionCoverage]]:
        if not run_ids:
            return {}
        attach_stmt = (
            select(
                run_collections.c.run_id,
                CollectionModel.id,
                CollectionModel.name,
                CollectionModel.type,
            )
            .select_from(run_collections)
            .join(CollectionModel, CollectionModel.id == run_collections.c.collection_id)
            .where(
                run_collections.c.run_id.in_(run_ids),
                CollectionModel.workspace_id == workspace_id,
            )
        )
        attach_rows = (await self._uow.session.execute(attach_stmt)).all()

        covered_stmt = (
            select(
                run_collections.c.run_id,
                run_collections.c.collection_id,
                func.count(func.distinct(ReadoutDataModel.molecule_id)),
            )
            .select_from(run_collections)
            .join(
                ReadoutDataModel,
                and_(
                    ReadoutDataModel.run_id == run_collections.c.run_id,
                    ReadoutDataModel.molecule_id.is_not(None),
                ),
            )
            .join(
                CollectionMoleculeModel,
                and_(
                    CollectionMoleculeModel.collection_id == run_collections.c.collection_id,
                    CollectionMoleculeModel.molecule_id == ReadoutDataModel.molecule_id,
                ),
            )
            .where(run_collections.c.run_id.in_(run_ids))
            .group_by(run_collections.c.run_id, run_collections.c.collection_id)
        )
        covered = {
            (row[0], row[1]): row[2]
            for row in (await self._uow.session.execute(covered_stmt)).all()
        }
        sizes = await self._collection_sizes([r[1] for r in attach_rows])

        out: dict[uuid.UUID, list[CollectionCoverage]] = {}
        for run_id, cid, name, ctype in attach_rows:
            out.setdefault(run_id, []).append(
                CollectionCoverage(
                    ref=CollectionRef(id=cid, name=name, type=ctype),
                    covered=covered.get((run_id, cid), 0),
                    total=sizes.get(cid, 0),
                )
            )
        return out

    async def protocol_coverage(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> list[EffectiveCollectionCoverage]:
        attach_stmt = (
            select(
                CollectionModel.id,
                CollectionModel.name,
                CollectionModel.type,
                func.count(func.distinct(run_collections.c.run_id)),
            )
            .select_from(run_collections)
            .join(RunModel, RunModel.id == run_collections.c.run_id)
            .join(CollectionModel, CollectionModel.id == run_collections.c.collection_id)
            .where(
                RunModel.protocol_id == protocol_id,
                CollectionModel.workspace_id == workspace_id,
            )
            .group_by(CollectionModel.id, CollectionModel.name, CollectionModel.type)
        )
        attach_rows = (await self._uow.session.execute(attach_stmt)).all()
        if not attach_rows:
            return []

        covered_stmt = (
            select(
                run_collections.c.collection_id,
                func.count(func.distinct(ReadoutDataModel.molecule_id)),
            )
            .select_from(run_collections)
            .join(
                RunModel,
                and_(
                    RunModel.id == run_collections.c.run_id,
                    RunModel.protocol_id == protocol_id,
                ),
            )
            .join(
                ReadoutDataModel,
                and_(
                    ReadoutDataModel.run_id == run_collections.c.run_id,
                    ReadoutDataModel.molecule_id.is_not(None),
                ),
            )
            .join(
                CollectionMoleculeModel,
                and_(
                    CollectionMoleculeModel.collection_id == run_collections.c.collection_id,
                    CollectionMoleculeModel.molecule_id == ReadoutDataModel.molecule_id,
                ),
            )
            .group_by(run_collections.c.collection_id)
        )
        covered = {row[0]: row[1] for row in (await self._uow.session.execute(covered_stmt)).all()}
        sizes = await self._collection_sizes([r[0] for r in attach_rows])

        return [
            EffectiveCollectionCoverage(
                ref=CollectionRef(id=cid, name=name, type=ctype),
                covered=covered.get(cid, 0),
                total=sizes.get(cid, 0),
                run_count=run_count,
            )
            for cid, name, ctype, run_count in attach_rows
        ]

    async def run_gap(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        screened = (
            select(ReadoutDataModel.molecule_id)
            .where(
                ReadoutDataModel.run_id == run_id,
                ReadoutDataModel.molecule_id == CollectionMoleculeModel.molecule_id,
            )
            .exists()
        )
        stmt = (
            select(CollectionMoleculeModel.molecule_id)
            .join(CollectionModel, CollectionMoleculeModel.collection_id == CollectionModel.id)
            .where(
                CollectionMoleculeModel.collection_id == collection_id,
                CollectionModel.workspace_id == workspace_id,
                ~screened,
            )
            .order_by(CollectionMoleculeModel.added_at, CollectionMoleculeModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        rows = await self._uow.session.execute(stmt)
        return list(rows.scalars())

    async def protocol_gap(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        screened = (
            select(ReadoutDataModel.molecule_id)
            .select_from(ReadoutDataModel)
            .join(
                run_collections,
                and_(
                    run_collections.c.run_id == ReadoutDataModel.run_id,
                    run_collections.c.collection_id == collection_id,
                ),
            )
            .join(
                RunModel,
                and_(
                    RunModel.id == ReadoutDataModel.run_id,
                    RunModel.protocol_id == protocol_id,
                ),
            )
            .where(ReadoutDataModel.molecule_id == CollectionMoleculeModel.molecule_id)
            .exists()
        )
        stmt = (
            select(CollectionMoleculeModel.molecule_id)
            .join(CollectionModel, CollectionMoleculeModel.collection_id == CollectionModel.id)
            .where(
                CollectionMoleculeModel.collection_id == collection_id,
                CollectionModel.workspace_id == workspace_id,
                ~screened,
            )
            .order_by(CollectionMoleculeModel.added_at, CollectionMoleculeModel.molecule_id)
            .offset(offset)
            .limit(limit)
        )
        rows = await self._uow.session.execute(stmt)
        return list(rows.scalars())
