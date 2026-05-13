"""Unit tests for PreviewRunImport use case (B6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.channel_resolution import (
    ResolvedCandidate,
)
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
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeChannelQuery:
    """In-memory implementation of ChannelResolutionQuery for tests.

    Configured with a per-(protocol_id, readout_def_id) candidate map.
    """

    def __init__(
        self,
        candidates_by_channel: dict[tuple[uuid.UUID, uuid.UUID], dict[uuid.UUID, list[ResolvedCandidate]]] | None = None,
    ) -> None:
        self._data = candidates_by_channel or {}
        self.calls: list = []

    async def fetch_candidates(self, *, workspace_id, channel, molecule_id):
        return []

    async def fetch_candidates_for_runs(
        self,
        *,
        workspace_id,
        run_ids,
        protocol_id,
        readout_definition_id,
        source_kind,
        normalization_applied=None,
    ):
        self.calls.append(
            (run_ids, protocol_id, readout_definition_id, source_kind, normalization_applied)
        )
        all_for_channel = self._data.get((protocol_id, readout_definition_id), {})
        # Filter candidates to those whose run_id is in the requested run_ids
        out: dict[uuid.UUID, list[ResolvedCandidate]] = {}
        run_set = set(run_ids)
        for mol_id, cands in all_for_channel.items():
            kept = [c for c in cands if c.run_id in run_set]
            if kept:
                out[mol_id] = kept
        return out


def _candidate(
    *,
    value: float = 50.0,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    unit: str = "nM",
    run_id: uuid.UUID | None = None,
    run_date: date | None = None,
    approved: bool = True,
    z_prime: float | None = 0.8,
    protocol_name: str = "Proto",
    protocol_version: int = 1,
) -> ResolvedCandidate:
    return ResolvedCandidate(
        value=value,
        qualifier=qualifier,
        unit=unit,
        run_id=run_id or uuid.uuid4(),
        run_date=run_date or date(2026, 1, 1),
        run_approved=approved,
        z_prime=z_prime,
        protocol_name=protocol_name,
        protocol_version=protocol_version,
        curve_id=None,
        readout_id=uuid.uuid4(),
    )


def _make_mol(id_: uuid.UUID, *, reg: str = "CVT-0001", smiles: str | None = "C") -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        registration_number=SimpleNamespace(value=reg),
        name=f"Mol-{reg}",
        structure=SimpleNamespace(smiles=smiles) if smiles else None,
    )


def _make_molecule_repo(molecules: list[SimpleNamespace]) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(return_value=molecules)
    return repo


def _make_run_repo(run_ids: list[uuid.UUID]) -> AsyncMock:
    repo = AsyncMock()
    runs = [SimpleNamespace(id=rid) for rid in run_ids]
    repo.find_by_ids = AsyncMock(return_value=runs)
    return repo


def _make_draft_campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="C1",
        description=None,
        publishes_collection=True,
        created_by=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPreviewRunImport:
    @pytest.mark.asyncio
    async def test_empty_run_ids_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([]),
            molecule_repo=_make_molecule_repo([]),
            channel_query=FakeChannelQuery(),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=uuid.uuid4(),
                    readout_definition_id=uuid.uuid4(),
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_campaign_not_found(self) -> None:
        auth = fake_auth()
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            run_repo=_make_run_repo([uuid.uuid4()]),
            molecule_repo=_make_molecule_repo([]),
            channel_query=FakeChannelQuery(),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            run_ids=[uuid.uuid4()],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=uuid.uuid4(),
                    readout_definition_id=uuid.uuid4(),
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_unauthorized(self) -> None:
        auth = fake_auth(role="viewer")
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            run_repo=_make_run_repo([uuid.uuid4()]),
            molecule_repo=_make_molecule_repo([]),
            channel_query=FakeChannelQuery(),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            run_ids=[uuid.uuid4()],
            channel_configs=[],
        )
        with pytest.raises(AuthorizationError):
            await uc(q, auth=auth)
    @pytest.mark.asyncio
    async def test_single_run_single_channel_no_threshold_no_hits(self) -> None:
        """No hit_threshold -> no active filter -> is_hit=False for everyone."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        readout_id = uuid.uuid4()
        run_id = uuid.uuid4()
        mol1 = uuid.uuid4()
        candidates_map = {
            (proto_id, readout_id): {
                mol1: [_candidate(value=100.0, run_id=run_id, run_date=date(2026, 1, 1))],
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo([_make_mol(mol1)]),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_id,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=None,  # no threshold -> no active filter
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        assert doc["summary"]["hits"] == 0
        assert doc["summary"]["non_hits"] == 1
        assert doc["rows"][0]["is_hit"] is False
        assert doc["rows"][0]["cells"][0]["hit_call"] is None

    @pytest.mark.asyncio
    async def test_single_channel_threshold_some_hits(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        readout_id = uuid.uuid4()
        run_id = uuid.uuid4()
        mol_hit = uuid.uuid4()
        mol_miss = uuid.uuid4()
        candidates_map = {
            (proto_id, readout_id): {
                mol_hit: [_candidate(value=42.0, run_id=run_id)],
                mol_miss: [_candidate(value=8500.0, run_id=run_id)],
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo(
                [_make_mol(mol_hit, reg="CVT-0142"), _make_mol(mol_miss, reg="CVT-0207")]
            ),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_id,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                    use_for_filter=True,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        assert doc["summary"]["hits"] == 1
        assert doc["summary"]["non_hits"] == 1
        hits = [r for r in doc["rows"] if r["is_hit"]]
        misses = [r for r in doc["rows"] if not r["is_hit"]]
        assert hits[0]["molecule"]["registration_number"] == "CVT-0142"
        assert hits[0]["cells"][0]["hit_call"] == "hit"
        assert misses[0]["cells"][0]["hit_call"] == "miss"

    @pytest.mark.asyncio
    async def test_two_channels_and_filter(self) -> None:
        """AND: molecule must hit in both channels to be is_hit=True."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        readout_a = uuid.uuid4()
        readout_b = uuid.uuid4()
        run_id = uuid.uuid4()
        mol_both = uuid.uuid4()
        mol_one = uuid.uuid4()
        candidates_map = {
            (proto_id, readout_a): {
                mol_both: [_candidate(value=42.0, run_id=run_id)],
                mol_one: [_candidate(value=50.0, run_id=run_id)],
            },
            (proto_id, readout_b): {
                mol_both: [_candidate(value=70.0, unit="%", run_id=run_id)],
                mol_one: [_candidate(value=20.0, unit="%", run_id=run_id)],
            },
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo(
                [_make_mol(mol_both, reg="A"), _make_mol(mol_one, reg="B")]
            ),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_a,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                    use_for_filter=True,
                ),
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_b,
                    label="%inh",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="%inh", operator="gt", value=50.0
                    ),
                    use_for_filter=True,
                ),
            ],
            filter_mode="all",
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        # mol_both: 42 < 1000 AND 70 > 50 -> hit; mol_one: 50 < 1000 BUT 20 < 50 -> not hit
        assert doc["summary"]["hits"] == 1
        assert doc["summary"]["non_hits"] == 1
        hits = [r for r in doc["rows"] if r["is_hit"]]
        assert hits[0]["molecule"]["registration_number"] == "A"

    @pytest.mark.asyncio
    async def test_two_channels_any_filter(self) -> None:
        """ANY: molecule needs to hit in at least one channel."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        ra, rb = uuid.uuid4(), uuid.uuid4()
        run_id = uuid.uuid4()
        mol = uuid.uuid4()
        candidates_map = {
            (proto_id, ra): {mol: [_candidate(value=42.0, run_id=run_id)]},
            (proto_id, rb): {mol: [_candidate(value=20.0, unit="%", run_id=run_id)]},
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo([_make_mol(mol)]),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=ra,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                ),
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=rb,
                    label="%inh",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="%inh", operator="gt", value=50.0
                    ),
                ),
            ],
            filter_mode="any",
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        # IC50: 42 < 1000 -> hit; %inh: 20 not > 50 -> miss; any -> hit
        assert doc["summary"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_channel_reuse_when_campaign_has_matching_channel(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        readout_id = uuid.uuid4()
        existing_channel = CampaignChannel(
            campaign_id=campaign.id,
            label="existing",
            display_order=0,
            protocol_id=proto_id,
            readout_definition_id=readout_id,
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        )
        campaign.channels.append(existing_channel)
        run_id = uuid.uuid4()
        mol = uuid.uuid4()
        candidates_map = {
            (proto_id, readout_id): {mol: [_candidate(run_id=run_id)]},
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo([_make_mol(mol)]),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_id,
                    label="IC50 (updated)",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        assert doc["summary"]["channels_reused"] == 1
        assert doc["summary"]["channels_new"] == 0
        assert doc["channels"][0]["source"] == "reused"
        assert doc["channels"][0]["reuse_of_channel_id"] == str(existing_channel.id)

    @pytest.mark.asyncio
    async def test_already_in_campaign_flag(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        existing_mol_id = uuid.uuid4()
        existing_result = CampaignResult(
            campaign_id=campaign.id, molecule_id=existing_mol_id
        )
        campaign.results.append(existing_result)

        proto_id = uuid.uuid4()
        readout_id = uuid.uuid4()
        run_id = uuid.uuid4()
        new_mol = uuid.uuid4()
        candidates_map = {
            (proto_id, readout_id): {
                existing_mol_id: [_candidate(value=10.0, run_id=run_id)],
                new_mol: [_candidate(value=20.0, run_id=run_id)],
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo(
                [_make_mol(existing_mol_id, reg="OLD"), _make_mol(new_mol, reg="NEW")]
            ),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_id,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        assert doc["summary"]["molecules_already_in_campaign"] == 1
        flags = {r["molecule"]["registration_number"]: r["already_in_campaign"] for r in doc["rows"]}
        assert flags["OLD"] is True
        assert flags["NEW"] is False

    @pytest.mark.asyncio
    async def test_replicate_count_and_contributing_runs_surface(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        readout_id = uuid.uuid4()
        r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates_map = {
            (proto_id, readout_id): {
                mol: [
                    _candidate(value=10.0, run_id=r1, run_date=date(2026, 1, 1)),
                    _candidate(value=12.0, run_id=r2, run_date=date(2026, 2, 1)),
                    _candidate(value=14.0, run_id=r3, run_date=date(2026, 3, 1)),
                ]
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([r1, r2, r3]),
            molecule_repo=_make_molecule_repo([_make_mol(mol)]),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[r1, r2, r3],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_id,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        cell = doc["rows"][0]["cells"][0]
        assert cell["replicate_count"] == 3
        assert set(cell["contributing_run_ids"]) == {str(r1), str(r2), str(r3)}
        assert cell["value"] == pytest.approx(12.0)  # mean of 10, 12, 14

    @pytest.mark.asyncio
    async def test_between_operator_filters_to_range(self) -> None:
        """HitCriterion operator='between' with [low, high] hits only values in range."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto = uuid.uuid4()
        readout = uuid.uuid4()
        run_id = uuid.uuid4()
        mol_in = uuid.uuid4()      # 50 — in (10, 100)
        mol_below = uuid.uuid4()   # 5  — below
        mol_above = uuid.uuid4()   # 150 — above
        candidates = {
            (proto, readout): {
                mol_in: [_candidate(value=50.0, run_id=run_id)],
                mol_below: [_candidate(value=5.0, run_id=run_id)],
                mol_above: [_candidate(value=150.0, run_id=run_id)],
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo([_make_mol(mol_in), _make_mol(mol_below), _make_mol(mol_above)]),
            channel_query=FakeChannelQuery(candidates),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="between", value=[10.0, 100.0]
                    ),
                    use_for_filter=True,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        assert doc["summary"]["hits"] == 1
        assert doc["summary"]["non_hits"] == 2
        hit_row = next(r for r in doc["rows"] if r["is_hit"])
        assert hit_row["cells"][0]["value"] == 50.0

    @pytest.mark.asyncio
    async def test_allowed_curve_classes_filters_candidates(self) -> None:
        """allowed_curve_classes restricts to curves whose curve_class is in the set."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto = uuid.uuid4()
        readout = uuid.uuid4()
        run_id = uuid.uuid4()
        mol_full = uuid.uuid4()
        mol_inactive = uuid.uuid4()

        def _cand_with_class(value: float, cls: str) -> ResolvedCandidate:
            c = _candidate(value=value, run_id=run_id)
            return ResolvedCandidate(
                value=c.value, qualifier=c.qualifier, unit=c.unit,
                run_id=c.run_id, run_date=c.run_date, run_approved=c.run_approved,
                z_prime=c.z_prime, protocol_name=c.protocol_name,
                protocol_version=c.protocol_version, curve_id=c.curve_id,
                readout_id=c.readout_id, curve_class=cls,
            )

        candidates = {
            (proto, readout): {
                mol_full: [_cand_with_class(50.0, "full")],
                mol_inactive: [_cand_with_class(60.0, "inactive")],
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo([_make_mol(mol_full), _make_mol(mol_inactive)]),
            channel_query=FakeChannelQuery(candidates),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    allowed_curve_classes=["full"],
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        doc = out.unwrap()
        # Only the "full" curve molecule should appear; "inactive" is filtered out.
        assert doc["summary"]["molecules_total"] == 1
        assert doc["rows"][0]["molecule"]["id"] == str(mol_full)

    @pytest.mark.asyncio
    async def test_qc_pass_false_for_unapproved_or_low_z_prime(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        proto_id = uuid.uuid4()
        readout_id = uuid.uuid4()
        run_id = uuid.uuid4()
        mol = uuid.uuid4()
        # Single candidate with z_prime=0.3 -> QC fail
        candidates_map = {
            (proto_id, readout_id): {
                mol: [_candidate(value=42.0, run_id=run_id, z_prime=0.3)]
            }
        }
        uc = PreviewRunImport(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_make_run_repo([run_id]),
            molecule_repo=_make_molecule_repo([_make_mol(mol)]),
            channel_query=FakeChannelQuery(candidates_map),
        )
        q = PreviewRunImportQuery(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto_id,
                    readout_definition_id=readout_id,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
        )
        out = await uc(q, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap()["rows"][0]["cells"][0]["qc_pass"] is False
