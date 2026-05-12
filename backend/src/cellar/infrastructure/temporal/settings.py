"""Temporal configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class TemporalSettings(BaseSettings):
    """Typed, validated Temporal configuration.

    Reads from environment variables (``TEMPORAL_ADDRESS``, etc.).
    """

    model_config = SettingsConfigDict(env_prefix="TEMPORAL_", env_file=".env")

    address: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "cellar-main"
