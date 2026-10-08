"""Every column that stores a protocol name must hold the longest name the policy allows."""

from cellar.domain.shared.protocol_naming import MAX_NAME_LENGTH
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignMeasurementModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import ProtocolModel


def test_protocol_name_columns_fit_the_longest_name():
    for column in (
        ProtocolModel.__table__.c.name,
        ProtocolModel.__table__.c.name_base,
        CampaignMeasurementModel.__table__.c.protocol_name_snapshot,
    ):
        assert column.type.length >= MAX_NAME_LENGTH, column
