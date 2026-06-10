"""Application-layer port for R-group decomposition.

The concrete impl lives in
``cellar.infrastructure.rdkit.rgroup_decomposer.RGroupDecomposer`` and is wired
via DI. The application layer depends only on this Protocol + the domain result
VO so the layer-dependency rule (application MUST NOT import infrastructure) is
preserved.
"""

from __future__ import annotations

from typing import Any, Protocol

from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult


class RGroupDecomposer(Protocol):
    """Decomposes ``(id, smiles)`` molecules against a core SMILES.

    The element type of ``molecules`` is left loose (``Any`` id) so the
    application layer doesn't pin an rdkit/UUID dependency at the boundary.
    """

    def decompose(
        self, *, core_smiles: str, molecules: list[tuple[Any, str]]
    ) -> RGroupDecompositionResult: ...
