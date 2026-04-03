"""Sentinel auth integration — SDK initialization and FastAPI wiring."""

from __future__ import annotations

from sentinel_auth import Sentinel

from chem_vault.infrastructure.sentinel.settings import SentinelSettings

# Service actions registered with Sentinel on startup.
# These correspond to RBAC permissions that can be granted to roles.
SERVICE_ACTIONS = [
    {"action": "chem-vault:register", "description": "Register molecules and batches"},
    {"action": "chem-vault:disclose", "description": "Submit disclosure requests"},
    {"action": "chem-vault:merge", "description": "Execute molecule merges"},
    {"action": "chem-vault:approve_run", "description": "Approve assay runs"},
    {"action": "chem-vault:export", "description": "Export data"},
    {"action": "chem-vault:admin_config", "description": "Modify workspace settings"},
    {"action": "chem-vault:manage_routes", "description": "Create/edit synthesis routes"},
    {"action": "chem-vault:request_synthesis", "description": "Submit synthesis requests"},
    {"action": "chem-vault:approve_synthesis", "description": "Approve synthesis requests"},
    {"action": "chem-vault:assign_synthesis", "description": "Assign synthesis to chemists/CROs"},
    {"action": "chem-vault:manage_formulations", "description": "Manage formulations"},
    {
        "action": "chem-vault:release_formulation_batch",
        "description": "Release formulation batches",
    },
    {"action": "chem-vault:manage_markush", "description": "Manage Markush definitions"},
    {"action": "chem-vault:search_markush", "description": "Search Markush library"},
]


def create_sentinel(settings: SentinelSettings | None = None) -> Sentinel:
    """Create and configure the Sentinel instance.

    The returned object provides:
    - ``sentinel.lifespan`` — FastAPI lifespan (fetches keys, registers actions)
    - ``sentinel.protect(app)`` — adds auth middleware
    - ``sentinel.get_auth`` — FastAPI dependency returning ``RequestAuth``
    - ``sentinel.require_user`` — FastAPI dependency returning ``AuthenticatedUser``
    """
    if settings is None:
        settings = SentinelSettings()

    return Sentinel(
        base_url=settings.url,
        service_name=settings.service_name,
        service_key=settings.service_key,
        mode="authz",
        idp_jwks_url=settings.idp_jwks_url,
        cache_ttl=settings.cache_ttl,
        actions=SERVICE_ACTIONS,
    )
