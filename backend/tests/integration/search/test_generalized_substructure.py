"""@>> with mol_to_xqmol matches tautomers that @> may miss.

Uses SMILES queries (not SMARTS) for the generalized path because mol_to_xqmol
accepts mol (from mol_from_smiles), enabling tautomer-aware matching via @>>.
Strict @> uses mol_from_smiles on both sides and does exact substructure.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import _make_molecule_model


@pytest.mark.asyncio
async def test_generalized_substructure_finds_tautomer(
    db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID,
) -> None:
    """Register the keto form (2-pyridone). Query with the enol form
    (2-hydroxypyridine) as SMILES. Strict @> misses; @>> with mol_to_xqmol finds it."""
    pyridone = _make_molecule_model(
        workspace_id, org_id,
        smiles="O=C1NC=CC=C1",
        name="2-pyridone",
    )
    db_session.add(pyridone)
    await db_session.flush()

    enol_smiles = "OC1=CC=CC=N1"

    # Generalized substructure (@>> + mol_to_xqmol) must find the keto tautomer.
    loose_result = await db_session.execute(
        text(
            "SELECT id FROM molecules WHERE workspace_id = :ws "
            "AND mol_from_smiles(smiles) @>> "
            "mol_to_xqmol(mol_from_smiles(:q))"
        ),
        {"ws": workspace_id, "q": enol_smiles},
    )
    loose_ids = [row.id for row in loose_result.all()]
    assert pyridone.id in loose_ids, (
        "Generalized substructure (@>> + mol_to_xqmol) must find the keto "
        "tautomer when queried with the enol SMILES form"
    )

    # Strict substructure (@>) must miss the tautomer (the two forms are structurally
    # distinct: keto has C=O + N-H; enol has O-H + C=N).
    strict_result = await db_session.execute(
        text(
            "SELECT id FROM molecules WHERE workspace_id = :ws "
            "AND mol_from_smiles(smiles) @> "
            "mol_from_smiles(:q)"
        ),
        {"ws": workspace_id, "q": enol_smiles},
    )
    strict_ids = [row.id for row in strict_result.all()]
    assert pyridone.id not in strict_ids, (
        "Strict substructure (@>) must NOT match the keto form via the enol SMILES; "
        "they are structurally distinct"
    )

    # Invariant: generalized is always a superset of strict.
    for sid in strict_ids:
        assert sid in loose_ids, (
            "Generalized substructure must be a superset of strict matches"
        )
