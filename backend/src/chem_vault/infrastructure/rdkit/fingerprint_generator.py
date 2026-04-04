"""Molecular fingerprint generation via RDKit."""

from __future__ import annotations

from rdkit.Chem import MACCSkeys, rdFingerprintGenerator
from rdkit.DataStructs import ExplicitBitVect


def _fp_to_bytes(fp: ExplicitBitVect) -> bytes:
    """Convert an RDKit fingerprint bit vector to bytes."""
    bs = fp.ToBitString()
    return bytes(int(bs[i : i + 8], 2) for i in range(0, len(bs), 8))


class FingerprintGenerator:
    """Generates multiple fingerprint types from an RDKit Mol object."""

    def __init__(self) -> None:
        self._morgan_gen = rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=2048
        )
        self._rdkit_gen = rdFingerprintGenerator.GetRDKitFPGenerator(fpSize=2048)
        self._torsion_gen = rdFingerprintGenerator.GetTopologicalTorsionGenerator(
            fpSize=2048
        )
        self._atom_pair_gen = rdFingerprintGenerator.GetAtomPairGenerator(fpSize=2048)

    def generate_all(self, mol: object) -> dict[str, bytes]:
        """Generate all fingerprint types and return as binary bytes.

        Keys: morgan, rdkit, maccs, topological_torsion, atom_pair
        """
        return {
            "morgan": _fp_to_bytes(self._morgan_gen.GetFingerprint(mol)),
            "rdkit": _fp_to_bytes(self._rdkit_gen.GetFingerprint(mol)),
            "maccs": _fp_to_bytes(MACCSkeys.GenMACCSKeys(mol)),
            "topological_torsion": _fp_to_bytes(
                self._torsion_gen.GetFingerprint(mol)
            ),
            "atom_pair": _fp_to_bytes(self._atom_pair_gen.GetFingerprint(mol)),
        }

    def generate_morgan(self, mol: object) -> bytes:
        return _fp_to_bytes(self._morgan_gen.GetFingerprint(mol))
