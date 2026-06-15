"""Pure hashing helpers for decomposition-run cache keys.

``compute_membership_hash`` folds ``(molecule_id, version)`` pairs into a stable,
order-independent SHA-256. It is **version-aware**: a merge or structure
correction bumps a member's ``version`` -> new hash -> cache miss -> recompute.
This removes the need for explicit invalidation handlers (the id-only
``compute_ids_hash`` in ``build_scaffold_network`` is deliberately NOT reused —
it cannot see a version change).

Both functions are pure (no RDKit, no I/O) so they live in the application layer.
Core-SMILES canonicalization is RDKit and lives in infrastructure; the caller
feeds the canonical string to ``sha256_hex``.
"""

from __future__ import annotations

import hashlib
from uuid import UUID


def compute_membership_hash(pairs: list[tuple[UUID, int]]) -> str:
    """SHA-256 of the sorted ``"id:version"`` strings. Order-independent."""
    payload = "\n".join(sorted(f"{mid}:{version}" for mid, version in pairs))
    return hashlib.sha256(payload.encode()).hexdigest()


def sha256_hex(text: str) -> str:
    """SHA-256 hex digest of ``text`` (used for the canonical core hash)."""
    return hashlib.sha256(text.encode()).hexdigest()
