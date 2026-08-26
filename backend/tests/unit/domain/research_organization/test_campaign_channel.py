import uuid

import pytest

from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.shared.errors import ValidationError



def test_channel_label_required():
    with pytest.raises(ValidationError):
        CampaignChannel(
            campaign_id=uuid.uuid4(),
            label="   ",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
        )


def test_channel_label_stripped():
    ch = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="  IC50  ",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    assert ch.label == "IC50"


def test_channel_negative_display_order_rejected():
    with pytest.raises(ValidationError, match="display_order"):
        CampaignChannel(
            campaign_id=uuid.uuid4(),
            label="x",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=-1,
        )



def test_channel_qc_filter_jsonable():
    ch = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="x",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter={"min_z_prime": 0.5, "require_approved": True},
    )
    assert ch.qc_filter == {"min_z_prime": 0.5, "require_approved": True}
