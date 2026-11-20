"""Each similarity mode ranks through the search reader: the query itself first, at 1.0.

Goes through ``SQLAlchemyMoleculeReader.ranked_ids_by_query`` — the composer's WHERE
clause plus the reader's score column — so the stored fingerprint columns
(``morgan_bfp`` from Python bytes, ``fcfp_bfp`` from the cartridge trigger) are compared
with query vectors built the way production builds them.
"""

from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)
from tests.integration import _screening_seed as seed

from .conftest import _make_molecule_model

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def corpus(uow, workspace_id) -> dict[uuid.UUID, str]:  # type: ignore[no-untyped-def]
    """Ethanol, isopropanol, benzene, committed so the reader's own session sees them."""
    async with uow:
        org = await seed.org(uow.session, workspace_id)
        models = [
            _make_molecule_model(workspace_id, org, smiles=smiles, name=name)
            for name, smiles in (
                ("ethanol", "CCO"),
                ("isopropanol", "CC(C)O"),
                ("benzene", "c1ccccc1"),
            )
        ]
        uow.session.add_all(models)
        await uow.commit()
    return {m.id: m.name for m in models}


async def _ranked(session_factory, workspace_id, corpus, mode: str) -> list[tuple[str, float]]:  # type: ignore[no-untyped-def]
    """(name, score) most similar first, for an ethanol query with no cutoff."""
    criterion = {"type": "structure", "kind": "similarity", "smiles": "CCO", "mode": mode}
    query = {"logic": "and", "criteria": [{**criterion, "threshold": 0.0}]}
    ranked = await SQLAlchemyMoleculeReader(session_factory).ranked_ids_by_query(
        workspace_id, query
    )
    return [(corpus[i], score) for i, score in ranked]


@pytest.mark.parametrize("mode", ["similar", "scaffold_hop", "fragment_in_target"])
async def test_the_query_itself_ranks_first_at_one(
    session_factory, workspace_id, corpus, mode
) -> None:
    ranked = await _ranked(session_factory, workspace_id, corpus, mode)

    assert {name for name, _ in ranked} == {"ethanol", "isopropanol", "benzene"}
    assert ranked[0] == ("ethanol", pytest.approx(1.0, abs=1e-6))
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("mode", ["similar", "fragment_in_target"])
async def test_an_aliphatic_analogue_outranks_an_unrelated_ring(
    session_factory, workspace_id, corpus, mode
) -> None:
    scores = dict(await _ranked(session_factory, workspace_id, corpus, mode))

    assert scores["isopropanol"] > scores["benzene"]
