"""SQLAlchemy repository for PlateLoan aggregates."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from cellar.domain.inventory.enums import ACTIVE_LOAN_ITEM_STATUSES, LoanItemStatus, LoanStatus
from cellar.domain.inventory.plate_loan import LoanItem, PlateLoan
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_models import (
    LoanItemModel,
    PlateLoanModel,
)

_ACTIVE_ITEM_STATUS_VALUES = [s.value for s in ACTIVE_LOAN_ITEM_STATUSES]


class SQLAlchemyPlateLoanRepository(SQLAlchemyRepository[PlateLoan, PlateLoanModel]):
    model_class = PlateLoanModel

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None = None,
        owner_org_id: uuid.UUID | None = None,
        borrower_org_id: uuid.UUID | None = None,
        requested_by: uuid.UUID | None = None,
        plate_id: uuid.UUID | None = None,
        overdue: bool = False,
    ) -> list[PlateLoan]:
        stmt = select(PlateLoanModel).where(PlateLoanModel.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(PlateLoanModel.status == status)
        if owner_org_id is not None:
            stmt = stmt.where(PlateLoanModel.owner_org_id == owner_org_id)
        if borrower_org_id is not None:
            stmt = stmt.where(PlateLoanModel.borrower_org_id == borrower_org_id)
        if requested_by is not None:
            stmt = stmt.where(PlateLoanModel.requested_by == requested_by)
        if plate_id is not None:
            stmt = stmt.where(
                PlateLoanModel.id.in_(
                    select(LoanItemModel.loan_id).where(LoanItemModel.plate_id == plate_id)
                )
            )
        if overdue:
            stmt = stmt.where(
                PlateLoanModel.status == LoanStatus.OPEN.value,
                PlateLoanModel.due_date.isnot(None),
                PlateLoanModel.due_date < date.today(),
            )
        stmt = stmt.order_by(PlateLoanModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def active_plate_ids(
        self, workspace_id: uuid.UUID, plate_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not plate_ids:
            return set()
        stmt = (
            select(LoanItemModel.plate_id)
            .join(PlateLoanModel, LoanItemModel.loan_id == PlateLoanModel.id)
            .where(
                PlateLoanModel.workspace_id == workspace_id,
                LoanItemModel.plate_id.in_(plate_ids),
                LoanItemModel.status.in_(_ACTIVE_ITEM_STATUS_VALUES),
            )
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def borrowed_plate_ids(
        self, workspace_id: uuid.UUID, borrower_org_id: uuid.UUID
    ) -> set[uuid.UUID]:
        stmt = (
            select(LoanItemModel.plate_id)
            .join(PlateLoanModel, LoanItemModel.loan_id == PlateLoanModel.id)
            .where(
                PlateLoanModel.workspace_id == workspace_id,
                PlateLoanModel.borrower_org_id == borrower_org_id,
                LoanItemModel.status.in_(_ACTIVE_ITEM_STATUS_VALUES),
            )
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def _to_domain(self, model: PlateLoanModel) -> PlateLoan:
        items = [
            LoanItem(
                id=item.id,
                loan_id=item.loan_id,
                plate_id=item.plate_id,
                status=LoanItemStatus(item.status),
                status_changed_at=item.status_changed_at,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in model.items
        ]
        return PlateLoan(
            id=model.id,
            workspace_id=model.workspace_id,
            owner_org_id=model.owner_org_id,
            borrower_org_id=model.borrower_org_id,
            requested_by=model.requested_by,
            approved_by=model.approved_by,
            due_date=model.due_date,
            notes=model.notes,
            status=LoanStatus(model.status),
            closed_at=model.closed_at,
            items=items,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: PlateLoan) -> PlateLoanModel:
        model = PlateLoanModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            owner_org_id=aggregate.owner_org_id,
            borrower_org_id=aggregate.borrower_org_id,
            requested_by=aggregate.requested_by,
            approved_by=aggregate.approved_by,
            due_date=aggregate.due_date,
            notes=aggregate.notes,
            status=aggregate.status.value,
            closed_at=aggregate.closed_at,
            version=aggregate.version,
        )
        model.items = [self._item_to_model(i) for i in aggregate.items]
        return model

    def _update_model(self, model: PlateLoanModel, aggregate: PlateLoan) -> None:
        # owner_org_id/borrower_org_id/requested_by/due_date/notes are set
        # once at PlateLoan.request() and have no domain setter — excluded
        # here, same rationale as Shipment's destination_org_id/sender_id.
        model.approved_by = aggregate.approved_by
        model.status = aggregate.status.value
        model.closed_at = aggregate.closed_at
        model.items = [self._item_to_model(i) for i in aggregate.items]

    @staticmethod
    def _item_to_model(item: LoanItem) -> LoanItemModel:
        return LoanItemModel(
            id=item.id,
            loan_id=item.loan_id,
            plate_id=item.plate_id,
            status=item.status.value,
            status_changed_at=item.status_changed_at,
        )
