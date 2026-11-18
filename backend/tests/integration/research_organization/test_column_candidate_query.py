"""SQL ColumnCandidateQuery: one round trip per column, with the facts the
resolver groups on (well dose or the run's Test concentration, batch, replicates)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.measurement_facts import (
    TEST_CONCENTRATION,
    Concentration,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.column_candidate_query import (  # noqa: E501
    SQLAlchemyColumnCandidateQuery,
)
from tests.integration import _screening_seed as seed


def _channel(
    protocol_id: uuid.UUID, rd_id: uuid.UUID, kind: ChannelSourceKind, norm: str | None = None
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=protocol_id,
        readout_definition_id=rd_id,
        source_kind=kind,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        normalization_applied=norm,
    )


@pytest.mark.asyncio
async def test_fetch_joins_well_dose_and_condition(uow, session_factory, workspace_id):
    ws = workspace_id
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m")
        b1, b2 = await seed.batch(s, ws, mol, "B1"), await seed.batch(s, ws, mol, "B2")
        p = await seed.protocol(
            s, ws, dose_unit="nM", conditions=[(TEST_CONCENTRATION, "numeric", "uM")]
        )
        rd = await seed.readout_def(s, p, name="Signal", aggregation="median")
        plate_run = await seed.run(s, ws, p, date(2026, 1, 1), conditions={TEST_CONCENTRATION: 10})
        plate = await seed.plate(s, plate_run, 1)
        dosed = await seed.well(s, plate, "A", 1, dose=500.0, batch_id=b1)
        undosed = await seed.well(s, plate, "A", 2)
        control = await seed.well(s, plate, "A", 3, well_type="positive_control")
        await seed.readout(s, ws, plate_run, rd, mol, 40.0, well_id=dosed)
        await seed.readout(s, ws, plate_run, rd, mol, 41.0, well_id=undosed, batch_id=b2)
        await seed.readout(s, ws, plate_run, rd, mol, 99.0, well_id=control)
        await seed.readout(s, ws, plate_run, rd, mol, 1.0, well_id=dosed, outlier=True)
        summary = await seed.run(
            s, ws, p, date(2026, 2, 1), conditions={TEST_CONCENTRATION: "500 nM"}
        )
        await seed.readout(
            s, ws, summary, rd, mol, 7.5, wellless=True, batch_id=b2, replicate_count=3
        )
        bare = await seed.run(s, ws, p, date(2026, 3, 1))
        await seed.readout(s, ws, bare, rd, mol, 9.0, wellless=True)
        await uow.commit()

    out = await SQLAlchemyColumnCandidateQuery(session_factory).fetch(
        workspace_id=ws,
        channel=_channel(p, rd, ChannelSourceKind.READOUT_DATA),
        run_ids=None,
        molecule_ids=None,
    )

    facts = {
        c.run.value: (c.run.run_id, c.dose, c.batch_id, c.well_id is None, c.replicate_count)
        for c in out[mol]
    }
    assert facts == {
        # The well's dose wins over the run's condition, in the protocol's dose unit.
        40.0: (plate_run, Concentration(500.0, "nM"), b1, False, None),
        # No well dose: the run's bare-number condition, in the definition's unit.
        41.0: (plate_run, Concentration(10.0, "µM"), b2, False, None),
        7.5: (summary, Concentration(500.0, "nM"), b2, True, 3),
        9.0: (bare, None, None, True, None),
    }
    assert {c.aggregation for c in out[mol]} == {"median"}


@pytest.mark.asyncio
async def test_fetch_run_and_molecule_filters(uow, session_factory, workspace_id):
    ws = workspace_id
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        m1, m2 = await seed.molecule(s, ws, org, "m1"), await seed.molecule(s, ws, org, "m2")
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal")
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        ra = await seed.run(s, ws, p, date(2026, 1, 1))
        rb = await seed.run(s, ws, p, date(2026, 2, 1))
        curves = {}
        for run in (ra, rb):
            for mol in (m1, m2):
                await seed.readout(s, ws, run, signal, mol, 10.0)
                # with_well: a per-well response on the IC50 definition, never an endpoint.
                curves[run, mol] = await seed.curve(s, ws, p, run, mol, ic50)
        await seed.readout(s, ws, rb, ic50, m2, 3.3, wellless=True)
        await uow.commit()

    query = SQLAlchemyColumnCandidateQuery(session_factory)
    readout = _channel(p, signal, ChannelSourceKind.READOUT_DATA)

    scoped = await query.fetch(workspace_id=ws, channel=readout, run_ids=[ra], molecule_ids=[m1])
    assert {m: [c.run.run_id for c in cs] for m, cs in scoped.items()} == {m1: [ra]}

    every = await query.fetch(workspace_id=ws, channel=readout, run_ids=None, molecule_ids=None)
    assert {m: sorted(c.run.run_id for c in cs) for m, cs in every.items()} == {
        m1: sorted([ra, rb]),
        m2: sorted([ra, rb]),
    }

    assert await query.fetch(workspace_id=ws, channel=readout, run_ids=[], molecule_ids=None) == {}
    assert (
        await query.fetch(
            workspace_id=uuid.uuid4(), channel=readout, run_ids=None, molecule_ids=None
        )
        == {}
    )

    dr = _channel(p, ic50, ChannelSourceKind.DOSE_RESPONSE_CURVE)
    out = await query.fetch(workspace_id=ws, channel=dr, run_ids=[rb], molecule_ids=[m2])
    assert list(out) == [m2]
    by_kind = {c.run.curve_id is not None: c for c in out[m2]}
    assert len(out[m2]) == 2  # the curve, plus the well-less endpoint (D1)
    assert by_kind[True].run.curve_id == curves[rb, m2]
    assert by_kind[True].batch_id is not None
    assert by_kind[True].dose is None
    assert by_kind[False].run.value == 3.3
    assert by_kind[False].well_id is None
