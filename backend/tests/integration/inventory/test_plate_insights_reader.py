"""Integration test for SQLAlchemyPlateInsightsReader — org-scoped dashboard counts."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from cellar.application.inventory.plate_insights_reader import GroupSize
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    PlateGroupModel,
    RegisteredPlateModel,
    StorageLocationModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_insights_reader import (
    SQLAlchemyPlateInsightsReader,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_models import (
    LoanItemModel,
    PlateLoanModel,
)


async def _seed(session, ws: uuid.UUID, org_a: uuid.UUID, org_b: uuid.UUID) -> dict:
    """Org A: 3 plates (2 stored/1 depleted, 2 assay/1 mother, 2 in a named
    location + 1 unassigned, 2 in group "Vendor set" + 1 ungrouped), plus 1
    overdue open loan with a checked_out item and a returned item (now).
    Org B: 1 plate + 1 loan — noise that must never leak into org A's counts.
    """
    user = uuid.uuid4()
    location_id = uuid.uuid4()
    group_id = uuid.uuid4()

    session.add(
        StorageLocationModel(id=location_id, workspace_id=ws, name="Freezer 1", type="freezer")
    )
    session.add(
        PlateGroupModel(
            id=group_id, workspace_id=ws, owner_org_id=org_a, name="Vendor set", created_by=user
        )
    )
    await session.flush()  # parents before the plates that FK to them

    plate_rows = [
        ("stored", "assay", location_id, group_id),
        ("stored", "assay", location_id, group_id),
        ("depleted", "mother", None, None),
    ]
    for i, (status, plate_type, loc, grp) in enumerate(plate_rows):
        session.add(
            RegisteredPlateModel(
                id=uuid.uuid4(),
                workspace_id=ws,
                owner_org_id=org_a,
                barcode=f"PL-A-{i}",
                plate_label=f"PL-A-{i}",
                format="96",
                plate_type=plate_type,
                status=status,
                storage_location_id=loc,
                group_id=grp,
                registered_by=user,
            )
        )

    session.add(
        RegisteredPlateModel(
            id=uuid.uuid4(),
            workspace_id=ws,
            owner_org_id=org_b,
            barcode="PL-B-0",
            plate_label="PL-B-0",
            format="96",
            plate_type="assay",
            status="stored",
            registered_by=user,
        )
    )

    loan_a = uuid.uuid4()
    session.add(
        PlateLoanModel(
            id=loan_a,
            workspace_id=ws,
            owner_org_id=org_a,
            borrower_org_id=org_a,
            requested_by=user,
            due_date=date.today() - timedelta(days=1),
            status="open",
        )
    )
    await session.flush()  # loan before its items
    session.add(
        LoanItemModel(
            id=uuid.uuid4(),
            loan_id=loan_a,
            plate_id=uuid.uuid4(),
            status="checked_out",
            status_changed_at=datetime.now(UTC),
        )
    )
    session.add(
        LoanItemModel(
            id=uuid.uuid4(),
            loan_id=loan_a,
            plate_id=uuid.uuid4(),
            status="returned",
            status_changed_at=datetime.now(UTC),
        )
    )

    loan_b = uuid.uuid4()
    session.add(
        PlateLoanModel(
            id=loan_b,
            workspace_id=ws,
            owner_org_id=org_b,
            borrower_org_id=org_b,
            requested_by=user,
            status="open",
        )
    )
    await session.flush()  # loan before its item
    session.add(
        LoanItemModel(
            id=uuid.uuid4(),
            loan_id=loan_b,
            plate_id=uuid.uuid4(),
            status="requested",
            status_changed_at=datetime.now(UTC),
        )
    )

    await session.commit()
    return {"location_id": location_id, "group_id": group_id}


async def test_org_scoped_insights_counts_and_isolation(session_factory) -> None:
    ws = uuid.uuid4()
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as session:
        ids = await _seed(session, ws, org_a, org_b)

    reader = SQLAlchemyPlateInsightsReader(session_factory)
    data = await reader.get_insights(ws, org_a)

    assert data.total_plates == 3
    assert {b.key: b.count for b in data.by_status} == {"stored": 2, "depleted": 1}
    assert {b.key: b.count for b in data.by_type} == {"assay": 2, "mother": 1}

    by_name = {loc.name: (loc.location_id, loc.count) for loc in data.by_location}
    assert by_name["Freezer 1"] == (ids["location_id"], 2)
    assert by_name["Unassigned"] == (None, 1)

    assert data.group_sizes == [GroupSize(group_id=ids["group_id"], name="Vendor set", count=2)]

    assert data.open_loans == 1
    assert data.overdue_count == 1

    assert len(data.loan_activity_weekly) == 12
    *earlier_weeks, last_week = data.loan_activity_weekly
    assert last_week.requested == 1
    assert last_week.returned == 1
    assert all(w.requested == 0 and w.returned == 0 for w in earlier_weeks)

    # Org B's rows never leak into org A's counts, and vice versa.
    org_b_data = await reader.get_insights(ws, org_b)
    assert org_b_data.total_plates == 1
    assert org_b_data.open_loans == 1
    assert org_b_data.group_sizes == []
