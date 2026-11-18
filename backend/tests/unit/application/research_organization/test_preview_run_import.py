"""Unit tests for PreviewRunImport (B6 read-only preview).

The preview runs the commit's own computation and never saves, so its cells are
exactly what the commit writes (``test_stage_scoped_cases.test_preview_matches_commit``).
These cover the document: hit calls and filter modes, column reuse, the row
filter, and the facts each cell carries.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure

from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
    PreviewRunImport,
    PreviewRunImportQuery,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey
from tests.unit.application.research_organization._helpers import (
    FakeRunData,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
    reading,
)

PROTO = uuid.uuid4()


def _make_mol(id_: uuid.UUID, *, reg: str = "CVT-0001") -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        registration_number=SimpleNamespace(value=reg),
        name=f"Mol-{reg}",
        structure=SimpleNamespace(smiles="C"),
    )


def _molecule_repo(*mols: uuid.UUID) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(return_value=[_make_mol(m, reg=str(m)) for m in mols])
    return repo


def _run_repo(run_ids: list[uuid.UUID]) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(
        return_value={r: SimpleNamespace(id=r, protocol_id=PROTO) for r in run_ids}
    )
    return repo


def _campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="C1",
        description=None,
        created_by=uuid.uuid4(),
    )


def _config(
    readout: uuid.UUID,
    rule: SelectionRule = SelectionRule.LATEST_RUN,
    *,
    threshold: HitCriterion | None = None,
    kind: ChannelSourceKind = ChannelSourceKind.READOUT_DATA,
    **kw,
) -> ChannelImportConfig:
    return ChannelImportConfig(
        protocol_id=PROTO,
        readout_definition_id=readout,
        label="IC50",
        source_kind=kind,
        selection_rule=rule,
        hit_threshold=threshold,
        **kw,
    )


def _lt(value: float) -> HitCriterion:
    return HitCriterion(readout_name="IC50", operator="lt", value=value)


async def _preview(campaign, data, run_ids, *configs, mols=(), auth=None, **kw):
    auth = auth or fake_auth()
    campaign_repo = make_campaign_repo(find_in_ws=campaign)
    uc = PreviewRunImport(
        uow=FakeUnitOfWork(),
        campaign_repo=campaign_repo,
        run_repo=_run_repo(run_ids),
        molecule_repo=_molecule_repo(*mols),
        query=data,
    )
    out = await uc(
        PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id if campaign else uuid.uuid4(),
            run_ids=run_ids,
            channel_configs=list(configs),
            **kw,
        ),
        auth=auth,
    )
    campaign_repo.save.assert_not_called()
    return out


class TestPreviewRunImport:
    @pytest.mark.asyncio
    async def test_empty_run_ids_returns_validation_failure(self) -> None:
        auth = fake_auth()
        out = await _preview(
            _campaign(auth.workspace_id), FakeRunData(), [], _config(uuid.uuid4()), auth=auth
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_campaign_not_found(self) -> None:
        out = await _preview(None, FakeRunData(), [uuid.uuid4()], _config(uuid.uuid4()))
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_unknown_stage_id_is_not_found(self) -> None:
        auth = fake_auth()
        out = await _preview(
            _campaign(auth.workspace_id),
            FakeRunData(),
            [uuid.uuid4()],
            _config(uuid.uuid4()),
            auth=auth,
            stage_id=uuid.uuid4(),
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_unauthorized(self) -> None:
        with pytest.raises(AuthorizationError):
            await _preview(None, FakeRunData(), [uuid.uuid4()], auth=fake_auth(role="viewer"))

    @pytest.mark.asyncio
    async def test_no_threshold_no_hits(self) -> None:
        auth = fake_auth()
        readout, run_id, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(mol, 100.0, run_id))
        out = await _preview(
            _campaign(auth.workspace_id), data, [run_id], _config(readout), mols=[mol], auth=auth
        )
        doc = out.unwrap()
        assert (doc["summary"]["hits"], doc["summary"]["non_hits"]) == (0, 1)
        assert doc["rows"][0]["is_hit"] is False
        assert doc["rows"][0]["cells"][0]["hit_call"] is None

    @pytest.mark.asyncio
    async def test_single_channel_threshold_some_hits(self) -> None:
        auth = fake_auth()
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        mol_hit, mol_miss = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(mol_hit, 42.0, run_id), reading(mol_miss, 8500.0, run_id))
        out = await _preview(
            _campaign(auth.workspace_id),
            data,
            [run_id],
            _config(readout, threshold=_lt(1000.0)),
            mols=[mol_hit, mol_miss],
            auth=auth,
        )
        doc = out.unwrap()
        assert (doc["summary"]["hits"], doc["summary"]["non_hits"]) == (1, 1)
        calls = {r["molecule"]["id"]: r["cells"][0]["hit_call"] for r in doc["rows"]}
        assert calls == {str(mol_hit): "hit", str(mol_miss): "miss"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("mode", "hits"), [("all", 1), ("any", 2)])
    async def test_two_channels_filter_mode(self, mode: str, hits: int) -> None:
        auth = fake_auth()
        ra, rb, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        both, one = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(ra, reading(both, 42.0, run_id), reading(one, 50.0, run_id))
        data.add(rb, reading(both, 70.0, run_id), reading(one, 20.0, run_id))
        out = await _preview(
            _campaign(auth.workspace_id),
            data,
            [run_id],
            _config(ra, threshold=_lt(1000.0)),
            _config(rb, threshold=HitCriterion(readout_name="%inh", operator="gt", value=50.0)),
            mols=[both, one],
            auth=auth,
            filter_mode=mode,
        )
        assert out.unwrap()["summary"]["hits"] == hits

    @pytest.mark.asyncio
    async def test_channel_reuse_when_campaign_has_matching_channel(self) -> None:
        auth = fake_auth()
        campaign = _campaign(auth.workspace_id)
        readout, run_id, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        existing = CampaignChannel(
            campaign_id=campaign.id,
            label="existing",
            display_order=0,
            protocol_id=PROTO,
            readout_definition_id=readout,
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        )
        campaign.add_channel(existing)
        data = FakeRunData()
        data.add(readout, reading(mol, 5.0, run_id))
        doc = (
            await _preview(campaign, data, [run_id], _config(readout), mols=[mol], auth=auth)
        ).unwrap()
        assert (doc["summary"]["channels_reused"], doc["summary"]["channels_new"]) == (1, 0)
        assert doc["channels"][0]["source"] == "reused"
        assert doc["channels"][0]["reuse_of_channel_id"] == str(existing.id)

    @pytest.mark.asyncio
    async def test_already_in_campaign_flag(self) -> None:
        auth = fake_auth()
        campaign = _campaign(auth.workspace_id)
        old, new = uuid.uuid4(), uuid.uuid4()
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=old))
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(old, 10.0, run_id), reading(new, 20.0, run_id))
        doc = (
            await _preview(campaign, data, [run_id], _config(readout), mols=[old, new], auth=auth)
        ).unwrap()
        assert doc["summary"]["molecules_already_in_campaign"] == 1
        flags = {r["molecule"]["id"]: r["already_in_campaign"] for r in doc["rows"]}
        assert flags == {str(old): True, str(new): False}

    @pytest.mark.asyncio
    async def test_cell_carries_the_value_facts(self) -> None:
        auth = fake_auth()
        readout, mol = uuid.uuid4(), uuid.uuid4()
        runs = [uuid.uuid4() for _ in range(3)]
        batch = uuid.uuid4()
        data = FakeRunData()
        for i, (run_id, value) in enumerate(zip(runs, (10.0, 12.0, 14.0), strict=True)):
            data.add(
                readout,
                reading(
                    mol,
                    value,
                    run_id,
                    run_date=date(2026, i + 1, 1),
                    dose=Concentration(10.0, "µM"),
                    batch_id=batch,
                ),
            )
        doc = (
            await _preview(
                _campaign(auth.workspace_id),
                data,
                runs,
                _config(readout, SelectionRule.MEAN_ACROSS_RUNS),
                mols=[mol],
                auth=auth,
            )
        ).unwrap()
        cell = doc["rows"][0]["cells"][0]
        assert cell["value"] == pytest.approx(12.0)
        assert cell["replicate_count"] == 3
        assert set(cell["contributing_run_ids"]) == {str(r) for r in runs}
        assert (cell["test_concentration_value"], cell["test_concentration_unit"]) == (10.0, "µM")
        assert cell["batch_ids"] == [str(batch)]
        assert cell["basis"] == "measured"
        assert cell["concentration_series"] is False
        assert cell["unresolved_reason"] is None
        # The old import-time QC heuristic is not a fact the commit writes.
        assert (cell["qc_pass"], cell["qc_reason"]) == (None, None)

    @pytest.mark.asyncio
    async def test_between_operator_filters_to_range(self) -> None:
        auth = fake_auth()
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        inside, below, above = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        for mol, v in ((inside, 50.0), (below, 5.0), (above, 150.0)):
            data.add(readout, reading(mol, v, run_id, unit="nM", curve_class="full"))
        doc = (
            await _preview(
                _campaign(auth.workspace_id),
                data,
                [run_id],
                _config(
                    readout,
                    kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    threshold=HitCriterion(
                        readout_name="IC50", operator="between", value=[10.0, 100.0]
                    ),
                ),
                mols=[inside, below, above],
                auth=auth,
            )
        ).unwrap()
        assert (doc["summary"]["hits"], doc["summary"]["non_hits"]) == (1, 2)
        assert next(r for r in doc["rows"] if r["is_hit"])["cells"][0]["value"] == 50.0

    @pytest.mark.asyncio
    async def test_allowed_curve_classes_filters_rows(self) -> None:
        auth = fake_auth()
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        full, inactive, endpoint = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(
            readout,
            reading(full, 50.0, run_id, unit="nM", curve_class="full"),
            reading(inactive, 60.0, run_id, unit="nM", curve_class="inactive"),
            reading(endpoint, 32.0, run_id, unit="nM", well=False),
        )
        doc = (
            await _preview(
                _campaign(auth.workspace_id),
                data,
                [run_id],
                _config(
                    readout,
                    kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    allowed_curve_classes=["full"],
                ),
                mols=[full, endpoint],
                auth=auth,
            )
        ).unwrap()
        assert {r["molecule"]["id"] for r in doc["rows"]} == {str(full), str(endpoint)}
        assert doc["summary"]["molecules_total"] == 2

    @pytest.mark.asyncio
    async def test_multi_intercept_channels_disambiguate_cells_and_hits(self) -> None:
        """EC50 and EC90 columns on one readout each read their own intercept and
        make their own hit call."""
        auth = fake_auth()
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        mol_a, mol_b = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        for mol, ec50, ec90 in ((mol_a, 4.0, 40.0), (mol_b, 10.0, 200.0)):
            data.add(
                readout,
                reading(
                    mol,
                    ec50,
                    run_id,
                    unit="uM",
                    curve_class="full",
                    intercept_values=[
                        {"spec": {"kind": "ec", "level": 50}, "value": ec50},
                        {"spec": {"kind": "ec", "level": 90}, "value": ec90},
                    ],
                ),
            )
        doc = (
            await _preview(
                _campaign(auth.workspace_id),
                data,
                [run_id],
                _config(readout, kind=ChannelSourceKind.DOSE_RESPONSE_CURVE, threshold=_lt(50.0)),
                _config(
                    readout,
                    kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    intercept_key=InterceptKey(kind="ec", level=90),
                    threshold=_lt(50.0),
                ),
                mols=[mol_a, mol_b],
                auth=auth,
                filter_mode="all",
            )
        ).unwrap()
        assert doc["summary"]["channels_new"] == 2
        assert len({c["channel_key"] for c in doc["channels"]}) == 2
        rows = {r["molecule"]["id"]: r for r in doc["rows"]}
        a, b = rows[str(mol_a)], rows[str(mol_b)]
        assert [c["value"] for c in a["cells"]] == [4.0, 40.0]
        assert [c["hit_call"] for c in a["cells"]] == ["hit", "hit"]
        assert [c["value"] for c in b["cells"]] == [10.0, 200.0]
        assert [c["hit_call"] for c in b["cells"]] == ["hit", "miss"]
        assert (a["is_hit"], b["is_hit"]) == (True, False)

    @pytest.mark.asyncio
    async def test_dr_config_previews_molecule_with_only_a_reported_endpoint(self) -> None:
        auth = fake_auth()
        readout, run_id, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(mol, 32.0, run_id, unit="uM", well=False))
        doc = (
            await _preview(
                _campaign(auth.workspace_id),
                data,
                [run_id],
                _config(readout, kind=ChannelSourceKind.DOSE_RESPONSE_CURVE),
                mols=[mol],
                auth=auth,
            )
        ).unwrap()
        cell = doc["rows"][0]["cells"][0]
        assert (cell["value"], cell["basis"], cell["concentration_series"]) == (
            32.0,
            "reported",
            True,
        )
