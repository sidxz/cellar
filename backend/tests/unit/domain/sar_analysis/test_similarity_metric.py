import pytest

from cellar.domain.sar_analysis.similarity_metric import (
    Tanimoto,
    Tversky,
    serialize_metric,
)


def test_tanimoto_singleton_serializes_to_string() -> None:
    assert serialize_metric(Tanimoto()) == "tanimoto"


def test_tversky_serializes_with_alpha_and_beta() -> None:
    metric = Tversky(alpha=1.0, beta=0.0)
    assert serialize_metric(metric) == "tversky(1.0,0.0)"


def test_tversky_rejects_negative_alpha() -> None:
    with pytest.raises(ValueError, match="alpha must be >= 0"):
        Tversky(alpha=-0.1, beta=0.5)


def test_tversky_rejects_negative_beta() -> None:
    with pytest.raises(ValueError, match="beta must be >= 0"):
        Tversky(alpha=0.5, beta=-0.1)
