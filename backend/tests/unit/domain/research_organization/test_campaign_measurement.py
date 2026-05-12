import uuid
from datetime import date

import pytest

from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.enums import HitCall, ValueQualifier
from cellar.domain.shared.errors import ValidationError


def test_minimum_measurement():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="EGFR Binding",
        protocol_version_snapshot=3,
    )
    assert m.value == 42.0
    assert m.hit_call is None
    assert m.is_manual_override is False
    assert m.id is not None


def test_nd_measurement_has_no_value():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.value is None


def test_excluded_qualifier_clears_value():
    """If a cell is excluded, value is forced to None."""
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EXCLUDED,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.value is None


def test_eq_qualifier_requires_value():
    with pytest.raises(ValidationError, match="numeric value"):
        CampaignMeasurement(
            result_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            value=None,
            value_qualifier=ValueQualifier.EQ,
            unit="nM",
            protocol_name_snapshot="x",
            protocol_version_snapshot=1,
        )


def test_lt_qualifier_requires_value():
    with pytest.raises(ValidationError):
        CampaignMeasurement(
            result_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            value=None,
            value_qualifier=ValueQualifier.LT,
            unit="nM",
            protocol_name_snapshot="x",
            protocol_version_snapshot=1,
        )


def test_empty_unit_rejected_for_numeric_qualifier():
    with pytest.raises(ValidationError, match="unit"):
        CampaignMeasurement(
            result_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            value=42.0,
            value_qualifier=ValueQualifier.EQ,
            unit="",
            protocol_name_snapshot="x",
            protocol_version_snapshot=1,
        )


def test_empty_unit_accepted_for_nd_qualifier():
    """ND placeholders have no real unit — empty string allowed (B7)."""
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.unit == ""
    assert m.value is None


def test_empty_unit_accepted_for_excluded_qualifier():
    """Excluded cells have no real unit — empty string allowed (B7)."""
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,  # forced to None by post_init
        value_qualifier=ValueQualifier.EXCLUDED,
        unit="",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.value is None
    assert m.unit == ""


def test_audit_snapshot_fields_default_to_none():
    """New B6/B8 fields default to None and persist as set."""
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.override_reason is None
    assert m.test_concentration_value is None
    assert m.test_concentration_unit is None
    assert m.replicate_count is None
    assert m.qc_pass is None
    assert m.contributing_run_ids is None


def test_audit_snapshot_fields_set_through_constructor():
    rid1, rid2 = uuid.uuid4(), uuid.uuid4()
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
        override_reason="QC fail on plate 3",
        test_concentration_value=10.0,
        test_concentration_unit="uM",
        replicate_count=3,
        qc_pass=True,
        contributing_run_ids=[rid1, rid2],
    )
    assert m.override_reason == "QC fail on plate 3"
    assert m.test_concentration_value == 10.0
    assert m.test_concentration_unit == "uM"
    assert m.replicate_count == 3
    assert m.qc_pass is True
    assert m.contributing_run_ids == [rid1, rid2]


def test_mark_manual_override_with_reason():
    """mark_manual_override accepts an optional reason (B8)."""
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=10.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    m.mark_manual_override(reason="QC fail on plate 3")
    assert m.is_manual_override is True
    assert m.override_reason == "QC fail on plate 3"


def test_with_hit_call_and_source():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=2,
        hit_call=HitCall.HIT,
        source_run_id=uuid.uuid4(),
        source_curve_id=uuid.uuid4(),
        run_date_snapshot=date(2026, 5, 1),
    )
    assert m.hit_call == HitCall.HIT
    assert m.run_date_snapshot == date(2026, 5, 1)


def test_mark_override_flips_flag():
    m = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=10.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    assert m.is_manual_override is False
    m.mark_manual_override()
    assert m.is_manual_override is True
