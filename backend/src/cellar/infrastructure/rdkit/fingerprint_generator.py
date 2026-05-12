"""Stereo-aware Morgan fingerprint generation."""

from __future__ import annotations

from cellar.application.chemical_registration.protocols import Fingerprints
from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm

__all__ = ["FingerprintGenerator", "Fingerprints"]


class FingerprintGenerator:
    """Generates stereo-aware Morgan fingerprint bytes."""

    def __init__(self, morgan: MorganAlgorithm | None = None) -> None:
        self._morgan = morgan or MorganAlgorithm()

    def compute(self, mol: object) -> Fingerprints:
        return Fingerprints(morgan=self._morgan.compute_bytes(mol))
