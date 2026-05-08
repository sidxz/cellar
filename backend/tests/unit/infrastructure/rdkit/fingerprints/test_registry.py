import pytest

from chem_vault.infrastructure.rdkit.fingerprints.fcfp import FCFPAlgorithm
from chem_vault.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm
from chem_vault.infrastructure.rdkit.fingerprints.registry import (
    FingerprintRegistry,
    UnknownAlgorithmError,
)


def test_default_registry_has_morgan_and_fcfp() -> None:
    registry = FingerprintRegistry.default()
    assert set(registry.names()) == {"morgan", "fcfp"}
    assert isinstance(registry.get("morgan"), MorganAlgorithm)
    assert isinstance(registry.get("fcfp"), FCFPAlgorithm)


def test_get_unknown_algorithm_raises() -> None:
    registry = FingerprintRegistry.default()
    with pytest.raises(UnknownAlgorithmError, match="map4"):
        registry.get("map4")


def test_register_adds_new_algorithm() -> None:
    registry = FingerprintRegistry()

    class _MyAlg:
        name = "custom"
        column_name = "custom_bfp"
        cartridge_query_fn = "custom_fp"

    registry.register(_MyAlg())
    assert "custom" in registry.names()
