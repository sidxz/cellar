"""Logging configuration via environment variables."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class _CustomEnvSource(EnvSettingsSource):
    """Custom env source that doesn't JSON-decode string values for level_overrides."""

    def field_is_complex(self, field: Any) -> bool:
        """Mark level_overrides as non-complex so it won't be JSON-decoded."""
        if field.annotation == dict[str, str]:
            # For our custom parsing, treat it as non-complex
            # The validator will handle the string-to-dict conversion
            return False
        return super().field_is_complex(field)


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
    level_overrides: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """Use custom env source that doesn't JSON-decode level_overrides."""
        return (
            init_settings,
            _CustomEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("level_overrides", mode="before")
    @classmethod
    def _parse_overrides(cls, value: object) -> dict[str, str]:
        """Accept ``"name=LEVEL,name=LEVEL"`` strings; pass dicts through."""
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return {}
        if not value:
            return {}
        result: dict[str, str] = {}
        for pair in value.split(","):
            name, sep, lvl = pair.partition("=")
            name, lvl = name.strip(), lvl.strip()
            if sep and name and lvl:
                result[name] = lvl
        return result
