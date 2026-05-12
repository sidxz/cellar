"""Database configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Typed, validated database configuration.

    Reads from environment variables (``DATABASE_URL``, ``POOL_SIZE``, etc.)
    and ``.env`` file.
    """

    model_config = SettingsConfigDict(env_prefix="", env_file=".env")

    database_url: str

    # Connection pool
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True
    echo: bool = False
