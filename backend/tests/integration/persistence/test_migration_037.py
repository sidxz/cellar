"""Integration test: migration 037 — bemis_murcko_smiles on molecule."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_molecule_has_bemis_murcko_smiles_column(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {c["name"]: c for c in inspect(sync_conn).get_columns("molecules")}
        )
    assert "bemis_murcko_smiles" in cols
    assert cols["bemis_murcko_smiles"]["nullable"] is True
    assert str(cols["bemis_murcko_smiles"]["type"]).upper().startswith("TEXT")
