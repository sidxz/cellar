from __future__ import annotations
import uuid

import pytest

from cellar.application.sar_analysis.build_scaffold_network import (
    BuildScaffoldNetwork,
    BuildScaffoldNetworkInput,
    compute_ids_hash,
)
from cellar.domain.sar_analysis.scaffold_tree_types import (
    NO_SCAFFOLD_SENTINEL,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)
from cellar.infrastructure.rdkit.scaffold_network_builder import ScaffoldNetworkBuilder


def _real_builder() -> ScaffoldNetworkBuilder:
    """Concrete RDKit-backed builder. Application unit tests are allowed to
    instantiate infra adapters directly — what's forbidden is the production
    code path doing so. See `application/sar_analysis/scaffold_network.py`."""
    return ScaffoldNetworkBuilder()


class _NullUoW:
    """No-op UoW for unit tests — fakes don't need real DB sessions."""

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


class _FakeMoleculeFetcher:
    def __init__(self, mols):
        # mols: list of tuples (id, smiles, bemis_murcko_smiles)
        self._mols = mols

    async def fetch_for_scaffold_tree(
        self, *, molecule_ids, workspace_id
    ):
        wanted = set(molecule_ids)
        return [m for m in self._mols if m[0] in wanted]


class _NeverCachingRepo:
    async def find_cached(self, *, ids_hash, ttl_seconds):
        return None


@pytest.mark.asyncio
async def test_empty_input_returns_empty_result():
    uc = BuildScaffoldNetwork(
        molecule_fetcher=_FakeMoleculeFetcher([]),
        job_repository=_NeverCachingRepo(),
        uow=_NullUoW(),
        network_builder=_real_builder(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(
            molecule_ids=[], workspace_id=uuid.uuid4()
        )
    )
    assert out.nodes == []
    assert out.edges == []
    assert out.stats.cache_hit is False


@pytest.mark.asyncio
async def test_acyclic_mols_grouped_under_no_scaffold_bucket():
    workspace_id = uuid.uuid4()
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    uc = BuildScaffoldNetwork(
        molecule_fetcher=_FakeMoleculeFetcher([(m1, "CCCC", ""), (m2, "CCCCO", "")]),
        job_repository=_NeverCachingRepo(),
        uow=_NullUoW(),
        network_builder=_real_builder(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(molecule_ids=[m1, m2], workspace_id=workspace_id)
    )
    bucket = [n for n in out.nodes if n.scaffold_smiles == NO_SCAFFOLD_SENTINEL]
    assert len(bucket) == 1
    assert set(bucket[0].molecule_ids) == {m1, m2}


@pytest.mark.asyncio
async def test_ringed_mols_yield_network_with_member_counts():
    workspace_id = uuid.uuid4()
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    uc = BuildScaffoldNetwork(
        molecule_fetcher=_FakeMoleculeFetcher([
            (m1, "c1ccccc1", "c1ccccc1"),
            (m2, "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "c1ccccc1"),  # ibuprofen → benzene
        ]),
        job_repository=_NeverCachingRepo(),
        uow=_NullUoW(),
        network_builder=_real_builder(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(molecule_ids=[m1, m2], workspace_id=workspace_id)
    )
    benzene_node = next(n for n in out.nodes if n.scaffold_smiles == "c1ccccc1")
    assert benzene_node.molecule_count == 2
    assert set(benzene_node.molecule_ids) == {m1, m2}


@pytest.mark.asyncio
async def test_cache_hit_short_circuits():
    class _AlwaysCacheHitRepo:
        async def find_cached(self, *, ids_hash, ttl_seconds):
            return ScaffoldTreeResult(
                nodes=[], edges=[],
                stats=ScaffoldTreeStats(node_count=0, elapsed_ms=999, cache_hit=False),
            )

    fetched_calls = []
    class _SpyFetcher:
        async def fetch_for_scaffold_tree(self, *, molecule_ids, workspace_id):
            fetched_calls.append((tuple(molecule_ids), workspace_id))
            return []

    uc = BuildScaffoldNetwork(
        molecule_fetcher=_SpyFetcher(),
        job_repository=_AlwaysCacheHitRepo(),
        uow=_NullUoW(),
        network_builder=_real_builder(),
        cache_ttl_seconds=3600,
    )
    out = await uc.execute(
        BuildScaffoldNetworkInput(
            molecule_ids=[uuid.uuid4()], workspace_id=uuid.uuid4()
        )
    )
    assert out.stats.cache_hit is True
    assert fetched_calls == []  # fetcher never invoked on cache hit


def test_ids_hash_stable_under_reorder():
    a = uuid.uuid4()
    b = uuid.uuid4()
    assert compute_ids_hash([a, b]) == compute_ids_hash([b, a])


def test_ids_hash_empty_is_deterministic():
    assert compute_ids_hash([]) == compute_ids_hash([])
