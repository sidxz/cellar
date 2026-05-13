"""Lagom composition root — wires all dependencies for the application.

Each bounded context owns a `register_<context>(container)` function in its
own `_<context>.py` module. `create_container` composes them.

Usage::

    container = create_container(db_settings)
    uow = container[AsyncUnitOfWork]
"""

from __future__ import annotations

from lagom import Container

from cellar.infrastructure.di._admin import register_admin
from cellar.infrastructure.di._attachment import register_attachment
from cellar.infrastructure.di._audit import register_audit
from cellar.infrastructure.di._cdd_import import register_cdd_import
from cellar.infrastructure.di._chemical_registration import register_chemical_registration
from cellar.infrastructure.di._core import register_core
from cellar.infrastructure.di._dashboard import register_dashboard
from cellar.infrastructure.di._inventory import register_inventory
from cellar.infrastructure.di._research_organization import register_research_organization
from cellar.infrastructure.di._screening import register_screening
from cellar.infrastructure.di._user import register_user
from cellar.infrastructure.di._workspace_config import register_workspace_config
from cellar.infrastructure.persistence.settings import DatabaseSettings


def create_container(db_settings: DatabaseSettings | None = None) -> Container:
    """Build and return the fully-wired DI container."""
    container = Container()

    register_core(container, db_settings)
    register_admin(container)
    register_audit(container)
    register_user(container)
    register_workspace_config(container)
    register_chemical_registration(container)
    register_screening(container)
    register_inventory(container)
    register_research_organization(container)
    register_attachment(container)
    register_dashboard(container)
    register_cdd_import(container)

    return container
