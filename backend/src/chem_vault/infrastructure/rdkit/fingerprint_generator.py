"""Stereo-aware Morgan fingerprint generation."""

from __future__ import annotations

from dataclasses import dataclass

from chem_vault.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm


@dataclass(frozen=True)
class Fingerprints:
    """Computed fingerprints for a single molecule.

    Only Morgan is computed in Python (stereo-aware). FCFP is computed by
    a Postgres trigger from the canonical SMILES.
    """

    morgan: bytes


class FingerprintGenerator:
    """Generates stereo-aware Morgan fingerprint bytes."""

    def __init__(self, morgan: MorganAlgorithm | None = None) -> None:
        self._morgan = morgan or MorganAlgorithm()

    def compute(self, mol: object) -> Fingerprints:
        return Fingerprints(morgan=self._morgan.compute_bytes(mol))
