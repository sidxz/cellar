"""FingerprintAlgorithm Protocol -- domain-level abstraction for similarity FPs.

Implementations live in infrastructure/rdkit/fingerprints/*. Domain code
references algorithms only via name; the registry resolves names to impls.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FingerprintAlgorithm(Protocol):
    """Metadata for a fingerprint algorithm.

    Pure metadata + SQL fragments. Actual fingerprint computation lives in
    infrastructure; this Protocol only exposes what the query layer needs.
    """

    @property
    def name(self) -> str:  # e.g. "morgan", "fcfp"
        ...

    @property
    def column_name(self) -> str:  # bfp column to query, e.g. "morgan_bfp"
        ...

    @property
    def cartridge_query_fn(self) -> str:
        """SQL function name that wraps a query molecule into a bfp.

        e.g. ``morganbv_fp`` for Morgan, ``featmorganbv_fp`` for FCFP.
        Implementations must produce SQL like
        ``<cartridge_query_fn>(mol_from_smiles(:q))`` (the radius arg is
        appended by the composer where applicable).
        """
        ...
