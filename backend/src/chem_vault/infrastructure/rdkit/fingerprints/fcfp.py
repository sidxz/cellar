"""FCFP -- pharmacophore-flavored circular fingerprint.

Fully cartridge-managed (no Python compute). The DB trigger writes
``fcfp_bfp`` from ``smiles`` via ``featmorganbv_fp(mol_from_smiles(...), 2)``.
This algorithm is metadata only; it has no ``compute_bytes`` method.
"""

from __future__ import annotations


class FCFPAlgorithm:
    name = "fcfp"
    column_name = "fcfp_bfp"
    cartridge_query_fn = "featmorganbv_fp"
