"""Admin context DI bindings."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.admin.admin_hard_delete import AdminHardDelete
from cellar.application.admin.cascade_delete import CascadeDelete
from cellar.application.admin.cascade_preview import CascadePreview
from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.infrastructure.cascade.cascade_service_impl import UoWBackedCascadeService
from cellar.infrastructure.di._chemical_registration import build_chemical_registration_admin_repos
from cellar.infrastructure.di._inventory import build_inventory_admin_repos
from cellar.infrastructure.di._research_organization import build_research_org_admin_repos
from cellar.infrastructure.di._screening import build_screening_admin_repos
from cellar.infrastructure.di._workspace_config import build_workspace_config_admin_repos
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _build_admin_repo_map(uow) -> dict:
    """Build the combined repo map for all Tier-1 admin-deletable entities.

    Called once per AdminHardDelete invocation (inside the active UoW) so
    that every repo shares the caller's transaction session.
    """
    repos: dict = {}
    repos.update(build_workspace_config_admin_repos(uow))
    repos.update(build_chemical_registration_admin_repos(uow))
    repos.update(build_screening_admin_repos(uow))
    repos.update(build_inventory_admin_repos(uow))
    repos.update(build_research_org_admin_repos(uow))
    return repos


def register_admin(container: Container) -> None:
    def _admin_hard_delete(c: Container) -> AdminHardDelete:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return AdminHardDelete(
            uow=uow,
            audit=c[AuditRecordingService],
            repos=_build_admin_repo_map,  # factory: (uow) -> repo map
            cascade_service=UoWBackedCascadeService(uow),
        )

    container.define(AdminHardDelete, _admin_hard_delete)

    def _cascade_preview(c: Container) -> CascadePreview:
        # Use a single UoW instance so the cascade service reads the same session.
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CascadePreview(
            uow=uow,
            cascade_service=UoWBackedCascadeService(uow),
        )

    container.define(CascadePreview, _cascade_preview)

    def _cascade_delete(c: Container) -> CascadeDelete:
        # Use a single UoW instance so the cascade service reads the same session.
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CascadeDelete(
            uow=uow,
            audit=c[AuditRecordingService],
            cascade_service=UoWBackedCascadeService(uow),
        )

    container.define(CascadeDelete, _cascade_delete)
