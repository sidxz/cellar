"""Port for CDD protocol import — application-layer interface.

CddVaultClient (infrastructure) satisfies this via structural subtyping.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CddProtocolGateway(Protocol):
    async def list_protocols(self, vault_id: str, api_key: str) -> list[dict[str, Any]]: ...
    async def get_protocol(
        self, vault_id: str, api_key: str, protocol_id: int
    ) -> dict[str, Any]: ...
