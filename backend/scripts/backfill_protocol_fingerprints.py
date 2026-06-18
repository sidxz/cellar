"""One-shot: compute fingerprints for protocols missing one. Idempotent.

Usage (from backend/):
    uv run python scripts/backfill_protocol_fingerprints.py

Re-saves each protocol with a NULL fingerprint so the repository's
compute_protocol_fingerprint call fires and persists the value.
Safe to run multiple times — protocols already having a fingerprint are skipped.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import ProtocolModel
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def main() -> None:
    settings = DatabaseSettings()  # type: ignore[call-arg]
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Collect all (id, workspace_id) pairs where fingerprint IS NULL
    async with AsyncSession(engine) as session:
        rows = (
            await session.execute(
                select(ProtocolModel.id, ProtocolModel.workspace_id).where(
                    ProtocolModel.fingerprint.is_(None)
                )
            )
        ).all()

    count = len(rows)
    print(f"found {count} protocol(s) with missing fingerprint")

    if count > 0:
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            repo = SQLAlchemyProtocolRepository(uow)
            for pid, ws in rows:
                p = await repo.find_by_id_in_workspace(ws, pid)
                if p is not None:
                    await repo.save(p)
            await uow.commit()

    await engine.dispose()
    print(f"backfilled {count} protocols")


if __name__ == "__main__":
    asyncio.run(main())
