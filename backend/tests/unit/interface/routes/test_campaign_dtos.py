"""Unit tests for the campaign interface-DTO projections (_campaign_dtos)."""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.source_ref import (
    CollectionRef,
    RunRef,
)
from cellar.interface.routes._campaign_dtos import _derive_compound_sources


def _result(campaign_id: uuid.UUID, added_from) -> CampaignResult:
    return CampaignResult(
        campaign_id=campaign_id,
        molecule_id=uuid.uuid4(),
        added_from=added_from,
    )


class TestDeriveCompoundSources:
    def test_two_runs_no_description_stay_distinct(self) -> None:
        """Two runs with description=None must group by run_id, not collapse.

        Reproduces the production bug: the add-run wizard records a RunRef
        with description=None, so two distinct runs were merged into one
        ("run", None) bucket — losing the second source row.
        """
        campaign_id = uuid.uuid4()
        run_a = uuid.uuid4()
        run_b = uuid.uuid4()
        results = [
            _result(campaign_id, RunRef(run_id=run_a)),
            _result(campaign_id, RunRef(run_id=run_b)),
            _result(campaign_id, RunRef(run_id=run_b)),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 2
        by_run = {s["run_id"]: s["count"] for s in sources}
        assert by_run == {str(run_a): 1, str(run_b): 2}

    def test_same_run_groups_into_one(self) -> None:
        campaign_id = uuid.uuid4()
        run = uuid.uuid4()
        results = [
            _result(campaign_id, RunRef(run_id=run)),
            _result(campaign_id, RunRef(run_id=run)),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 1
        assert sources[0]["run_id"] == str(run)
        assert sources[0]["count"] == 2

    def test_two_collections_no_description_stay_distinct(self) -> None:
        campaign_id = uuid.uuid4()
        coll_a = uuid.uuid4()
        coll_b = uuid.uuid4()
        results = [
            _result(campaign_id, CollectionRef(collection_id=coll_a)),
            _result(campaign_id, CollectionRef(collection_id=coll_b)),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 2
        by_coll = {s["collection_id"]: s["count"] for s in sources}
        assert by_coll == {str(coll_a): 1, str(coll_b): 1}

    def test_all_manual_group_into_one(self) -> None:
        campaign_id = uuid.uuid4()
        results = [
            _result(campaign_id, None),
            _result(campaign_id, None),
            _result(campaign_id, None),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 1
        assert sources[0]["kind"] == "manual"
        assert sources[0]["count"] == 3
