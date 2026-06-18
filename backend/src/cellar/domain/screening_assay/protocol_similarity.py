"""Value object: a single protocol-similarity match (a read-model result)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolSimilarityMatch:
    protocol_id: uuid.UUID
    name: str
    protocol_type: str
    status: str
    score: float
    # True when this looks like a *run* of an existing method (the keystone
    # reroute), not a new method: strong readout-schema overlap AND a shared
    # target or a strong name match.
    is_run_candidate: bool
    shared_target_ids: list[uuid.UUID]
    shared_readout_kinds: list[str]
