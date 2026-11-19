"""Migration 109: compound IDs are looked up case-insensitively, so the lookup has an index."""

from __future__ import annotations

import sqlalchemy as sa


async def test_case_insensitive_identifier_lookup_has_an_index(session_factory) -> None:
    async with session_factory() as session:
        indexdef = (
            await session.execute(
                sa.text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_molecule_identifiers_ws_lower_identifier'"
                )
            )
        ).scalar_one_or_none()

    assert indexdef is not None
    assert "molecule_identifiers" in indexdef
    assert "(workspace_id, lower((identifier)::text))" in indexdef
