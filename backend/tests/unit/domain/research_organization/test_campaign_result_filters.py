"""A measurement-range filter compares units by canonical spelling, never converting."""

import uuid

import pytest

from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_result_filters import MeasurementFilter
from cellar.domain.research_organization.enums import ValueQualifier


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
