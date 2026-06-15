from __future__ import annotations

import uuid

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar


def test_activity_scalar_holds_value_and_snapshot():
    mid = uuid.uuid4()
    s = ActivityScalar(
        molecule_id=mid,
        scalar=0.42,
        unit="uM",
        qualifier=None,
        source="dose_response",
        snapshot={"value": 0.42},
    )
    assert s.molecule_id == mid
    assert s.scalar == 0.42
    assert s.snapshot == {"value": 0.42}


def test_snapshot_defaults_to_empty_dict():
    s = ActivityScalar(
        molecule_id=uuid.uuid4(), scalar=1.0, unit=None, qualifier=None, source="readout"
    )
    assert s.snapshot == {}
