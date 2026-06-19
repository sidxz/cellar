"""API tests for the per-slot ontology-annotation PUT endpoint.

This interactive single-slot editor path (used by the protocol detail editor)
had no API-level coverage. These pin its happy path and assert that a malformed
term is a clean 422 at the boundary rather than a 500.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _make_protocol(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "Annotation target protocol",
            "protocol_type": "biochemical",
            "readout_definitions": [
                {"name": "IC50", "data_type": "numeric", "display_order": 0}
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_set_ontology_annotation_persists_slot(client: AsyncClient) -> None:
    protocol_id = await _make_protocol(client)
    resp = await client.put(
        f"/api/v1/protocols/{protocol_id}/ontology-annotations",
        json={
            "slot": "organism",
            "terms": [
                {
                    "term_id": "free_text:Homo sapiens",
                    "label": "Homo sapiens",
                    "ontology_source": "free_text",
                    "uri": None,
                }
            ],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    annots = resp.json()["ontology_annotations"]
    assert annots["organism"][0]["label"] == "Homo sapiens"


async def test_set_ontology_annotation_rejects_malformed_term(client: AsyncClient) -> None:
    protocol_id = await _make_protocol(client)
    resp = await client.put(
        f"/api/v1/protocols/{protocol_id}/ontology-annotations",
        json={
            "slot": "organism",
            # 'ontology_source' omitted — must be a 422, not a 500.
            "terms": [{"term_id": "free_text:X", "label": "X"}],
        },
    )
    assert resp.status_code == 422, resp.text
