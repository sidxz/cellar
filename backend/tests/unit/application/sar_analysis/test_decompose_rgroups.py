from __future__ import annotations

import uuid

import pytest

from cellar.application.sar_analysis.decompose_rgroups import (
    DecomposeRGroups,
    DecomposeRGroupsInput,
)
from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer


class _NullUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def commit(self):
        return []

    async def rollback(self):
        pass

    @property
    def is_active(self):
        return True


class _FakeFetcher:
    """Returns (id, smiles, bemis_murcko_smiles) triples like the real repo."""

    def __init__(self, rows):
        self._rows = rows

    async def fetch_for_scaffold_tree(self, *, molecule_ids, workspace_id):
        wanted = set(molecule_ids)
        return [r for r in self._rows if r[0] in wanted]


@pytest.mark.asyncio
async def test_decompose_uses_fetched_smiles():
    f_id, cl_id = uuid.uuid4(), uuid.uuid4()
    uc = DecomposeRGroups(
        molecule_fetcher=_FakeFetcher(
            [
                (f_id, "Fc1ccccc1", "c1ccccc1"),
                (cl_id, "Clc1ccccc1", "c1ccccc1"),
            ]
        ),
        decomposer=RGroupDecomposer(),
        uow=_NullUoW(),
    )
    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=[f_id, cl_id],
            workspace_id=uuid.uuid4(),
            core_smiles="c1ccccc1",
        )
    )
    assert "R1" in result.rgroup_labels
    assert {a.molecule_id for a in result.assignments} == {f_id, cl_id}


@pytest.mark.asyncio
async def test_empty_set_returns_empty_result():
    uc = DecomposeRGroups(
        molecule_fetcher=_FakeFetcher([]),
        decomposer=RGroupDecomposer(),
        uow=_NullUoW(),
    )
    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=[], workspace_id=uuid.uuid4(), core_smiles="c1ccccc1"
        )
    )
    assert result.assignments == []
    assert result.unmatched_ids == []


@pytest.mark.asyncio
async def test_molecule_without_smiles_is_unmatched_not_dropped():
    good_id, no_smiles_id = uuid.uuid4(), uuid.uuid4()
    uc = DecomposeRGroups(
        molecule_fetcher=_FakeFetcher(
            [
                (good_id, "Fc1ccccc1", "c1ccccc1"),
                (no_smiles_id, "", None),
            ]
        ),
        decomposer=RGroupDecomposer(),
        uow=_NullUoW(),
    )
    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=[good_id, no_smiles_id],
            workspace_id=uuid.uuid4(),
            core_smiles="c1ccccc1",
        )
    )
    # The empty-SMILES molecule is surfaced as unmatched, never silently dropped.
    assert no_smiles_id in result.unmatched_ids
    assert good_id in {a.molecule_id for a in result.assignments}
    # Every input id is accounted for in exactly one bucket.
    accounted = {a.molecule_id for a in result.assignments} | set(result.unmatched_ids)
    assert accounted == {good_id, no_smiles_id}
