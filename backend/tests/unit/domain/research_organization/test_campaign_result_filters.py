"""A measurement-range filter compares units by canonical spelling, never converting."""

import uuid

import pytest

from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_result_filters import MeasurementFilter
from cellar.domain.research_organization.enums import QcVerdict, ValueQualifier


def _row_with_unit(channel_id: uuid.UUID, unit: str) -> CampaignResult:
    row = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    row.add_measurement(
        CampaignMeasurement(
            result_id=row.id,
            channel_id=channel_id,
            value=2.0,
            value_qualifier=ValueQualifier.EQ,
            unit=unit,
            protocol_name_snapshot="x",
            protocol_version_snapshot=1,
        )
    )
    return row


@pytest.mark.parametrize(
    "filter_unit,cell_unit,expected",
    [
        ("µM", "uM", True),  # frozen snapshot keeps the old spelling
        ("uM", "µM", True),
        ("µM", "μM", True),  # Greek mu
        ("µM", "µM", True),
        ("nM", "µM", False),  # different unit: no conversion
        ("mM", "µM", False),
    ],
)
def test_unit_match_ignores_spelling_variants(filter_unit, cell_unit, expected):
    channel = uuid.uuid4()
    row = _row_with_unit(channel, cell_unit)
    flt = MeasurementFilter(channel_id=channel, minimum=1, maximum=3, unit=filter_unit)
    assert flt.matches(row) is expected


def _cell_row(channel_id, qualifier, value, verdict=None):
    row = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    row.add_measurement(
        CampaignMeasurement(
            result_id=row.id,
            channel_id=channel_id,
            value=value,
            value_qualifier=qualifier,
            unit="uM",
            protocol_name_snapshot="x",
            protocol_version_snapshot=1,
            qc_verdict=verdict,
        )
    )
    return row


def test_qc_verified_matches_verified_only():
    ch = uuid.uuid4()
    flt = MeasurementFilter(channel_id=ch, qc="verified")
    assert flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0, QcVerdict.VERIFIED))
    assert not flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0, QcVerdict.FAILED))
    assert not flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0))


def test_qc_failed_matches_failed_only():
    ch = uuid.uuid4()
    flt = MeasurementFilter(channel_id=ch, qc="failed")
    assert flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0, QcVerdict.FAILED))
    assert not flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0, QcVerdict.VERIFIED))
    assert not flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0))


def test_qc_not_tested_matches_result_cells_without_verdict():
    ch = uuid.uuid4()
    flt = MeasurementFilter(channel_id=ch, qc="not_tested")
    assert flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0))
    assert not flt.matches(_cell_row(ch, ValueQualifier.EQ, 2.0, QcVerdict.VERIFIED))
    # An untested ND (no result to judge) is not "not tested".
    assert not flt.matches(_cell_row(ch, ValueQualifier.ND, None))


@pytest.mark.parametrize("old", ["passed", "unknown"])
def test_old_qc_values_rejected(old):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MeasurementFilter(channel_id=uuid.uuid4(), qc=old)
