"""MaxMin diverse-subset picker wrapper."""

from __future__ import annotations

from rdkit import DataStructs
from rdkit.SimDivFilters import MaxMinPicker


class MaxMinPickerAdapter:
    """Greedy diverse-subset selection on Tanimoto similarity.

    Wraps RDKit's MaxMinPicker.LazyPick — at each step picks the compound
    farthest from all already-picked compounds. Deterministic given firstPicks (seed).
    """

    def __init__(self, *, seed: int = 42) -> None:
        self._seed = seed

    def pick(self, fingerprints: list, *, n: int) -> list[int]:
        size = len(fingerprints)
        if n >= size:
            return list(range(size))

        def dist_fn(i: int, j: int) -> float:
            return 1.0 - DataStructs.TanimotoSimilarity(fingerprints[i], fingerprints[j])

        picker = MaxMinPicker()
        picks = picker.LazyPick(dist_fn, size, n, seed=self._seed)
        return list(picks)
