import uuid

from cellar.domain.screening_assay.collection_coverage import (
    CollectionCoverage,
    CollectionRef,
    EffectiveCollectionCoverage,
)


def _ref() -> CollectionRef:
    return CollectionRef(id=uuid.uuid4(), name="Kinase Set", type="library")


def test_fraction_is_ratio_of_covered_to_total():
    cov = CollectionCoverage(ref=_ref(), covered=1840, total=2000)
    assert cov.fraction == 0.92


def test_fraction_is_none_for_empty_collection():
    cov = CollectionCoverage(ref=_ref(), covered=0, total=0)
    assert cov.fraction is None


def test_effective_coverage_carries_run_count():
    eff = EffectiveCollectionCoverage(ref=_ref(), covered=1840, total=2000, run_count=2)
    assert eff.fraction == 0.92
    assert eff.run_count == 2
