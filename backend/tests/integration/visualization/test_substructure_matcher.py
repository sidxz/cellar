"""SQLAlchemySubstructureMatcher against the real cartridge: Search's clause, workspace-scoped."""

from __future__ import annotations

import re
import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.visualization.substructure_matcher import (
    SQLAlchemySubstructureMatcher,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

KETCHER_BENZENE = "[#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1"


async def _molecule(s, ws, org, name: str, smiles: str | None) -> uuid.UUID:
    mid = await seed.molecule(s, ws, org, name)
    await s.execute(
        sa.text("UPDATE molecules SET smiles = :smiles WHERE id = :id"),
        {"smiles": smiles, "id": mid},
    )
    return mid


async def _world(uow, ws: uuid.UUID, other_ws: uuid.UUID) -> dict[str, uuid.UUID]:
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        other_org = await seed.org(s, other_ws)
        ids = {
            "toluene": await _molecule(s, ws, org, "toluene", "Cc1ccccc1"),
            "cyclohexane": await _molecule(s, ws, org, "cyclohexane", "C1CCCCC1"),
            "pyridine": await _molecule(s, ws, org, "pyridine", "c1ccncc1"),
            "blank": await _molecule(s, ws, org, "undisclosed", None),
            "foreign": await _molecule(s, other_ws, other_org, "foreign toluene", "Cc1ccccc1"),
        }
        await uow.commit()
    return ids


@pytest.fixture
async def world(uow, workspace_id):
    return await _world(uow, workspace_id, uuid.uuid4())


def _local(world) -> list[uuid.UUID]:
    return [world[k] for k in ("toluene", "cyclohexane", "pyridine", "blank")]


@pytest.mark.parametrize(
    ("query", "kind"),
    [("C1=CC=CC=C1", "smiles"), (KETCHER_BENZENE, None)],
    ids=["kekule-smiles", "ketcher-kekule-smarts-untagged"],
)
async def test_benzene_matches_toluene_only(session_factory, workspace_id, world, query, kind):
    matcher = SQLAlchemySubstructureMatcher(session_factory)

    result = await matcher.match(workspace_id, _local(world), query, kind)

    assert result.matched_ids == [world["toluene"]]
    assert (result.searched, result.without_structure) == (4, 1)


async def test_smarts_aromatic_carbon_matches_both_aromatics(session_factory, workspace_id, world):
    matcher = SQLAlchemySubstructureMatcher(session_factory)

    result = await matcher.match(workspace_id, _local(world), "[#6;a]", "smarts")

    assert set(result.matched_ids) == {world["toluene"], world["pyridine"]}


async def test_another_workspaces_molecule_is_neither_matched_nor_counted(
    session_factory, workspace_id, world
):
    matcher = SQLAlchemySubstructureMatcher(session_factory)

    result = await matcher.match(
        workspace_id, [world["foreign"], world["cyclohexane"]], "c1ccccc1", "smiles"
    )

    assert result.matched_ids == []
    assert (result.searched, result.without_structure) == (1, 0)


async def test_forty_thousand_ids_bind_as_one_array(session_factory, workspace_id, world):
    matcher = SQLAlchemySubstructureMatcher(session_factory)
    ids = [uuid.uuid4() for _ in range(40_000)] + [world["toluene"]]

    result = await matcher.match(workspace_id, ids, "c1ccccc1", "smiles")

    assert result.matched_ids == [world["toluene"]]
    assert result.searched == 1


@pytest.mark.parametrize(
    ("query", "kind"),
    [("C1CC", "smiles"), ("[#6", "smarts"), ("C1CC", None)],
    ids=["smiles", "smarts", "untagged"],
)
async def test_an_unreadable_query_raises_naming_it(
    session_factory, workspace_id, world, query, kind
):
    matcher = SQLAlchemySubstructureMatcher(session_factory)

    with pytest.raises(ValueError, match=re.escape(query)):
        await matcher.match(workspace_id, _local(world), query, kind)
