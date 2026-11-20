"""API test: protocol create persists ALL ontology-annotation facets atomically.

Regression for the create-dialog race: each facet slot used to be written via a
separate, concurrent PUT after create, so all but one slot was silently dropped
(they raced on the aggregate's optimistic-concurrency version). Facets are now
part of the create transaction.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api._protocols import protocol_body

pytestmark = pytest.mark.asyncio


async def test_create_protocol_persists_all_ontology_annotation_slots(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            **await protocol_body(client),
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
