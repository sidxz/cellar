"""any_id_text matches ids written into JSON in any letter case."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.infrastructure.cascade.rules import any_id_text


async def test_an_uppercase_id_in_json_matches(db_session: AsyncSession) -> None:
    run_id = uuid.uuid4()
    doc = sa.cast(sa.literal(f'{{"run_id": "{str(run_id).upper()}"}}'), JSONB)
    stored = doc["run_id"].astext

    assert await db_session.scalar(sa.select(any_id_text(stored, [run_id]))) is True
    assert await db_session.scalar(sa.select(any_id_text(stored, [uuid.uuid4()]))) is False
