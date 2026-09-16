"""prot-cellar connection settings (``PROT_CELLAR_*`` env vars)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProtCellarSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROT_CELLAR_", env_file=".env")

    url: str = "http://localhost:8001"
    timeout_seconds: float = 30.0
