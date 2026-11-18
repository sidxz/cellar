import uuid
from types import SimpleNamespace

from cellar.application.research_organization.column_descriptions import (
    describe_channels,
    readout_label,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    MeasurementBasis,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import SeedRun
from cellar.domain.shared.hit_criterion import InterceptKey


def _channel(**kw) -> CampaignChannel:
    base = dict(
        campaign_id=uuid.uuid4(),
        label="col",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    base.update(kw)
    return CampaignChannel(**base)


def test_primary_intercept_column_is_named_for_its_readout():
    assert readout_label(_channel(), "IC50") == "IC50"


def test_secondary_intercept_columns_of_one_readout_get_distinct_labels():
    ec90 = _channel(intercept_key=InterceptKey(kind="ec", level=90.0))
    ic99 = _channel(intercept_key=InterceptKey(kind="ic", level=99.0))
    assert readout_label(ec90, "EC50") == "EC90"
    assert readout_label(ic99, "IC50") == "IC99"
    assert readout_label(_channel(), "EC50") != readout_label(ec90, "EC50")


def test_readout_column_carries_its_normalization_layer():
    ch = _channel(
        source_kind=ChannelSourceKind.READOUT_DATA, normalization_applied="percent_inhibition"
    )
    assert readout_label(ch, "Signal") == "Signal (% Inhibition)"


def _described(channel: CampaignChannel, unit: str, readout_unit: str | None) -> str:
    """The rule part of ``channel``'s description, with one value cell in ``unit``."""
    campaign = Campaign.create(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )
    channel.campaign_id = campaign.id
    campaign.add_channel(channel)
    row = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    row.add_measurement(
        CampaignMeasurement(
            result_id=row.id,
            channel_id=channel.id,
            value=40.0,
            value_qualifier=ValueQualifier.EQ,
            unit=unit,
            protocol_name_snapshot="P",
            protocol_version_snapshot=1,
            contributing_run_ids=[uuid.uuid4(), uuid.uuid4()],
            basis=MeasurementBasis.MEASURED,
            concentration_series=channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE,
        )
    )
    campaign.add_result(row)
    readouts = {channel.readout_definition_id: SimpleNamespace(name="Signal", unit=readout_unit)}
    d = describe_channels(campaign, readouts)[channel.id]
    assert d.short_label.endswith(f" · {d.rule}")
    return d.rule


def test_rule_part_is_the_rule_a_readout_column_computes():
    """A single-point column computes a geometric mean of % values as a mean, and a
    best fit as the latest run; the description says what it computes."""
    gmean = _channel(
        source_kind=ChannelSourceKind.READOUT_DATA,
        normalization_applied="percent_inhibition",
        selection_rule=SelectionRule.GEOMETRIC_MEAN,
    )
    assert _described(gmean, "%", "RFU") == "mean across runs"
    best = _channel(
        source_kind=ChannelSourceKind.READOUT_DATA, selection_rule=SelectionRule.BEST_R_SQUARED
    )
    assert _described(best, "µM", "µM") == "latest run"


def test_rule_part_of_a_dose_response_column_is_as_configured():
    gmean = _channel(selection_rule=SelectionRule.GEOMETRIC_MEAN)
    assert _described(gmean, "µM", "µM") == "geometric mean"


def _stage_column_description(*, stage_runs: int, contributing: int, all_runs: bool = False):
    """A stage column whose stage holds ``stage_runs`` runs, ``contributing`` of
    which fed its one value."""
    campaign = Campaign.create(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )
    stage = CampaignStage(campaign_id=campaign.id, name="Retest", display_order=0)
    campaign.add_stage(stage)
    ch = _channel(campaign_id=campaign.id, stage_id=stage.id, resolve_from_all_runs=all_runs)
    campaign.add_channel(ch)
    campaign.seed_runs = [
        SeedRun(run_id=uuid.uuid4(), protocol_id=ch.protocol_id, stage_ids=(stage.id,))
        for _ in range(stage_runs)
    ]
    row = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    row.add_measurement(
        CampaignMeasurement(
            result_id=row.id,
            channel_id=ch.id,
            value=40.0,
            value_qualifier=ValueQualifier.EQ,
            unit="µM",
            protocol_name_snapshot="P",
            protocol_version_snapshot=1,
            contributing_run_ids=[uuid.uuid4() for _ in range(contributing)],
            basis=MeasurementBasis.MEASURED,
            concentration_series=True,
        )
    )
    campaign.add_result(row)
    readouts = {ch.readout_definition_id: SimpleNamespace(name="IC50", unit="µM")}
    return describe_channels(campaign, readouts)[ch.id]


def test_runs_part_reads_n_of_m_when_some_runs_set_aside():
    d = _stage_column_description(stage_runs=3, contributing=2)
    assert "2 of 3 runs" in d.short_label
    assert (d.run_count, d.scope_run_count) == (2, 3)
    one = _stage_column_description(stage_runs=2, contributing=1)
    assert "1 of 2 runs" in one.short_label


def test_runs_part_plain_when_all_runs_contribute():
    d = _stage_column_description(stage_runs=2, contributing=2)
    assert " 2 runs" in f" {d.short_label}" and " of " not in d.short_label
    assert d.scope_run_count == 2


def test_all_runs_column_has_no_scope_count():
    d = _stage_column_description(stage_runs=3, contributing=2, all_runs=True)
    assert d.scope_run_count is None
    assert "2 runs" in d.short_label and " of 3" not in d.short_label
