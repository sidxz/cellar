"""qmol_from_smarts handles aromaticity perception across SMARTS dialects.

Originally this test wrapped the SMARTS in mol_adjust_query_properties per the
literature recommendation, but with this cartridge build that wrap silently
strips legitimate aromatic matches (e.g. benzene SMARTS hits 2/719 instead of
535/719 on a real corpus). qmol_from_smarts already produces the right query
mol for the @> operator path.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import _make_molecule_model


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query_text,description",
    [
        ("c1ccccc1", "lowercase aromatic SMARTS"),
        ("[c]1[c][c][c][c][c]1", "explicit aromatic-atom SMARTS"),
        ("[#6]1~[#6]~[#6]~[#6]~[#6]~[#6]~1", "atomic-number + any-bond SMARTS"),
    ],
)
async def test_three_benzene_smarts_all_match(
    query_text: str,
    description: str,
    db_session: AsyncSession,
    workspace_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """All three SMARTS forms of benzene must match the registered benzene."""
    benzene = _make_molecule_model(
        workspace_id, org_id, smiles="c1ccccc1", name="benzene",
    )
    db_session.add(benzene)
    await db_session.flush()

    result = await db_session.execute(
        text(
            "SELECT id FROM molecules WHERE workspace_id = :ws "
            "AND mol_from_smiles(smiles) @> qmol_from_smarts(:q)"
        ),
        {"ws": workspace_id, "q": query_text},
    )
    matched_ids = [row.id for row in result.all()]
    assert benzene.id in matched_ids, (
        f"SMARTS {query_text!r} ({description}) did not match benzene"
    )
