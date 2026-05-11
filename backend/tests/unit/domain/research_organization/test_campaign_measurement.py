import uuid
from datetime import date

import pytest

from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.enums import HitCall, ValueQualifier
from chem_vault.domain.shared.errors import ValidationError


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


def test_empty_unit_rejected():
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
