from __future__ import annotations

import uuid

import pytest

from cellar.application.sar_analysis.activity_channel import ActivityChannelSpec
from cellar.application.sar_analysis.activity_enrichment import enrich_to_scalars
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey

_COLUMN = "drc:" + str(uuid.uuid4())


class FakeEnricher:
    def __init__(self, table):
        self._table = table
        self.calls = []

    async def enrich_molecules(
        self, workspace_id, molecule_ids, protocol_columns, *,
        selection_rule, qualifier_handling, run_scopes=None,
    ):
        self.calls.append((list(molecule_ids), list(protocol_columns), selection_rule, run_scopes))
        return {mid: self._table[mid] for mid in molecule_ids if mid in self._table}


def _channel(intercept_key=None) -> ActivityChannelSpec:
    return ActivityChannelSpec(
        column=_COLUMN,
        source="dr_curve",
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
        intercept_key=intercept_key,
    )


@pytest.mark.asyncio
async def test_enrich_to_scalars_picks_primary_value_and_snapshots():
    ws, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=2.0, qualifier=">", unit="uM", source="dose_response")},
    }
    out = await enrich_to_scalars(FakeEnricher(table), workspace_id=ws, molecule_ids=[a, b], channel=_channel())
    by_id = {s.molecule_id: s for s in out}
    assert by_id[a].scalar == 0.5
    assert by_id[a].unit == "uM"
    assert by_id[b].qualifier == ">"
    assert by_id[a].snapshot["value"] == 0.5  # snapshot present


@pytest.mark.asyncio
async def test_enrich_to_scalars_skips_molecules_with_no_value():
    ws, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    table = {
        a: {_COLUMN: ActivityValue(value=0.5, qualifier=None, unit="uM", source="dose_response")},
        b: {_COLUMN: ActivityValue(value=None, qualifier="nd", unit="uM", source="dose_response")},
        # 'a' present, 'b' has no scalar, unknown id dropped by the fake.
    }
    out = await enrich_to_scalars(FakeEnricher(table), workspace_id=ws, molecule_ids=[a, b], channel=_channel())
    assert {s.molecule_id for s in out} == {a}  # b skipped (None scalar -> sparse)


@pytest.mark.asyncio
async def test_enrich_to_scalars_uses_intercept_key():
    ws, a = uuid.uuid4(), uuid.uuid4()
    table = {a: {_COLUMN: ActivityValue(
        value=0.5, qualifier=None, unit="uM", source="dose_response",
        intercept_values=[{"spec": {"kind": "ic", "level": 90.0}, "value": 3.2}],
    )}}
    out = await enrich_to_scalars(
        FakeEnricher(table), workspace_id=ws, molecule_ids=[a],
        channel=_channel(intercept_key=InterceptKey(kind="ic", level=90.0)),
    )
    assert out[0].scalar == 3.2


@pytest.mark.asyncio
async def test_enrich_to_scalars_empty_ids_returns_empty_no_call():
    enricher = FakeEnricher({})
    out = await enrich_to_scalars(enricher, workspace_id=uuid.uuid4(), molecule_ids=[], channel=_channel())
    assert out == []
    assert enricher.calls == []
