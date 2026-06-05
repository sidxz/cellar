"""Similarity metric value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tanimoto:
    """Symmetric Jaccard-style similarity. The default."""


@dataclass(frozen=True)
class Tversky:
    """Asymmetric similarity with alpha/beta weights.

    ``Tversky(alpha=1.0, beta=0.0)`` answers "is A a feature-subset of B?",
    i.e. fragment-in-target search. ``alpha == beta == 1`` reduces to Jaccard.
    """

    alpha: float
    beta: float

    def __post_init__(self) -> None:
        if self.alpha < 0:
            raise ValueError(f"alpha must be >= 0, got {self.alpha}")
        if self.beta < 0:
            raise ValueError(f"beta must be >= 0, got {self.beta}")


SimilarityMetric = Tanimoto | Tversky


def serialize_metric(metric: SimilarityMetric) -> str:
    """Stable string form for API responses and logs."""
    if isinstance(metric, Tanimoto):
        return "tanimoto"
    if isinstance(metric, Tversky):
        return f"tversky({metric.alpha},{metric.beta})"
    raise TypeError(f"Unknown metric: {metric!r}")
