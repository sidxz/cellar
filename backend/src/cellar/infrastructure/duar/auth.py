"""Duar auth integration — SDK initialization and FastAPI wiring."""

from __future__ import annotations

from duar_auth import Duar

from cellar.infrastructure.duar.settings import DuarSettings

# Service actions registered with Duar on startup.
# These correspond to RBAC permissions that can be granted to roles.
SERVICE_ACTIONS = [
    {"action": "cellar:register", "description": "Register molecules and batches"},
    {"action": "cellar:disclose", "description": "Submit disclosure requests"},
    {"action": "cellar:merge", "description": "Execute molecule merges"},
    {"action": "cellar:approve_run", "description": "Approve assay runs"},
    {"action": "cellar:export", "description": "Export data"},
    {"action": "cellar:admin_config", "description": "Modify workspace settings"},
    {"action": "cellar:manage_routes", "description": "Create/edit synthesis routes"},
    {"action": "cellar:request_synthesis", "description": "Submit synthesis requests"},
    {"action": "cellar:approve_synthesis", "description": "Approve synthesis requests"},
    {"action": "cellar:assign_synthesis", "description": "Assign synthesis to chemists/CROs"},
    {"action": "cellar:manage_formulations", "description": "Manage formulations"},
    {
        "action": "cellar:release_formulation_batch",
        "description": "Release formulation batches",
    },
    {"action": "cellar:manage_markush", "description": "Manage Markush definitions"},
    {"action": "cellar:search_markush", "description": "Search Markush library"},
    {"action": "cellar:approve_loan", "description": "Approve and manage plate loan requests"},
]


def create_duar(settings: DuarSettings | None = None) -> Duar:
    """Create and configure a new Duar instance.

    The returned object provides:
    - ``duar.lifespan`` — FastAPI lifespan (fetches keys, registers actions)
    - ``duar.protect(app)`` — adds auth middleware
    - ``duar.get_auth`` — FastAPI dependency returning ``RequestAuth``
    - ``duar.require_user`` — FastAPI dependency returning ``AuthenticatedUser``
    """
    if settings is None:
        settings = DuarSettings()

    return Duar(
        base_url=settings.url,
        service_name=settings.service_name,
        service_key=settings.service_key,
        mode="authz",
        idp_jwks_url=settings.idp_jwks_url,
        idp_audience=settings.idp_audience,
        idp_issuer=settings.idp_issuer or None,
        cache_ttl=settings.cache_ttl,
        actions=SERVICE_ACTIONS,
    )


def get_duar(settings: DuarSettings | None = None) -> Duar:
    """Create and return a new Duar instance.

    The caller (``create_app`` in ``app.py``) is expected to call this once
    during application startup and hold the reference.
    """
    return create_duar(settings)
