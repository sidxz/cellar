"""GetProtocolActivitySummary: a compound's best value follows the readout's direction."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from returns.result import Success

from cellar.application.screening.get_protocol_activity import (
    GetProtocolActivityQuery,
    GetProtocolActivitySummary,
)
from cellar.application.screening.protocol_activity_reader import (
    MoleculeBaseRow,
    NumericReadoutRow,
    ProtocolActivityData,
    ProtocolRow,
)
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()
MOL = uuid.uuid4()


def _rd(name: str, measure: str | None = None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        data_type="numeric",
        unit="°C",
        dose_response_config=None,
        melt_config=None
        if measure is None
        else {
            "window": "Main",
            "measure": measure,
            "channel_key": "ratio",
            "low": 50.0,
            "high": 85.0,
        },
    )


class _Reader:
    def __init__(self, data: ProtocolActivityData) -> None:
        self._data = data

    async def get_activity_data(self, workspace_id, protocol_id, valid_statuses):
        return self._data


@pytest.mark.asyncio
async def test_shift_best_is_the_largest_in_either_direction_and_plain_stays_high():
    rds = [
        _rd("ΔTm (Main)", "delta_tm"),
        _rd("Lowest shifting conc.", "lowest_shift_concentration"),
        _rd("Signal"),
    ]
    row = lambda name, low, high: NumericReadoutRow(  # noqa: E731
        molecule_id=MOL, readout_name=name, best=high, mean=None, n=4, sd=None, low=low
    )
    data = ProtocolActivityData(
        protocol=ProtocolRow(id=uuid.uuid4(), readout_definitions=rds),
        molecule_rows=[MoleculeBaseRow(MOL, "x", "CC-1", None, 2, date(2026, 11, 13))],
        numeric_rows=[
            row("ΔTm (Main)", -8.5, 1.4),
            row("Lowest shifting conc.", 6.25, 50.0),
            row("Signal", 1.0, 9.0),
        ],
    )
    result = await GetProtocolActivitySummary(_Reader(data))(
        GetProtocolActivityQuery(workspace_id=WS, protocol_id=uuid.uuid4()),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert isinstance(result, Success)
    out = result.unwrap()
    readouts = out.items[0].readouts
    assert readouts["ΔTm (Main)"].best == -8.5
    assert readouts["Lowest shifting conc."].best == 6.25
    assert readouts["Signal"].best == 9.0
    directions = {d.name: d.best_direction for d in out.readout_definitions}
    melts = {d.name: d.melt_config for d in out.readout_definitions}
    assert melts["Signal"] is None
    assert melts["ΔTm (Main)"] == {
        "window": "Main",
        "measure": "delta_tm",
        "channel_key": "ratio",
        "low": 50.0,
        "high": 85.0,
    }
    assert directions == {
        "ΔTm (Main)": "magnitude",
        "Lowest shifting conc.": "low",
        "Signal": "high",
    }
