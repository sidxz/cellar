"""ProtocolRepository.find_usages — every reference that blocks a protocol delete."""

from __future__ import annotations

import json
import uuid
from datetime import date

import sqlalchemy as sa

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _draft(ws: uuid.UUID, name: str = "Onboarding draft") -> Protocol:
    return Protocol.create(
        workspace_id=ws,
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name="IC50", data_type=ReadoutDataType.NUMERIC
            )
        ],
    )


async def _usages(uow: AsyncUnitOfWork, ws: uuid.UUID, protocol_id: uuid.UUID) -> list[str]:
    async with uow:
        return await SQLAlchemyProtocolRepository(uow).find_usages(ws, protocol_id)


async def test_an_unused_draft_has_no_usages_and_deletes_cleanly(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    p = _draft(ws)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(p)
        await uow.commit()

    assert await _usages(uow, ws, p.id) == []

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.delete(ws, p.id)
        await uow.commit()
    async with uow:
        assert await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(ws, p.id) is None


async def test_every_blocking_reference_is_named(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    p = _draft(ws)
    child = _draft(ws, name="Onboarding draft v2")
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(p)
        await uow.commit()
    child.parent_protocol_id = p.id
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(child)
        await uow.commit()

    rd_id = p.readout_definitions[0].id
    campaign_id, seeded_id = uuid.uuid4(), uuid.uuid4()
    other_ws_campaign = uuid.uuid4()
    async with uow:
        s = uow.session
        for cid, cws, name, seeds in (
            (campaign_id, ws, "Test-2", []),
            (seeded_id, ws, "Seeded", [{"run_id": str(uuid.uuid4()), "protocol_id": str(p.id)}]),
            # Same protocol id referenced from another workspace must not leak in.
            (other_ws_campaign, uuid.uuid4(), "Elsewhere", []),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO campaign (id, workspace_id, project_id, name, created_by, "
                    "seed_runs) VALUES (:id, :ws, :proj, :name, :user, CAST(:seeds AS jsonb))"
                ),
                {
                    "id": cid,
                    "ws": cws,
                    "proj": uuid.uuid4(),
                    "name": name,
                    "user": uuid.uuid4(),
                    "seeds": json.dumps(seeds),
                },
            )
        for cid, label in ((campaign_id, "IC50"), (campaign_id, "IC90"), (other_ws_campaign, "X")):
            await s.execute(
                sa.text(
                    "INSERT INTO campaign_channel (id, campaign_id, label, protocol_id, "
                    "readout_definition_id, source_kind, selection_rule, qualifier_handling) "
                    "VALUES (:id, :cid, :label, :proto, :rd, 'readout_data', "
                    "'latest_approved_run', 'include_qualified')"
                ),
                {"id": uuid.uuid4(), "cid": cid, "label": label, "proto": p.id, "rd": rd_id},
            )
        await s.execute(
            sa.text(
                "INSERT INTO compound_flags (id, workspace_id, molecule_id, protocol_id, "
                "flagged_by, flag_type, created_at) "
                "VALUES (:id, :ws, :mol, :proto, :user, 'pains', now())"
            ),
            {"id": uuid.uuid4(), "ws": ws, "mol": uuid.uuid4(), "proto": p.id, "user": ws},
        )
        await s.execute(
            sa.text(
                "INSERT INTO import_templates (id, workspace_id, name, column_mappings, "
                "created_by, default_protocol_id) "
                "VALUES (:id, :ws, 'CRO sheet', '{}'::jsonb, :user, :proto)"
            ),
            {"id": uuid.uuid4(), "ws": ws, "user": uuid.uuid4(), "proto": p.id},
        )
        for _ in range(2):
            await s.execute(
                sa.text(
                    "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, "
                    "status, is_locked, version) "
                    "VALUES (:id, :ws, :proto, :d, :user, 'draft', false, 1)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": ws,
                    "proto": p.id,
                    "d": date(2026, 9, 15),
                    "user": uuid.uuid4(),
                },
            )
        await uow.commit()

    assert await _usages(uow, ws, p.id) == [
        'campaign "Test-2" (2 readouts)',
        'campaign "Seeded" (seeded from its runs)',
        'import template "CRO sheet"',
        'newer version "Onboarding draft v2"',
        "2 runs",
        "1 compound flag",
    ]
