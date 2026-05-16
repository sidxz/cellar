"""SQLAlchemy repository for ExportJob aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, select

from cellar.domain.export.enums import ExportFormat, ExportSource, ExportStatus
from cellar.domain.export.export_job import ExportJob
from cellar.infrastructure.persistence.sqlalchemy.export.export_job_model import ExportJobModel
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SqlAlchemyExportJobRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def save(self, job: ExportJob) -> None:
        session = self._uow.session
        existing = await session.get(ExportJobModel, job.id)
        if existing is None:
            session.add(_to_model(job))
        else:
            _apply_to_model(existing, job)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, job_id: uuid.UUID
    ) -> ExportJob | None:
        session = self._uow.session
        stmt = select(ExportJobModel).where(
            ExportJobModel.id == job_id,
            ExportJobModel.workspace_id == workspace_id,
        )
        model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list_in_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        cursor_requested_at: datetime | None = None,
    ) -> list[ExportJob]:
        session = self._uow.session
        stmt = (
            select(ExportJobModel)
            .where(ExportJobModel.workspace_id == workspace_id)
            .order_by(desc(ExportJobModel.requested_at))
            .limit(limit)
        )
        if cursor_requested_at is not None:
            stmt = stmt.where(ExportJobModel.requested_at < cursor_requested_at)
        return [_to_domain(m) for m in (await session.execute(stmt)).scalars().all()]

    async def find_expired_ready(self, before: datetime, *, limit: int = 100) -> list[ExportJob]:
        session = self._uow.session
        stmt = (
            select(ExportJobModel)
            .where(
                ExportJobModel.status == ExportStatus.READY.value,
                ExportJobModel.expires_at.isnot(None),
                ExportJobModel.expires_at < before,
            )
            .limit(limit)
        )
        return [_to_domain(m) for m in (await session.execute(stmt)).scalars().all()]


def _to_model(job: ExportJob) -> ExportJobModel:
    return ExportJobModel(
        id=job.id,
        workspace_id=job.workspace_id,
        requested_by=job.requested_by,
        source=job.source.value,
        format=job.format.value,
        query_snapshot=job.query_snapshot,
        status=job.status.value,
        row_count=job.row_count,
        progress=job.progress,
        file_key=job.file_key,
        byte_size=job.byte_size,
        content_type=job.content_type,
        filename=job.filename,
        error_message=job.error_message,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        version=job.version,
    )


def _apply_to_model(model: ExportJobModel, job: ExportJob) -> None:
    model.status = job.status.value
    model.row_count = job.row_count
    model.progress = job.progress
    model.file_key = job.file_key
    model.byte_size = job.byte_size
    model.content_type = job.content_type
    model.filename = job.filename
    model.error_message = job.error_message
    model.started_at = job.started_at
    model.completed_at = job.completed_at
    model.expires_at = job.expires_at
    model.version = job.version


def _to_domain(model: ExportJobModel) -> ExportJob:
    return ExportJob(
        id=model.id,
        workspace_id=model.workspace_id,
        requested_by=model.requested_by,
        source=ExportSource(model.source),
        format=ExportFormat(model.format),
        query_snapshot=model.query_snapshot,
        filename=model.filename or "",
        status=ExportStatus(model.status),
        row_count=model.row_count,
        progress=model.progress,
        file_key=model.file_key,
        byte_size=model.byte_size,
        content_type=model.content_type,
        error_message=model.error_message,
        requested_at=model.requested_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        expires_at=model.expires_at,
        version=model.version,
    )
