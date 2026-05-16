"""Export bounded context bindings: export jobs."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.domain.export.repository import ExportJobRepository
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_repository import (
    SqlAlchemyExportJobRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_export(container: Container) -> None:
    def _export_job_repo(c: Container) -> ExportJobRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SqlAlchemyExportJobRepository(uow)  # type: ignore[return-value]

    container.define(ExportJobRepository, _export_job_repo)
