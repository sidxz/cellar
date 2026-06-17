"""Logging configuration via environment variables."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class LoggingSettings(BaseSettings):
    """Typed logging configuration.

    Env vars (prefix ``LOG_``):
      - ``LOG_LEVEL``           root level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
      - ``LOG_FORMAT``          ``json`` (prod) or ``console`` (dev)
      - ``LOG_LEVEL_OVERRIDES`` ``"name=LEVEL,name=LEVEL"`` per-logger overrides
    """

    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env")

    level: str = "INFO"
    format: str = "json"
    # NoDecode: pydantic-settings would otherwise JSON-decode dict fields from the
    # environment before validators run, which breaks the "name=LEVEL,name=LEVEL"
    # string format. NoDecode hands the raw string to the before-validator.
    level_overrides: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    @field_validator("level_overrides", mode="before")
    @classmethod
    def _parse_overrides(cls, value: object) -> object:
        """Accept ``"name=LEVEL,name=LEVEL"`` strings; pass dicts through; skip malformed."""
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value:
            return {}
        result: dict[str, str] = {}
        for pair in value.split(","):
            name, sep, lvl = pair.partition("=")
            name, lvl = name.strip(), lvl.strip()
            if sep and name and lvl:
                result[name] = lvl
        return result
