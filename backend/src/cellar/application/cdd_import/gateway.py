"""Ports for CDD import — application-layer interfaces.

CddVaultClient (infrastructure) satisfies these via structural subtyping.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CddProtocolGateway(Protocol):
    async def list_protocols(self, vault_id: str, api_key: str) -> list[dict[str, Any]]: ...
    async def get_protocol(
        self, vault_id: str, api_key: str, protocol_id: int
    ) -> dict[str, Any]: ...


class CddMoleculeLookupGateway(Protocol):
    async def find_molecules_by_names(
        self, vault_id: str, api_key: str, names: list[str]
    ) -> list[dict[str, Any]]: ...


class CddFieldsGateway(Protocol):
    async def list_fields(self, vault_id: str, api_key: str) -> dict[str, Any]: ...


class CddSampleGateway(CddMoleculeLookupGateway, Protocol):
    async def sample_molecules(
        self, vault_id: str, api_key: str, molecule_ids: list[int] | None, limit: int
    ) -> list[dict[str, Any]]: ...
