"""BuildScaffoldNetwork — pure-structural scaffold tree builder.

Pipeline:
1. compute_ids_hash(molecule_ids) → stable cache key fragment.
2. job repository find_cached(ids_hash, ttl_seconds) → short-circuit on hit.
3. fetch (id, smiles, bemis_murcko_smiles) tuples scoped to workspace.
4. Partition rows: ringed (with stored scaffold) vs acyclic ("" scaffold).
5. ScaffoldNetworkBuilder.build(ringed_mols) → raw network.
6. Map node SMILES → owning molecule_ids using stored bemis_murcko_smiles.
7. DFS through edge graph to compute subtree_molecule_count per node.
8. Add NO_SCAFFOLD_SENTINEL bucket node if any acyclic mols exist.
9. Return ScaffoldTreeResult — caller persists if it wants caching.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from rdkit import Chem

from cellar.application.sar_analysis.repositories import ScaffoldTreeJobRepository
from cellar.application.sar_analysis.scaffold_network import ScaffoldNetworkBuilder
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.scaffold_tree_types import (
    NO_SCAFFOLD_SENTINEL,
    ScaffoldTreeEdge,
    ScaffoldTreeNode,
    ScaffoldTreeResult,
    ScaffoldTreeStats,
)


@dataclass(frozen=True)
class BuildScaffoldNetworkInput:
    molecule_ids: list[UUID]
    workspace_id: UUID


class MoleculeFetcherForScaffoldTree(Protocol):
    async def fetch_for_scaffold_tree(
        self, *, molecule_ids: list[UUID], workspace_id: UUID
    ) -> list[tuple[UUID, str, str | None]]: ...


def compute_ids_hash(ids: list[UUID]) -> str:
    """Stable SHA-256 hash of a molecule ID list, order-independent."""
    payload = ",".join(sorted(str(i) for i in ids))
    return hashlib.sha256(payload.encode()).hexdigest()


class BuildScaffoldNetwork:
    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeFetcherForScaffoldTree,
        job_repository: ScaffoldTreeJobRepository,
        uow: UnitOfWork,
        network_builder: ScaffoldNetworkBuilder,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._repo = job_repository
        self._uow = uow
        self._ttl = cache_ttl_seconds
        self._builder = network_builder

    async def execute(self, payload: BuildScaffoldNetworkInput) -> ScaffoldTreeResult:
        ids_hash = compute_ids_hash(payload.molecule_ids)

        async with self._uow:
            cached = await self._repo.find_cached(ids_hash=ids_hash, ttl_seconds=self._ttl)

        if cached is not None:
            return ScaffoldTreeResult(
                nodes=cached.nodes,
                edges=cached.edges,
                stats=ScaffoldTreeStats(
                    node_count=cached.stats.node_count,
                    elapsed_ms=cached.stats.elapsed_ms,
                    cache_hit=True,
                    truncated=cached.stats.truncated,
                ),
            )

        started = time.perf_counter()
        async with self._uow:
            rows = await self._fetcher.fetch_for_scaffold_tree(
                molecule_ids=payload.molecule_ids, workspace_id=payload.workspace_id
            )
        if not rows:
            return _empty_result(started)

        acyclic_ids: list[UUID] = []
        scaffold_to_mol_ids: dict[str, list[UUID]] = defaultdict(list)
        # Build the network from the STORED Bemis-Murcko scaffolds, not from
        # the full molecules. The original full-mol input caused rdScaffoldNetwork
        # to emit nodes that still carried OH / OMe / stereo decorations
        # (the "with attachments" variant and the molecule itself as a root).
        # Feeding the pure ring skeletons in means every emitted node is a
        # ring-fragment of a Murcko scaffold — visually identifiable as a real
        # scaffold by any chemist. Deduplicate by scaffold SMILES so we don't
        # build the network on N copies of `c1ccccc1`.
        scaffold_input_mols: dict[str, Chem.Mol] = {}
        for mid, _smi, scaffold in rows:
            if scaffold == "":
                acyclic_ids.append(mid)
                continue
            if scaffold is None:
                # Not yet backfilled — silently exclude from both buckets
                continue
            if scaffold not in scaffold_input_mols:
                mol = Chem.MolFromSmiles(scaffold)
                if mol is None:
                    continue
                scaffold_input_mols[scaffold] = mol
            scaffold_to_mol_ids[scaffold].append(mid)

        network = self._builder.build(list(scaffold_input_mols.values()))

        # Build parent→children map from (parent, child) edge tuples
        children: dict[str, list[str]] = defaultdict(list)
        for parent, child in network.edges:
            children[parent].append(child)

        # DFS with memoisation — subtree_count(node) = own members + all
        # descendant members.  The memo prevents double-counting when a node
        # appears as a child of multiple parents (DAG case).
        memo: dict[str, int] = {}

        def subtree_count(node: str) -> int:
            if node in memo:
                return memo[node]
            own = len(scaffold_to_mol_ids.get(node, []))
            total = own + sum(subtree_count(c) for c in children.get(node, []))
            memo[node] = total
            return total

        nodes: list[ScaffoldTreeNode] = []
        for scaffold in network.node_smiles:
            members = scaffold_to_mol_ids.get(scaffold, [])
            nodes.append(
                ScaffoldTreeNode(
                    scaffold_smiles=scaffold,
                    molecule_ids=list(members),
                    molecule_count=len(members),
                    subtree_molecule_count=subtree_count(scaffold),
                )
            )

        if acyclic_ids:
            nodes.append(
                ScaffoldTreeNode(
                    scaffold_smiles=NO_SCAFFOLD_SENTINEL,
                    molecule_ids=list(acyclic_ids),
                    molecule_count=len(acyclic_ids),
                    subtree_molecule_count=len(acyclic_ids),
                )
            )

        edges = [
            ScaffoldTreeEdge(parent_smiles=p, child_smiles=c)
            for p, c in network.edges
        ]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ScaffoldTreeResult(
            nodes=nodes,
            edges=edges,
            stats=ScaffoldTreeStats(
                node_count=len(nodes),
                elapsed_ms=elapsed_ms,
                cache_hit=False,
            ),
        )


def _empty_result(started: float) -> ScaffoldTreeResult:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ScaffoldTreeResult(
        nodes=[],
        edges=[],
        stats=ScaffoldTreeStats(
            node_count=0, elapsed_ms=elapsed_ms, cache_hit=False
        ),
    )
