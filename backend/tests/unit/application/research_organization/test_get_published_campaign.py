"""Unit tests for GetPublishedCampaign query."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.get_published_campaign import (
    GetPublishedCampaign,
    GetPublishedCampaignQuery,
    _decode_cursor,
    _encode_cursor,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    CampaignStatus,
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    fake_auth,
    make_campaign_repo,
)


# ---------------------------------------------------------------------------
# Local builder helpers
# ---------------------------------------------------------------------------


def _make_channel(
    campaign_id: uuid.UUID,
    *,
    protocol_id: uuid.UUID | None = None,
    readout_definition_id: uuid.UUID | None = None,
    display_order: int = 0,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign_id,
        label=f"IC50 channel {display_order}",
        protocol_id=protocol_id or uuid.uuid4(),
        readout_definition_id=readout_definition_id or uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=display_order,
    )


def _make_measurement(
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    unit: str = "nM",
    value: float = 42.0,
    source_run_id: uuid.UUID | None = None,
) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=value,
        value_qualifier=ValueQualifier.EQ,
        unit=unit,
        protocol_name_snapshot="EGFR Binding Assay",
        protocol_version_snapshot=3,
        hit_call=HitCall.HIT,
        source_run_id=source_run_id or uuid.uuid4(),
        run_date_snapshot=date(2026, 5, 1),
    )


def _make_fake_protocol(
    protocol_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
) -> AsyncMock:
    protocol = AsyncMock()
    protocol.id = protocol_id
    protocol.name = "EGFR Binding Assay"
    protocol.protocol_version = 3
    protocol.target_id = None

    readout = AsyncMock()
    readout.id = readout_definition_id
    readout.name = "IC50"
    readout.unit = "nM"
    readout.data_type = AsyncMock()
    readout.data_type.value = "numeric"
    protocol.readout_definitions = [readout]
    return protocol


def _make_closed_campaign(
    workspace_id: uuid.UUID,
    *,
    compound_source=None,
    publishes_collection: bool = True,
    n_results: int = 2,
    protocol_id: uuid.UUID | None = None,
    readout_definition_id: uuid.UUID | None = None,
    decisions: list[CampaignDecision] | None = None,
    published_collection_id: uuid.UUID | None = None,
    signature_id: uuid.UUID | None = None,
) -> tuple[Campaign, CampaignChannel]:
    """Build a CLOSED campaign with 1 channel and n_results results."""
    pid = protocol_id or uuid.uuid4()
    rdid = readout_definition_id or uuid.uuid4()
    mol_ids = [uuid.uuid4() for _ in range(max(n_results, 1))]

    if compound_source is None:
        compound_source = ExplicitListSource(molecule_ids=mol_ids)

    campaign = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="EGFR Round 2",
        description="Primary screen",
        status=CampaignStatus.CLOSED,
        compound_source=compound_source,
        publishes_collection=publishes_collection,
        source_protocols=[
            {
                "id": str(pid),
                "name": "EGFR Binding Assay",
                "version": 3,
                "target_id": None,
                "target_name": None,
            }
        ],
        closed_at=datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc),
        closed_by=uuid.uuid4(),
        signature_id=signature_id or uuid.uuid4(),
        published_collection_id=published_collection_id,
        created_by=uuid.uuid4(),
    )

    ch = _make_channel(campaign.id, protocol_id=pid, readout_definition_id=rdid)
    campaign.channels.append(ch)

    if decisions is None:
        decisions = [CampaignDecision.SELECTED if i == 0 else CampaignDecision.REJECTED for i in range(n_results)]

    for i, mol_id in enumerate(mol_ids[:n_results]):
        result = CampaignResult(campaign_id=campaign.id, molecule_id=mol_id)
        m = _make_measurement(result.id, ch.id)
        result.measurements.append(m)
        result.decision = decisions[i] if i < len(decisions) else CampaignDecision.DEFERRED
        campaign.results.append(result)

    return campaign, ch


def _make_query(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    cursor: str | None = None,
    page_size: int | None = None,
) -> GetPublishedCampaignQuery:
    return GetPublishedCampaignQuery(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        cursor=cursor,
        page_size=page_size,
    )


def _build_use_case(
    campaign: Campaign | None = None,
    *,
    protocol_id: uuid.UUID | None = None,
    readout_definition_id: uuid.UUID | None = None,
    project: AsyncMock | None = None,
    collection: AsyncMock | None = None,
    collection_size: int = 12,
    molecule_lookup: dict | None = None,
    batch_lookup: dict | None = None,
) -> tuple[GetPublishedCampaign, AsyncMock]:
    campaign_repo = make_campaign_repo(find_in_ws=campaign)

    project_repo = AsyncMock()
    project_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

    protocol_repo = AsyncMock()
    if protocol_id is not None and readout_definition_id is not None:
        proto = _make_fake_protocol(protocol_id, readout_definition_id)
        protocol_repo.find_by_ids = AsyncMock(return_value=[proto])
    else:
        protocol_repo.find_by_ids = AsyncMock(return_value=[])

    coll_repo = AsyncMock()
    coll_repo.find_by_id_in_workspace = AsyncMock(return_value=collection)
    coll_repo.count_molecules = AsyncMock(return_value=collection_size)

    mol_repo = AsyncMock()
    if molecule_lookup is not None:
        async def _find_by_ids(ws_id, ids):
            return [molecule_lookup[mid] for mid in ids if mid in molecule_lookup]
        mol_repo.find_by_ids = AsyncMock(side_effect=_find_by_ids)
    else:
        mol_repo.find_by_ids = AsyncMock(return_value=[])

    batch_repo = AsyncMock()
    if batch_lookup is not None:
        async def _find_by_id(bid):
            return batch_lookup.get(bid)
        batch_repo.find_by_id = AsyncMock(side_effect=_find_by_id)
    else:
        batch_repo.find_by_id = AsyncMock(return_value=None)

    uc = GetPublishedCampaign(
        campaign_repo=campaign_repo,
        project_repo=project_repo,
        protocol_repo=protocol_repo,
        collection_repo=coll_repo,
        molecule_repo=mol_repo,
        batch_repo=batch_repo,
    )
    return uc, campaign_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCursorHelpers:
    def test_encode_decode_roundtrip(self) -> None:
        assert _decode_cursor(_encode_cursor(42), 0) == 42

    def test_decode_none_returns_default(self) -> None:
        assert _decode_cursor(None, 0) == 0

    def test_decode_invalid_returns_default(self) -> None:
        assert _decode_cursor("not-a-number", 0) == 0


class TestGetPublishedCampaign:
    # ------------------------------------------------------------------
    # 1. Happy path: publishes_collection=True
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_happy_path_publishes_collection_true(self) -> None:
        auth = fake_auth()
        pid = uuid.uuid4()
        rdid = uuid.uuid4()
        coll_id = uuid.uuid4()

        campaign, ch = _make_closed_campaign(
            auth.workspace_id,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4(), uuid.uuid4()]),
            publishes_collection=True,
            n_results=2,
            protocol_id=pid,
            readout_definition_id=rdid,
            decisions=[CampaignDecision.SELECTED, CampaignDecision.REJECTED],
            published_collection_id=coll_id,
        )
        sig_id = campaign.signature_id

        fake_coll = AsyncMock()
        fake_coll.id = coll_id
        fake_coll.name = "Hits — EGFR Round 2"

        uc, _ = _build_use_case(
            campaign,
            protocol_id=pid,
            readout_definition_id=rdid,
            collection=fake_coll,
            collection_size=12,
        )
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        doc = out.unwrap()

        # Top-level keys present.
        for key in ("campaign", "compound_source", "source_protocols", "channels", "results", "published_collection"):
            assert key in doc, f"missing key: {key}"

        # Campaign header.
        assert doc["campaign"]["status"] == "closed"
        assert doc["campaign"]["signature"]["id"] == str(sig_id)
        assert doc["campaign"]["signature"]["signed_at"] is None  # TODO pending

        # Results length.
        assert len(doc["results"]) == 2

        # Published collection present.
        assert doc["published_collection"] is not None
        assert doc["published_collection"]["id"] == str(coll_id)
        assert doc["published_collection"]["size"] == 12

        # CompoundSource kind.
        assert doc["compound_source"]["kind"] == "explicit_list"
        assert "molecule_ids" in doc["compound_source"]["ref"]

        # No pagination key when page_size is None.
        assert "pagination" not in doc

    # ------------------------------------------------------------------
    # 2. Happy path: publishes_collection=False → null
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_happy_path_publishes_collection_false(self) -> None:
        auth = fake_auth()
        campaign, _ = _make_closed_campaign(
            auth.workspace_id,
            publishes_collection=False,
            published_collection_id=None,
        )

        uc, _ = _build_use_case(campaign)
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        doc = out.unwrap()
        assert doc["published_collection"] is None

    # ------------------------------------------------------------------
    # 3. CompoundSource serialization — parametrized
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "source,expected_kind,ref_key",
        [
            (
                CollectionSource(collection_id=uuid.uuid4()),
                "collection",
                "collection_id",
            ),
            (
                DerivedFromCampaignSource(
                    campaign_id=uuid.uuid4(),
                    decision_filter=[CampaignDecision.SELECTED],
                ),
                "derived_from_campaign",
                "campaign_id",
            ),
            (
                SavedSearchSource(saved_search_id=uuid.uuid4()),
                "saved_search",
                "saved_search_id",
            ),
        ],
    )
    async def test_compound_source_serialization(
        self, source, expected_kind: str, ref_key: str
    ) -> None:
        auth = fake_auth()
        campaign, _ = _make_closed_campaign(
            auth.workspace_id,
            compound_source=source,
        )
        uc, _ = _build_use_case(campaign)
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        cs = out.unwrap()["compound_source"]
        assert cs["kind"] == expected_kind
        assert ref_key in cs["ref"]

    # ------------------------------------------------------------------
    # 4. Pagination — 5 results, page_size=2
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pagination_five_results(self) -> None:
        auth = fake_auth()
        campaign, _ = _make_closed_campaign(
            auth.workspace_id,
            n_results=5,
            decisions=[CampaignDecision.SELECTED] * 5,
        )

        uc, _ = _build_use_case(campaign)

        # Page 1: offset=0 → 2 results, next_cursor="2".
        q1 = _make_query(auth.workspace_id, campaign.id, page_size=2)
        out1 = await uc(q1, auth=auth)
        assert isinstance(out1, Success)
        doc1 = out1.unwrap()
        assert len(doc1["results"]) == 2
        assert doc1["pagination"]["next_cursor"] == "2"
        assert doc1["pagination"]["total"] == 5

        # Page 2: offset=2 → 2 results, next_cursor="4".
        q2 = _make_query(auth.workspace_id, campaign.id, cursor="2", page_size=2)
        out2 = await uc(q2, auth=auth)
        assert isinstance(out2, Success)
        doc2 = out2.unwrap()
        assert len(doc2["results"]) == 2
        assert doc2["pagination"]["next_cursor"] == "4"

        # Page 3: offset=4 → 1 result, next_cursor=None.
        q3 = _make_query(auth.workspace_id, campaign.id, cursor="4", page_size=2)
        out3 = await uc(q3, auth=auth)
        assert isinstance(out3, Success)
        doc3 = out3.unwrap()
        assert len(doc3["results"]) == 1
        assert doc3["pagination"]["next_cursor"] is None

    # ------------------------------------------------------------------
    # 5. Campaign not found → Failure(NotFoundError)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_campaign_not_found(self) -> None:
        auth = fake_auth()
        uc, _ = _build_use_case(campaign=None)
        q = _make_query(auth.workspace_id, uuid.uuid4())
        out = await uc(q, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)

    # ------------------------------------------------------------------
    # 6. Campaign in DRAFT → Failure(ValidationError)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_draft_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        draft = Campaign(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="Draft Campaign",
            status=CampaignStatus.DRAFT,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
            publishes_collection=False,
            created_by=uuid.uuid4(),
        )
        uc, _ = _build_use_case(draft)
        q = _make_query(auth.workspace_id, draft.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Failure)
        err = out.failure()
        assert isinstance(err, ValidationError)
        assert "closed/superseded" in str(err).lower()

    # ------------------------------------------------------------------
    # 7. Signature is None → "signature": null in output
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_signature_none_emits_null(self) -> None:
        auth = fake_auth()
        campaign, _ = _make_closed_campaign(
            auth.workspace_id,
            signature_id=None,  # force no signature
        )
        # Patch signature_id directly since _make_closed_campaign always sets one.
        object.__setattr__(campaign, "signature_id", None) if False else None
        campaign.signature_id = None  # type: ignore[misc]

        uc, _ = _build_use_case(campaign)
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap()["campaign"]["signature"] is None

    # ------------------------------------------------------------------
    # 8. Missing protocol in lookup → protocol_ref with nulls (defensive)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_missing_protocol_emits_null_protocol_ref(self) -> None:
        auth = fake_auth()
        # Channel will reference a protocol_id that the repo won't return.
        pid = uuid.uuid4()
        rdid = uuid.uuid4()
        campaign, _ = _make_closed_campaign(
            auth.workspace_id,
            protocol_id=pid,
            readout_definition_id=rdid,
        )

        # protocol_repo returns nothing (empty list).
        uc, _ = _build_use_case(campaign)  # no protocol_id kwarg → empty return

        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        doc = out.unwrap()
        # Should not fail; channel's protocol_ref should have nulls.
        assert len(doc["channels"]) == 1
        pref = doc["channels"][0]["protocol_ref"]
        assert pref["id"] == str(pid)
        assert pref["name"] is None
        assert pref["version"] is None

    # ------------------------------------------------------------------
    # 9. Unauthorized (viewer role) → Failure(AuthorizationError)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, _ = _make_closed_campaign(auth.workspace_id)

        uc, _ = _build_use_case(campaign)
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)

    # ------------------------------------------------------------------
    # 10. Superseded campaign is also publishable
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_superseded_campaign_is_valid(self) -> None:
        auth = fake_auth()
        campaign, _ = _make_closed_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.SUPERSEDED  # type: ignore[misc]

        uc, _ = _build_use_case(campaign)
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap()["campaign"]["status"] == "superseded"

    # ------------------------------------------------------------------
    # 11. Molecule and batch resolution in results
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_molecule_and_batch_resolved_in_results(self) -> None:
        auth = fake_auth()
        mol_id = uuid.uuid4()
        batch_id = uuid.uuid4()

        campaign, _ = _make_closed_campaign(
            auth.workspace_id,
            n_results=1,
            decisions=[CampaignDecision.SELECTED],
        )
        # Override the molecule_id on the single result and set batch.
        campaign.results[0].molecule_id = mol_id
        campaign.results[0].representative_batch_id = batch_id

        fake_mol = AsyncMock()
        fake_mol.id = mol_id
        fake_mol.registration_number = AsyncMock()
        fake_mol.registration_number.value = "CVT-000142"
        fake_mol.name = "Compound A"
        fake_mol.structure = AsyncMock()
        fake_mol.structure.smiles = "CCO"

        fake_batch = AsyncMock()
        fake_batch.id = batch_id
        fake_batch.batch_number = AsyncMock()
        fake_batch.batch_number.value = "BAT-000171"

        uc, _ = _build_use_case(
            campaign,
            molecule_lookup={mol_id: fake_mol},
            batch_lookup={batch_id: fake_batch},
        )
        q = _make_query(auth.workspace_id, campaign.id)
        out = await uc(q, auth=auth)

        assert isinstance(out, Success)
        result = out.unwrap()["results"][0]
        assert result["molecule"]["primary_id"] == "CVT-000142"
        assert result["molecule"]["structure_smiles"] == "CCO"
        assert result["representative_batch"]["name"] == "BAT-000171"
