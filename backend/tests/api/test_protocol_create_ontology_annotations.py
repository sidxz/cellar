"""API test: protocol create persists ALL ontology-annotation facets atomically.

Regression for the create-dialog race: each facet slot used to be written via a
separate, concurrent PUT after create, so all but one slot was silently dropped
(they raced on the aggregate's optimistic-concurrency version). Facets are now
part of the create transaction.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_protocol_persists_all_ontology_annotation_slots(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "ArgB ArgC coupled NADPH",
            "protocol_type": "biochemical",
            "readout_definitions": [
                {"name": "% Inhibition", "data_type": "numeric", "display_order": 0}
            ],
            "ontology_annotations": {
                "organism": [
                    {
                        "term_id": "free_text:Homo sapiens",
                        "label": "Homo sapiens",
                        "ontology_source": "free_text",
                        "uri": None,
                    }
                ],
                "assay_format": [
                    {
                        "term_id": "free_text:biochemical",
                        "label": "biochemical",
                        "ontology_source": "free_text",
                        "uri": None,
                    }
                ],
                "detection": [
                    {
                        "term_id": "free_text:fluorescence",
                        "label": "fluorescence",
                        "ontology_source": "free_text",
                        "uri": None,
                    }
                ],
            },
        },
    )
    assert resp.status_code == 201, resp.text
    annots = resp.json()["ontology_annotations"]
    # All three slots survive — not just whichever won a race.
    assert set(annots) == {"organism", "assay_format", "detection"}
    assert annots["assay_format"][0]["label"] == "biochemical"
    assert annots["detection"][0]["label"] == "fluorescence"


async def test_create_protocol_rejects_facet_term_missing_required_field(
    client: AsyncClient,
) -> None:
    """A facet term missing a required field is a client error (422) at the
    boundary — not a 500 from a KeyError deep in the use case."""
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "Malformed facet term",
            "protocol_type": "biochemical",
            "readout_definitions": [
                {"name": "IC50", "data_type": "numeric", "display_order": 0}
            ],
            "ontology_annotations": {
                # 'ontology_source' omitted.
                "organism": [{"term_id": "free_text:X", "label": "X"}],
            },
        },
    )
    assert resp.status_code == 422, resp.text


async def test_create_protocol_without_annotations_still_succeeds(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "Plain protocol no facets",
            "protocol_type": "biochemical",
            "readout_definitions": [
                {"name": "IC50", "data_type": "numeric", "display_order": 0}
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["ontology_annotations"] in (None, {})
