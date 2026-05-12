"""Environment-variable-based secret provider (fallback / local dev)."""

from __future__ import annotations

import os


class EnvSecretProvider:
    """Reads secrets from environment variables.

    Key mapping: ``workspace_id:key_name`` → ``WORKSPACE_ID_KEY_NAME``
    (uppercased, colons replaced with underscores).

    This provider is read-only — set/delete are no-ops.
    """

    async def get_secret(self, key: str) -> str | None:
        env_key = key.upper().replace(":", "_")
        return os.environ.get(env_key)

    async def set_secret(self, key: str, value: str) -> None:
        pass  # env vars are read-only

    async def delete_secret(self, key: str) -> None:
        pass  # env vars are read-only
