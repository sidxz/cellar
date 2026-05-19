"""Tests for ExcludedPointDetail VO."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionReason,
    ExclusionSource,
)
from cellar.domain.shared.errors import ValidationError


def test_constructs_with_required_fields_manual():
    d = ExcludedPointDetail(
        idx=3,
        source=ExclusionSource.MANUAL,
        excluded=True,
        reason=ExclusionReason.OUTLIER,
        author_id=uuid.uuid4(),
        ts=datetime(2026, 5, 19, 10, 0, 0),
    )
    assert d.idx == 3
    assert d.is_suggestion is False


def test_suggestion_is_unexcluded_auto_source():
    d = ExcludedPointDetail(
        idx=3,
        source=ExclusionSource.AUTO_3SIGMA,
        excluded=False,
        reason=ExclusionReason.AUTO_3SIGMA,
        author_id=None,
        ts=datetime(2026, 5, 19, 10, 0, 0),
    )
    assert d.is_suggestion is True


def test_manual_exclusion_requires_author_id():
    with pytest.raises(ValidationError, match="author_id required for manual"):
        ExcludedPointDetail(
            idx=3,
            source=ExclusionSource.MANUAL,
            excluded=True,
            reason=ExclusionReason.OUTLIER,
            author_id=None,
            ts=datetime(2026, 5, 19, 10, 0, 0),
        )


def test_auto_source_with_outlier_reason_rejected():
    # source MANUAL must NOT carry AUTO_3SIGMA reason
    with pytest.raises(ValidationError, match="AUTO_3SIGMA reason only valid for AUTO source"):
        ExcludedPointDetail(
            idx=3,
            source=ExclusionSource.MANUAL,
            excluded=True,
            reason=ExclusionReason.AUTO_3SIGMA,
            author_id=uuid.uuid4(),
            ts=datetime(2026, 5, 19, 10, 0, 0),
        )


def test_legacy_entry_with_null_idx_carries_concentration_and_response():
    d = ExcludedPointDetail(
        idx=None,
        source=ExclusionSource.AUTO_3SIGMA,
        excluded=True,
        reason=ExclusionReason.AUTO_3SIGMA,
        author_id=None,
        ts=datetime(2026, 5, 19, 10, 0, 0),
        concentration=1e-6,
        response=42.5,
    )
    assert d.idx is None
    assert d.concentration == 1e-6
    assert d.response == 42.5


def test_jsonb_round_trip_preserves_all_fields():
    original = ExcludedPointDetail(
        idx=2,
        source=ExclusionSource.MANUAL,
        excluded=True,
        reason=ExclusionReason.OUTLIER,
        author_id=uuid.uuid4(),
        ts=datetime(2026, 5, 19, 10, 0, 0),
        note="dispense spike",
    )
    raw = original.to_jsonb()
    restored = ExcludedPointDetail.from_jsonb(raw)
    assert restored == original


def test_jsonb_round_trip_legacy_entry_with_null_idx():
    original = ExcludedPointDetail(
        idx=None,
        source=ExclusionSource.AUTO_3SIGMA,
        excluded=True,
        reason=ExclusionReason.AUTO_3SIGMA,
        author_id=None,
        ts=datetime(2026, 5, 19, 10, 0, 0),
        concentration=1e-6,
        response=42.5,
    )
    raw = original.to_jsonb()
    restored = ExcludedPointDetail.from_jsonb(raw)
    assert restored == original
    assert raw["concentration"] == 1e-6
    assert raw["response"] == 42.5
    assert raw["idx"] is None
