"""Admin context DI bindings."""

from __future__ import annotations

from lagom import Container

from chem_vault.application.admin.admin_hard_delete import AdminHardDelete
from chem_vault.application.audit.audit_recording_service import AuditRecordingService
from chem_vault.application.shared.unit_of_work import UnitOfWork


def register_admin(container: Container) -> None:
    container.define(
        AdminHardDelete,
        lambda c: AdminHardDelete(
            uow=c[UnitOfWork],
            audit=c[AuditRecordingService],
            container=c,
        ),
    )
