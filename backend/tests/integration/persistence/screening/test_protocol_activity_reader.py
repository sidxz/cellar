"""Protocol Activity summary over the real SQL reader: one normalization layer per readout."""

from __future__ import annotations

import uuid
from datetime import date

from returns.result import Success

from cellar.application.screening.get_protocol_activity import (
    ActivitySummaryV2,
    GetProtocolActivityQuery,
    GetProtocolActivitySummary,
)
from cellar.domain.screening_assay.enums import primary_normalization
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_activity_reader import (
    SQLAlchemyProtocolActivityReader,
)
from tests.fakes.fake_auth import FakeAuth
from tests.integration import _screening_seed as seed


async def _summary(
    uow,
    session_factory,
    ws: uuid.UUID,
    *,
    unit: str,
    normalizations: list[str],
    rows: list[tuple[float, str | None]],
) -> ActivitySummaryV2:
    """One compound, one completed run, readout "Signal" with ``rows`` (value, layer)."""
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", unit=unit, normalizations=normalizations)
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="completed")
        for value, layer in rows:
            await seed.readout(s, ws, run, rd, mol, value, normalization=layer)
        await uow.commit()
    result = await GetProtocolActivitySummary(SQLAlchemyProtocolActivityReader(session_factory))(
        GetProtocolActivityQuery(workspace_id=ws, protocol_id=p),
        auth=FakeAuth(role="viewer", workspace_id=ws),
    )
    assert isinstance(result, Success)
    return result.unwrap()


async def test_primary_layer_is_read_alone_when_it_has_data(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="RFU",
        normalizations=["percent_inhibition"],
        rows=[
            (1000.0, None),
            (3000.0, None),
            (40.0, "percent_inhibition"),
            (60.0, "percent_inhibition"),
        ],
    )

    signal = out.items[0].readouts["Signal"]
    assert (signal.mean, signal.n, signal.best) == (50.0, 2, 60.0)
    assert out.readout_definitions[0].unit == "%"


async def test_raw_layer_when_the_primary_has_no_data(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="RFU",
        normalizations=["percent_control"],
        rows=[(10.0, None), (20.0, None)],
    )

    assert out.items[0].readouts["Signal"].mean == 15.0
    assert out.readout_definitions[0].unit == "RFU"


async def test_readout_without_normalizations_reads_raw(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="RFU",
        normalizations=[],
        rows=[(1.0, None), (3.0, None)],
    )

    assert out.items[0].readouts["Signal"].mean == 2.0


def test_primary_normalization_skips_none():
    assert primary_normalization(["none", "z_score"]) == "z_score"
    assert primary_normalization([]) is None
    assert primary_normalization(None) is None
