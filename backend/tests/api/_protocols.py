"""Create bodies for tests that need *a* protocol, not a particular name.

Protocol names are generated from the category pattern and the facts. "Plasma stability" needs
no facts, and a per-call discriminator keeps several protocols in one test from colliding.
"""

from itertools import count
from typing import Any

from httpx import AsyncClient

_seq = count(1)


async def seed_protocol_categories(client: AsyncClient) -> None:
    """Adds the shipped default categories (idempotent)."""
    r = await client.post("/api/v1/protocol-categories/defaults")
    assert r.status_code == 200, r.text


async def protocol_body(
    client: AsyncClient, label: str = "test", *, seeder: AsyncClient | None = None, **fields: Any
) -> dict[str, Any]:
    """``seeder`` seeds the categories when ``client`` is not an admin."""
    await seed_protocol_categories(seeder or client)
    return {
        "protocol_type": "biochemical",
        "category": "Plasma stability",
        "discriminator": f"{label} {next(_seq)}",
        "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
    } | fields
