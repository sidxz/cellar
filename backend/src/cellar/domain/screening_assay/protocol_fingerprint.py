"""Pure structural fingerprint for a Protocol — the dedup/browse spine.

Derived solely from the aggregate's structured content (type + readout schema
+ ontology-annotation facets). Targets are intentionally excluded — they live
in protocol_targets and the similarity query joins them live, avoiding a
derived-data drift surface. Recomputed on every save by the repository; never
hand-set.
"""
from __future__ import annotations

from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.shared.ontology import OntologyTerm

# v1: protocol_type + readout schema. v2: adds the `facets` map (ontology
# annotations folded in). Bump whenever the derivation changes so rows can be
# re-derived.
FINGERPRINT_VERSION = 2

_FREE_TEXT_PREFIX = "free_text:"


def normalize_facet_id(facet_id: str) -> str:
    """Canonical comparable key for a facet id. Grounded ids → lowercased/
    stripped/whitespace-collapsed; free-text ids (``free_text:<label>``) keep
    the prefix and collapse/lower only the label. Used by both the fingerprint
    builder and the similarity query so their keys always agree."""
    s = facet_id.strip()
    if s.startswith(_FREE_TEXT_PREFIX):
        label = s[len(_FREE_TEXT_PREFIX):]
        return _FREE_TEXT_PREFIX + " ".join(label.lower().split())
    return " ".join(s.lower().split())


def _normalize_readout_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _facet_key(term: OntologyTerm) -> str:
    """Stable, comparable key for a facet term.

    Grounded terms cluster by their (lowercased) ontology id; free-text terms
    by a normalized label so casing/whitespace variants converge.
    """
    raw = f"{_FREE_TEXT_PREFIX}{term.label}" if term.ontology_source == "free_text" else term.term_id
    return normalize_facet_id(raw)


def compute_protocol_fingerprint(protocol: Protocol) -> dict:
    readout_kinds = sorted(
        {_normalize_readout_name(rd.name) for rd in protocol.readout_definitions if rd.name.strip()}
    )
    readout_data_types = sorted({rd.data_type.value for rd in protocol.readout_definitions})
    facets = {
        slot: sorted({_facet_key(t) for t in terms})
        for slot, terms in (protocol.ontology_annotations or {}).items()
        if terms
    }
    return {
        "v": FINGERPRINT_VERSION,
        "protocol_type": protocol.protocol_type.value,
        "readout_kinds": readout_kinds,
        "readout_data_types": readout_data_types,
        "facets": facets,
    }
