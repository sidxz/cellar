"""Chain-of-responsibility secret provider."""

from __future__ import annotations

from cellar.domain.shared.secret_provider import SecretProvider


class ChainSecretProvider:
    """Tries multiple providers in order; returns the first non-None result.

    Writes (set/delete) are delegated to the *first* provider only,
    which is assumed to be the primary writable store.
    """

    def __init__(self, *providers: SecretProvider) -> None:
        self._providers = providers

    async def get_secret(self, key: str) -> str | None:
        for provider in self._providers:
            value = await provider.get_secret(key)
            if value is not None:
                return value
        return None

    async def set_secret(self, key: str, value: str) -> None:
        if self._providers:
            await self._providers[0].set_secret(key, value)

    async def delete_secret(self, key: str) -> None:
        if self._providers:
            await self._providers[0].delete_secret(key)
