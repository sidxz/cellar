"""Stage-scoped campaign cases (spec §12): each stage's columns read only that
stage's runs, every add or removal recomputes the stage's columns over all of its
runs, and nothing at one stage moves another stage's values or tallies."""

from __future__ import annotations

import copy
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.research_organization.add_campaign_channel import (
    AddCampaignChannel,
    AddCampaignChannelCommand,
)
from cellar.application.research_organization.add_results_from_runs import (
    AddResultsFromRuns,
    AddResultsFromRunsCommand,
)
from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
    PreviewRunImport,
    PreviewRunImportQuery,
)
from cellar.application.research_organization.remove_run_from_stage import (
    RemoveRunFromStage,
    RemoveRunFromStageCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    UnresolvedReason,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.research_organization.stage_evaluation import (
    evaluate_stages,
    tally_stage_counts,
)
from cellar.domain.shared.hit_criterion import HitCriterion
from tests.unit.application.research_organization._helpers import (
    FakeRunData,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
    reading,
)

PROTO = uuid.uuid4()
PCT = uuid.uuid4()  # % inhibition, single concentration
IC50 = uuid.uuid4()  # dose-response
TEN_UM = Concentration(10.0, "µM")
X = uuid.uuid4()
Y = uuid.uuid4()


def pct(
    rule: SelectionRule = SelectionRule.LATEST_RUN,
    threshold: float | None = 50.0,
    *,
    protocol: uuid.UUID = PROTO,
    readout: uuid.UUID = PCT,
) -> ChannelImportConfig:
    return ChannelImportConfig(
        protocol_id=protocol,
        readout_definition_id=readout,
        label="% inhibition",
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=rule,
        hit_threshold=(
            HitCriterion(readout_name="% inhibition", operator="gte", value=threshold)
            if threshold is not None
            else None
        ),
    )


def ic50() -> ChannelImportConfig:
    return ChannelImportConfig(
        protocol_id=PROTO,
        readout_definition_id=IC50,
        label="IC50",
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_RUN,
        hit_threshold=HitCriterion(readout_name="IC50", operator="lte", value=10.0),
    )


class World:
    """One draft campaign, its runs and their readings, driven through the use cases."""

    def __init__(self) -> None:
        self.auth = fake_auth()
        self.campaign = Campaign.create(
            workspace_id=self.auth.workspace_id,
            project_id=uuid.uuid4(),
            name="Screen",
            description=None,
            created_by=uuid.uuid4(),
        )
        self.data = FakeRunData()
        self.runs: dict[uuid.UUID, SimpleNamespace] = {}

    def stage(self, name: str, parent: uuid.UUID | None = None) -> uuid.UUID:
        s = CampaignStage(
            campaign_id=self.campaign.id,
            name=name,
            display_order=len(self.campaign.stages),
            parent_stage_id=parent,
        )
        self.campaign.add_stage(s)
        return s.id

    def run(self, *readings: tuple, protocol: uuid.UUID = PROTO, day: int = 1) -> uuid.UUID:
        """A run; each reading is ``(readout, molecule, value[, dose])``."""
        rid = uuid.uuid4()
        self.runs[rid] = SimpleNamespace(id=rid, protocol_id=protocol)
        for readout, mol, value, *dose in readings:
            self.data.add(
                readout,
                reading(
                    mol,
                    value,
                    rid,
                    run_date=date(2026, 1, day),
                    dose=dose[0] if dose else TEN_UM,
                ),
            )
        return rid

    def _run_repo(self) -> AsyncMock:
        repo = AsyncMock()

        async def find_by_ids(ws, ids):
            return {i: self.runs[i] for i in ids if i in self.runs}

        repo.find_by_ids = AsyncMock(side_effect=find_by_ids)
        return repo

    async def add(self, run_ids, stage_id, *configs, scope: str = "all", campaign=None, **kw):
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign or self.campaign),
            run_repo=self._run_repo(),
            query=self.data,
            dispatcher=AsyncMock(),
        )
        out = await uc(
            AddResultsFromRunsCommand(
                workspace_id=self.auth.workspace_id,
                campaign_id=self.campaign.id,
                run_ids=list(run_ids),
                channel_configs=list(configs),
                scope=scope,  # type: ignore[arg-type]
                stage_id=stage_id,
                **kw,
            ),
            auth=self.auth,
        )
        assert isinstance(out, Success), out
        return out.unwrap()

    async def preview(self, run_ids, stage_id, *configs, **kw) -> dict:
        """Previews against a copy: the use case never saves, and the commit that
        follows must start from the same campaign."""
        molecules = AsyncMock()
        molecules.find_by_ids = AsyncMock(
            side_effect=lambda ws, ids: [
                SimpleNamespace(
                    id=m,
                    registration_number=SimpleNamespace(value=str(m)),
                    name=None,
                    structure=None,
                )
                for m in ids
            ]
        )
        campaign_repo = make_campaign_repo(find_in_ws=copy.deepcopy(self.campaign))
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            run_repo=self._run_repo(),
            molecule_repo=molecules,
            query=self.data,
        )
        out = await uc(
            PreviewRunImportQuery(
                workspace_id=self.auth.workspace_id,
                campaign_id=self.campaign.id,
                run_ids=list(run_ids),
                channel_configs=list(configs),
                stage_id=stage_id,
                **kw,
            ),
            auth=self.auth,
        )
        assert isinstance(out, Success), out
        campaign_repo.save.assert_not_called()
        return out.unwrap()

    async def remove(self, stage_id: uuid.UUID, run_id: uuid.UUID) -> None:
        uc = RemoveRunFromStage(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=self.campaign),
            query=self.data,
            dispatcher=AsyncMock(),
        )
        out = await uc(
            RemoveRunFromStageCommand(
                workspace_id=self.auth.workspace_id,
                campaign_id=self.campaign.id,
                stage_id=stage_id,
                run_id=run_id,
            ),
            auth=self.auth,
        )
        assert isinstance(out, Success), out

    def column(self, stage_id: uuid.UUID | None, readout: uuid.UUID = PCT):
        return next(
            c
            for c in self.campaign.channels
            if c.stage_id == stage_id and c.readout_definition_id == readout
        )

    def cell(
        self, mol: uuid.UUID, stage_id: uuid.UUID | None, readout: uuid.UUID = PCT
    ) -> CampaignMeasurement:
        row = next(r for r in self.campaign.results if r.molecule_id == mol)
        m = row.find_measurement(self.column(stage_id, readout).id)
        assert m is not None
        return m

    def stage_cells(self, stage_id: uuid.UUID) -> dict:
        ids = {c.id for c in self.campaign.channels_of_stage(stage_id)}
        return {
            (r.molecule_id, m.channel_id): copy.deepcopy(m)
            for r in self.campaign.results
            for m in r.measurements
            if m.channel_id in ids
        }

    def tally(self, stage_id: uuid.UUID) -> dict[str, int]:
        return tally_stage_counts(self.campaign, evaluate_stages(self.campaign))[stage_id]


# ---------------------------------------------------------------------------
# Cases A-H, L (spec §12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_a_primary_unchanged_after_retest() -> None:
    w = World()
    primary = w.stage("Primary")
    retest = w.stage("Retest", parent=primary)
    await w.add([w.run((PCT, X, 62.0))], primary, pct())
    before = w.tally(primary)

    retests = [w.run((PCT, X, v), day=d) for d, v in ((2, 30.0), (3, 35.0), (4, 40.0))]
    await w.add(retests, retest, pct(SelectionRule.MEAN_ACROSS_RUNS))

    assert w.cell(X, primary).value == 62.0
    second = w.cell(X, retest)
    assert second.value == pytest.approx(35.0)
    assert sorted(second.contributing_run_ids) == sorted(retests)
    assert w.tally(primary) == before
    assert before["hit"] == 1
    assert w.tally(retest)["miss"] == 1


@pytest.mark.asyncio
async def test_case_c_dose_response_runs_do_not_move_stage_1() -> None:
    w = World()
    primary = w.stage("Primary")
    dose_response = w.stage("Dose response", parent=primary)
    await w.add([w.run((PCT, X, 62.0))], primary, pct())
    before_cells, before = w.stage_cells(primary), w.tally(primary)

    dr_run = w.run(
        (PCT, X, 20.0, Concentration(0.1, "µM")),
        (PCT, X, 50.0, Concentration(1.0, "µM")),
        (PCT, X, 90.0, TEN_UM),
        day=9,
    )
    w.data.add(
        IC50, reading(X, 2.5, dr_run, run_date=date(2026, 1, 9), unit="µM", curve_class="full")
    )
    await w.add([dr_run], dose_response, ic50(), pct())

    assert w.stage_cells(primary) == before_cells
    assert w.tally(primary) == before
    assert w.cell(X, dose_response, IC50).value == 2.5
    # Its per-concentration % inhibition never reaches a single-concentration column.
    assert w.cell(X, dose_response, PCT).value is None


@pytest.mark.asyncio
async def test_case_d_ten_runs_one_value() -> None:
    w = World()
    primary = w.stage("Primary")
    runs = [w.run((PCT, X, 10.0 * i), day=i) for i in range(1, 11)]
    await w.add(runs, primary, pct(SelectionRule.MEAN_ACROSS_RUNS))

    assert [r.molecule_id for r in w.campaign.results] == [X]
    cell = w.cell(X, primary)
    assert cell.value == pytest.approx(55.0)
    assert len(cell.contributing_run_ids) == 10
    assert cell.replicate_count == 10


@pytest.mark.asyncio
async def test_case_e_one_run_two_stages() -> None:
    w = World()
    primary = w.stage("Primary")
    retest = w.stage("Retest", parent=primary)
    run = w.run((PCT, X, 62.0))
    await w.add([run], primary, pct())
    await w.add([run], retest, pct())

    assert [s.stage_ids for s in w.campaign.seed_runs] == [(primary, retest)]
    assert w.cell(X, primary).value == w.cell(X, retest).value == 62.0


@pytest.mark.asyncio
async def test_case_f_untested_at_stage_without_runs() -> None:
    w = World()
    primary = w.stage("Primary")
    retest = w.stage("Retest", parent=primary)
    await w.add([w.run((PCT, X, 62.0))], primary, pct())

    uc = AddCampaignChannel(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=w.campaign),
        query=w.data,
        dispatcher=AsyncMock(),
    )
    out = await uc(
        AddCampaignChannelCommand(
            workspace_id=w.auth.workspace_id,
            campaign_id=w.campaign.id,
            label="% inhibition",
            protocol_id=PROTO,
            readout_definition_id=PCT,
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            qc_filter=None,
            display_order=5,
            stage_id=retest,
        ),
        auth=w.auth,
    )
    assert isinstance(out, Success)
    column = w.column(retest)
    w.campaign.update_stage(
        retest, criteria=[StageCriterion(channel_id=column.id, operator="gte", value=50.0)]
    )

    cell = w.cell(X, retest)
    assert cell.value is None
    assert cell.unresolved_reason == UnresolvedReason.NO_RUNS_AT_STAGE
    assert w.tally(retest)["untested"] == 1


@pytest.mark.asyncio
async def test_remove_run_from_stage_leaves_other_stage_untouched() -> None:
    """Case G."""
    w = World()
    primary = w.stage("Primary")
    retest = w.stage("Retest", parent=primary)
    shared = w.run((PCT, X, 62.0))
    retest_run = w.run((PCT, X, 30.0), day=2)
    await w.add([shared], primary, pct())
    await w.add([shared, retest_run], retest, pct(SelectionRule.MEAN_ACROSS_RUNS))
    assert w.cell(X, retest).value == pytest.approx(46.0)
    before_cells, before = w.stage_cells(primary), w.tally(primary)

    await w.remove(retest, shared)

    assert w.stage_cells(primary) == before_cells
    assert w.tally(primary) == before
    assert w.cell(X, retest).value == pytest.approx(30.0)
    assert w.campaign.seed_runs[0].stage_ids == (primary,)


@pytest.mark.asyncio
async def test_case_h_different_protocols_unchanged() -> None:
    w = World()
    primary = w.stage("Primary")
    counter = w.stage("Counter-screen", parent=primary)
    other_proto, other_readout = uuid.uuid4(), uuid.uuid4()
    await w.add([w.run((PCT, X, 62.0))], primary, pct())
    before_cells, before = w.stage_cells(primary), w.tally(primary)

    other = w.run((other_readout, X, 12.0), protocol=other_proto, day=2)
    await w.add([other], counter, pct(protocol=other_proto, readout=other_readout))

    assert w.stage_cells(primary) == before_cells
    assert w.tally(primary) == before
    assert w.cell(X, counter, other_readout).value == 12.0


@pytest.mark.asyncio
async def test_case_l_empty_run_changes_nothing() -> None:
    w = World()
    primary = w.stage("Primary")
    retest = w.stage("Retest", parent=primary)
    first = w.run((PCT, X, 62.0))
    await w.add([first], primary, pct())
    before = w.tally(primary)

    empty = w.run(day=20)  # no readings yet
    await w.add([empty], primary, pct(threshold=None))
    await w.add([empty], retest, pct())

    cell = w.cell(X, primary)
    assert (cell.value, cell.contributing_run_ids) == (62.0, [first])
    assert w.tally(primary) == before
    untested = w.cell(X, retest)
    assert untested.value is None
    assert not untested.contributing_run_ids
    assert w.tally(retest)["untested"] == 1


# ---------------------------------------------------------------------------
# Every add recomputes the stage over all of its runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_adds_mean_over_all_stage_runs() -> None:
    """Daikon adds one run per call; mean across runs must mean all of them."""
    w = World()
    retest = w.stage("Retest")
    runs = [w.run((PCT, X, v), day=d) for d, v in ((1, 30.0), (2, 35.0), (3, 40.0))]
    for run in runs:
        await w.add([run], retest, pct(SelectionRule.MEAN_ACROSS_RUNS))

    cell = w.cell(X, retest)
    assert cell.value == pytest.approx(35.0)
    assert sorted(cell.contributing_run_ids) == sorted(runs)


@pytest.mark.asyncio
async def test_hits_only_judges_stage_wide_values() -> None:
    """A compound is judged on the value the commit writes (over every stage run),
    not on the request's runs alone."""
    w = World()
    retest = w.stage("Retest")
    await w.add(
        [w.run((PCT, Y, 90.0))],
        retest,
        pct(SelectionRule.MEAN_ACROSS_RUNS, 95.0),
        scope="hits_only",
    )
    assert w.campaign.results == []

    outcome = await w.add(
        [w.run((PCT, Y, 20.0), day=2)],
        retest,
        pct(SelectionRule.MEAN_ACROSS_RUNS, 50.0),
        scope="hits_only",
    )
    assert outcome.added == 1
    assert w.cell(Y, retest).value == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_stage_id_add_never_touches_criteria() -> None:
    w = World()
    primary = w.stage("Primary")
    await w.add([w.run((PCT, X, 62.0))], primary, pct(threshold=None))
    column = w.column(primary)
    criteria = [StageCriterion(channel_id=column.id, operator="gte", value=40.0)]
    w.campaign.update_stage(primary, criteria=criteria)

    await w.add([w.run((PCT, X, 70.0), day=2)], primary, pct(threshold=None))

    assert w.campaign.find_stage(primary).criteria == criteria


@pytest.mark.asyncio
async def test_thresholds_replace_criteria_only_when_present() -> None:
    w = World()
    primary = w.stage("Primary")
    await w.add([w.run((PCT, X, 62.0))], primary, pct(threshold=50.0))
    await w.add([w.run((PCT, X, 70.0), day=2)], primary, pct(threshold=80.0))
    column = w.column(primary)
    replaced = [StageCriterion(channel_id=column.id, operator="gte", value=80.0)]
    assert w.campaign.find_stage(primary).criteria == replaced

    await w.add([w.run((PCT, X, 75.0), day=3)], primary, pct(threshold=None))
    assert w.campaign.find_stage(primary).criteria == replaced


@pytest.mark.asyncio
async def test_preview_matches_commit() -> None:
    w = World()
    retest = w.stage("Retest")
    await w.add([w.run((PCT, X, 30.0))], retest, pct(SelectionRule.MEAN_ACROSS_RUNS))
    new_run = w.run((PCT, X, 40.0), (PCT, Y, 70.0), day=2)
    config = pct(SelectionRule.MEAN_ACROSS_RUNS)

    doc = await w.preview([new_run], retest, config)
    await w.add([new_run], retest, config)

    assert {r["molecule"]["id"] for r in doc["rows"]} == {str(X), str(Y)}
    for row in doc["rows"]:
        [cell] = row["cells"]
        m = w.cell(uuid.UUID(row["molecule"]["id"]), retest)
        assert cell["value"] == pytest.approx(m.value)
        assert cell["value_qualifier"] == m.value_qualifier.value
        assert cell["unit"] == m.unit
        assert cell["replicate_count"] == m.replicate_count
        assert cell["contributing_run_ids"] == [str(r) for r in m.contributing_run_ids or []]
        assert cell["test_concentration_value"] == m.test_concentration_value
        assert cell["test_concentration_unit"] == m.test_concentration_unit
        assert cell["basis"] == (m.basis.value if m.basis else None)
    by_mol = {r["molecule"]["id"]: r for r in doc["rows"]}
    # Stage-wide: X is the mean of both of the stage's runs, not the new run alone.
    assert by_mol[str(X)]["cells"][0]["value"] == pytest.approx(35.0)
    assert by_mol[str(X)]["already_in_campaign"] is True
    assert by_mol[str(Y)]["already_in_campaign"] is False


@pytest.mark.asyncio
async def test_preview_new_stage_matches_commit() -> None:
    """``stage_name`` naming no stage previews an unsaved new stage whose runs are
    exactly the request's: its column ignores the protocol's campaign runs, and the
    values are the ones the commit then writes."""
    w = World()
    await w.add([w.run((PCT, X, 90.0))], None, pct(SelectionRule.MEAN_ACROSS_RUNS))
    new_run = w.run((PCT, X, 40.0), (PCT, Y, 70.0), day=2)
    config = pct(SelectionRule.MEAN_ACROSS_RUNS)

    doc = await w.preview([new_run], None, config, stage_name="Retest")
    assert w.campaign.stages == []
    await w.add([new_run], None, config, stage_name="Retest")

    [stage] = w.campaign.stages
    values = {}
    for row in doc["rows"]:
        [cell] = row["cells"]
        mol = uuid.UUID(row["molecule"]["id"])
        m = w.cell(mol, stage.id)
        assert cell["value"] == pytest.approx(m.value)
        assert cell["replicate_count"] == m.replicate_count
        assert cell["contributing_run_ids"] == [str(r) for r in m.contributing_run_ids or []]
        assert cell["unresolved_reason"] is None
        values[mol] = cell["value"]
    assert values == {X: pytest.approx(40.0), Y: pytest.approx(70.0)}

    # Named again, in another case, it previews the stage that now exists.
    later = w.run((PCT, X, 60.0), day=3)
    doc = await w.preview([later], None, config, stage_name="retest")
    assert doc["channels"][0]["source"] == "reused"
    x = next(r for r in doc["rows"] if r["molecule"]["id"] == str(X))
    assert x["cells"][0]["value"] == pytest.approx(50.0)
