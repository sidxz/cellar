"""Pure structural fingerprint for a Protocol — the dedup/browse spine.

Derived solely from the aggregate's structured content (type + readout
schema). Targets are intentionally excluded — they live in protocol_targets
and the similarity query joins them live, avoiding a derived-data drift
surface. Recomputed on every save by the repository; never hand-set.
"""
from __future__ import annotations

from cellar.domain.screening_assay.protocol import Protocol

FINGERPRINT_VERSION = 1


def _normalize_readout_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def compute_protocol_fingerprint(protocol: Protocol) -> dict:
    readout_kinds = sorted(
        {_normalize_readout_name(rd.name) for rd in protocol.readout_definitions if rd.name.strip()}
    )
    readout_data_types = sorted({rd.data_type.value for rd in protocol.readout_definitions})
    return {
        "v": FINGERPRINT_VERSION,
        "protocol_type": protocol.protocol_type.value,
        "readout_kinds": readout_kinds,
        "readout_data_types": readout_data_types,
    }
