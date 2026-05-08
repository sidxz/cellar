"""FingerprintRegistry -- runtime lookup from algorithm name to impl."""

from __future__ import annotations

from chem_vault.domain.sar_analysis.fingerprint_algorithm import FingerprintAlgorithm
from chem_vault.infrastructure.rdkit.fingerprints.fcfp import FCFPAlgorithm
from chem_vault.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm


class UnknownAlgorithmError(KeyError):
    """Raised when a query references an algorithm not in the registry."""


class FingerprintRegistry:
    def __init__(self) -> None:
        self._algos: dict[str, FingerprintAlgorithm] = {}

    @classmethod
    def default(cls) -> FingerprintRegistry:
        registry = cls()
        registry.register(MorganAlgorithm())
        registry.register(FCFPAlgorithm())
        return registry

    def register(self, algorithm: FingerprintAlgorithm) -> None:
        self._algos[algorithm.name] = algorithm

    def get(self, name: str) -> FingerprintAlgorithm:
        try:
            return self._algos[name]
        except KeyError as exc:
            valid = ", ".join(sorted(self._algos)) or "<empty>"
            raise UnknownAlgorithmError(
                f"Unknown fingerprint algorithm: {name!r}. Valid: {valid}"
            ) from exc

    def names(self) -> list[str]:
        return list(self._algos)

    def all(self) -> list[FingerprintAlgorithm]:
        return list(self._algos.values())
