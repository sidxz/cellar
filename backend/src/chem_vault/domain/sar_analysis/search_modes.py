"""User-facing search modes and their (algorithm, metric, threshold) defaults.

This is the ONLY place mode-to-algorithm mappings live. Adding a 4th mode
is one new entry here plus an algorithm impl in infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from chem_vault.domain.sar_analysis.similarity_metric import (
    SimilarityMetric,
    Tanimoto,
    Tversky,
)


class SearchMode(StrEnum):
    SIMILAR = "similar"                      # broad match
    SCAFFOLD_HOP = "scaffold_hop"            # bioisosteric replacements
    FRAGMENT_IN_TARGET = "fragment_in_target"  # big molecules containing this fragment


@dataclass(frozen=True)
class ModeConfig:
    """Default (algorithm, metric, threshold) for a search mode."""

    algorithm: str
    metric: SimilarityMetric
    threshold: float
    label: str
    description: str


MODE_DEFAULTS: dict[SearchMode, ModeConfig] = {
    SearchMode.SIMILAR: ModeConfig(
        algorithm="morgan",
        metric=Tanimoto(),
        threshold=0.7,
        label="Similar",
        description="Tanimoto similarity over Morgan/ECFP4 fingerprints.",
    ),
    SearchMode.SCAFFOLD_HOP: ModeConfig(
        algorithm="fcfp",
        metric=Tanimoto(),
        threshold=0.55,
        label="Scaffold hop",
        description=(
            "Tanimoto over feature-class (FCFP4) fingerprints. "
            "Surfaces bioisosteric replacements that strict similarity may miss."
        ),
    ),
    SearchMode.FRAGMENT_IN_TARGET: ModeConfig(
        algorithm="morgan",
        metric=Tversky(alpha=1.0, beta=0.0),
        threshold=0.7,
        label="Contains my fragment",
        description=(
            "Asymmetric Tversky similarity (α=1, β=0). "
            "Ranks targets by the fraction of query features they contain."
        ),
    ),
}
