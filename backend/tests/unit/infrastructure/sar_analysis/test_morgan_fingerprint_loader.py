"""Round-trip test: bytes written by MorganAlgorithm.compute_bytes must decode
back to an ExplicitBitVect with the same on-bits."""

from __future__ import annotations

from rdkit import Chem

from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm
from cellar.infrastructure.sar_analysis.morgan_fingerprint_loader import (
    _bytes_to_bitvect,
)


def test_bytes_to_bitvect_round_trips_morgan_compute_bytes() -> None:
    mol = Chem.MolFromSmiles("c1ccccc1CCN")
    alg = MorganAlgorithm()
    packed = alg.compute_bytes(mol)
    assert len(packed) == 256  # 2048 bits / 8

    bv = _bytes_to_bitvect(packed)
    assert bv.GetNumBits() == 2048

    # On-bits should match the original fingerprint's on-bits.
    direct_fp = alg._gen.GetFingerprint(mol)
    assert list(bv.GetOnBits()) == list(direct_fp.GetOnBits())
