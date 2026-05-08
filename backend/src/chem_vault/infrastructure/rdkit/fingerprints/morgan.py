"""Morgan / ECFP4-equivalent fingerprint, computed in Python with stereo awareness.

The cartridge ``morganbv_fp`` does not expose ``useChirality``. To get
stereo-aware Morgan into a ``bfp`` column, we compute in Python and let a
DB trigger lift the bytes via ``bfp_from_binary_text``.
"""

from __future__ import annotations

from rdkit.Chem import rdFingerprintGenerator
from rdkit.DataStructs import ExplicitBitVect


class MorganAlgorithm:
    name = "morgan"
    column_name = "morgan_bfp"
    cartridge_query_fn = "morganbv_fp"

    def __init__(self) -> None:
        self._gen = rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=2048, includeChirality=True
        )

    def compute_bytes(self, mol: object) -> bytes:
        fp: ExplicitBitVect = self._gen.GetFingerprint(mol)  # type: ignore[arg-type]
        # Pack the bit string to bytes (cartridge `bfp_from_binary_text` expects
        # this format: 256 bytes packed MSB-first).
        bs = fp.ToBitString()
        return bytes(int(bs[i : i + 8], 2) for i in range(0, len(bs), 8))
