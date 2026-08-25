"""SQLAlchemy repository for Comment aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.infrastructure.persistence.sqlalchemy.base_repository import SQLAlchemyRepository
from cellar.infrastructure.persistence.sqlalchemy.inventory.comment_models import CommentModel


class SQLAlchemyCommentRepository(SQLAlchemyRepository[Comment, CommentModel]):
    model_class = CommentModel

    async def list_for_target(
        self, workspace_id: uuid.UUID, target_type: CommentTarget, target_id: uuid.UUID
    ) -> list[Comment]:
        stmt = (
            select(CommentModel)
            .where(
                CommentModel.workspace_id == workspace_id,
                CommentModel.target_type == target_type.value,
                CommentModel.target_id == target_id,
            )
            .order_by(CommentModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_for_loan(self, workspace_id: uuid.UUID, loan_id: uuid.UUID) -> list[Comment]:
        stmt = (
            select(CommentModel)
            .where(CommentModel.workspace_id == workspace_id, CommentModel.loan_id == loan_id)
            .order_by(CommentModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    # --- Mapping ---

    def _to_domain(self, model: CommentModel) -> Comment:
        return Comment(
            id=model.id,
            workspace_id=model.workspace_id,
            target_type=CommentTarget(model.target_type),
            target_id=model.target_id,
            body=model.body,
            author_id=model.author_id,
            author_name=model.author_name,
            loan_id=model.loan_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Comment) -> CommentModel:
        model = CommentModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            target_type=aggregate.target_type.value,
            target_id=aggregate.target_id,
            loan_id=aggregate.loan_id,
            body=aggregate.body,
            author_id=aggregate.author_id,
            author_name=aggregate.author_name,
            version=aggregate.version,
        )
        if aggregate.created_at is not None:
            model.created_at = aggregate.created_at  # legacy importer supplies history
        return model

    def _update_model(self, model: CommentModel, aggregate: Comment) -> None:
        # Append-only: nothing mutable after insert.
        return None
