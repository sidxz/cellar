"""Application-layer ports for streaming R-group decomposition.

The concrete impl lives in
``cellar.infrastructure.rdkit.streaming_rgroup_decomposer.StreamingRGroupDecomposer``
and is wired via DI. The application layer depends only on these Protocols + the
domain result VO so the layer rule (application MUST NOT import infrastructure)
holds.

``RGroupSession`` accumulates molecules across batches and labels them
consistently only at ``finish()`` — the streaming-correctness keystone (one
shared RDKit object across batches; memory is O(matched set)).
"""

from __future__ import annotations

from typing import Any, Protocol

from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult


class RGroupSession(Protocol):
    def add(self, molecule_id: Any, smiles: str) -> bool: ...

    def finish(self) -> RGroupDecompositionResult: ...


class StreamingDecomposer(Protocol):
    def canonical_core_smiles(self, core_smiles: str) -> str: ...

    def session(self, *, core_smiles: str) -> RGroupSession: ...
