"""Integration tests: ProtocolRepository.list_distinct_values."""
from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _make(ws: uuid.UUID, name: str, readouts: list[str], category: str | None = None) -> Protocol:
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws,
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        category=category,
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in readouts
        ],
    )


async def test_list_distinct_readout_names_ranked_by_similarity(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(_make(ws, "P1", ["% Inhibition", "IC50"]))
        await repo.save(_make(ws, "P2", ["% Inhibition", "Tm"]))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        all_names = await repo.list_distinct_values(ws, field="readout_name", q=None, limit=10)
        assert "% Inhibition" in all_names
        assert "IC50" in all_names
        ic = await repo.list_distinct_values(ws, field="readout_name", q="ic5", limit=10)
        assert ic and ic[0] == "IC50"


async def test_list_distinct_categories(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(_make(ws, "P1", ["IC50"], category="Enzyme"))
        await repo.save(_make(ws, "P2", ["IC50"], category="Whole Cell"))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        cats = await repo.list_distinct_values(ws, field="category", q=None, limit=10)
        assert set(cats) == {"Enzyme", "Whole Cell"}


async def test_list_distinct_values_is_workspace_scoped(uow: AsyncUnitOfWork) -> None:
    ws1 = uuid.uuid4()
    ws2 = uuid.uuid4()
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(_make(ws1, "P1", ["IC50 ws1"]))
        await repo.save(_make(ws2, "P2", ["Tm ws2"]))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        names1 = await repo.list_distinct_values(ws1, field="readout_name", q=None, limit=20)
    assert "IC50 ws1" in names1
    assert "Tm ws2" not in names1
