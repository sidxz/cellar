"""Sentinel auth configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SentinelSettings(BaseSettings):
    """Typed configuration for Sentinel auth integration (authz mode)."""

    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env")

    url: str = "http://localhost:9003"
    service_name: str = "cellar"
    service_key: str = ""
    idp_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    # Required since Sentinel 0.11.0 (authz mode): the IdP token's `aud` must
    # equal your OAuth client_id, else a token minted for any other client of
    # the same IdP would authenticate. `idp_issuer` defends against IdP swaps.
    idp_audience: str = ""
    idp_issuer: str = "https://accounts.google.com"
    cache_ttl: float = 120
