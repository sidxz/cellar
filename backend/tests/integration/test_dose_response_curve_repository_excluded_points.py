"""Integration test: ExcludedPointDetail round-trips through the DR curve repo.

A curve persisted with a mix of MANUAL + AUTO_3SIGMA ExcludedPointDetail entries
(including a legacy entry with idx=None and concentration/response baked in)
comes back from the repository as typed VOs with every field intact.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionReason,
    ExclusionSource,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from tests.fixtures.dose_response_curves import seed_curve


@pytest.mark.asyncio
class TestExcludedPointDetailRoundTrip:
    async def test_typed_entries_round_trip_intact(self, uow, workspace_id):
        author = uuid.uuid4()
        ts = datetime(2026, 5, 19, 10, 0, 0)
        async with uow:
            curve = await seed_curve(uow, workspace_id=workspace_id)
            curve.excluded_points = [
                ExcludedPointDetail(
                    idx=2,
                    source=ExclusionSource.MANUAL,
                    excluded=True,
                    reason=ExclusionReason.OUTLIER,
                    author_id=author,
                    ts=ts,
                    note="dispense spike",
                ),
                ExcludedPointDetail(
                    idx=5,
                    source=ExclusionSource.AUTO_3SIGMA,
                    excluded=False,
                    reason=ExclusionReason.AUTO_3SIGMA,
                    author_id=None,
                    ts=ts,
                ),
                # Legacy-style: idx=None with concentration/response carried.
                ExcludedPointDetail(
                    idx=None,
                    source=ExclusionSource.AUTO_3SIGMA,
                    excluded=True,
                    reason=ExclusionReason.AUTO_3SIGMA,
                    author_id=None,
                    ts=ts,
                    concentration=1e-6,
                    response=42.5,
                ),
            ]
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            await repo.save(curve)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            fetched_list = await repo.find_by_ids(workspace_id, [curve.id])

        assert len(fetched_list) == 1
        fetched = fetched_list[0]
        assert fetched.excluded_points is not None
        assert len(fetched.excluded_points) == 3
        for entry in fetched.excluded_points:
            assert isinstance(entry, ExcludedPointDetail)

        by_idx = {e.idx: e for e in fetched.excluded_points if e.idx is not None}
        assert by_idx[2].source == ExclusionSource.MANUAL
        assert by_idx[2].excluded is True
        assert by_idx[2].reason == ExclusionReason.OUTLIER
        assert by_idx[2].note == "dispense spike"
        assert by_idx[2].author_id == author
        assert by_idx[2].ts == ts

        assert by_idx[5].source == ExclusionSource.AUTO_3SIGMA
        assert by_idx[5].excluded is False
        assert by_idx[5].is_suggestion is True

        legacy = [e for e in fetched.excluded_points if e.idx is None]
        assert len(legacy) == 1
        assert legacy[0].concentration == 1e-6
        assert legacy[0].response == 42.5
        assert legacy[0].excluded is True

    async def test_raw_dict_legacy_producers_still_persist(self, uow, workspace_id):
        """curve_fitter.py still emits raw dicts pre-Task 2.7; the write path
        must tolerate them and the read path must hydrate them to VOs.

        We simulate the legacy producer by directly assigning a list of dicts
        in the post-migration shape (idx=null, concentration/response set).
        """
        async with uow:
            curve = await seed_curve(uow, workspace_id=workspace_id)
            # Bypass the typed setter via dict shape that curve_fitter emits.
            # The migration-041 backfill normalizes any legacy row to the full
            # shape, so we use that shape here.
            curve.excluded_points = [  # type: ignore[assignment]
                {
                    "idx": None,
                    "concentration": 5e-7,
                    "response": 13.0,
                    "source": "auto_3sigma",
                    "excluded": True,
                    "reason": "auto_3sigma",
                    "note": None,
                    "author_id": None,
                    "ts": "2026-05-19T10:00:00Z",
                }
            ]
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            await repo.save(curve)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            fetched_list = await repo.find_by_ids(workspace_id, [curve.id])

        assert len(fetched_list) == 1
        fetched = fetched_list[0]
        assert fetched.excluded_points is not None
        assert len(fetched.excluded_points) == 1
        entry = fetched.excluded_points[0]
        assert isinstance(entry, ExcludedPointDetail)
        assert entry.idx is None
        assert entry.concentration == 5e-7
        assert entry.response == 13.0
        assert entry.source == ExclusionSource.AUTO_3SIGMA
        assert entry.excluded is True

    async def test_none_round_trips_as_none(self, uow, workspace_id):
        async with uow:
            curve = await seed_curve(uow, workspace_id=workspace_id)
            curve.excluded_points = None
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            await repo.save(curve)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            fetched_list = await repo.find_by_ids(workspace_id, [curve.id])

        assert len(fetched_list) == 1
        assert fetched_list[0].excluded_points is None
