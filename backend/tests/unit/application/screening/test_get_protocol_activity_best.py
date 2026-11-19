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
    BestParamsRow,
    DRAggRow,
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


def _dr_def():
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Potency",
        data_type="dose_response",
        unit="uM",
        dose_response_config={"intercepts": [{"kind": "ec", "level": 50.0}]},
        melt_config=None,
    )


def _iv(level: float, value: float | None, qualifier: str | None = None) -> dict:
    iv = {
        "spec": {"kind": "ec", "level": level, "basis": "relative_percent", "label": None},
        "value": value,
        "ci_low": None,
        "ci_high": None,
        "at_bound": False,
    }
    return iv if qualifier is None else {**iv, "qualifier": qualifier}


def _best_curve(rd_id: uuid.UUID, curve_class: str, intercepts: list[dict]) -> BestParamsRow:
    return BestParamsRow(
        molecule_id=MOL,
        readout_definition_id=rd_id,
        curve_class=curve_class,
        hill_slope=1.0,
        top=95.0,
        bottom=88.0,
        fitted_value=0.5,
        r_squared=0.4,
        raw_data=[{"concentration": d, "response": 92.0} for d in (0.0002, 0.02, 2.0)],
        batch_number=None,
        intercept_values=intercepts,
    )


async def _summary(rd, dr_row: DRAggRow, best: BestParamsRow):
    data = ProtocolActivityData(
        protocol=ProtocolRow(id=uuid.uuid4(), readout_definitions=[rd]),
        molecule_rows=[MoleculeBaseRow(MOL, "x", "CC-1", None, 1, date(2026, 11, 19))],
        dr_agg_rows=[dr_row],
        best_params_rows=[best],
    )
    result = await GetProtocolActivitySummary(_Reader(data))(
        GetProtocolActivityQuery(workspace_id=WS, protocol_id=uuid.uuid4()),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert isinstance(result, Success)
    return result.unwrap()


@pytest.mark.asyncio
async def test_the_best_curves_intercepts_carry_their_qualifiers_and_nd_has_no_value():
    rd = _dr_def()
    ivs = [_iv(50.0, 0.5, "="), _iv(90.0, None, "nd"), _iv(10.0, 0.1)]
    best = _best_curve(rd.id, "partial", ivs)
    dr_row = DRAggRow(MOL, rd.id, best=0.5, geo_mean=0.5, n_tested=1, n_used=1)

    out = await _summary(rd, dr_row, best)

    ivs = out.items[0].readouts["Potency"].curve_params.intercept_values
    assert [(iv.spec.level, iv.value, iv.qualifier) for iv in ivs] == [
        (50.0, 0.5, "="),
        (90.0, None, "nd"),
        (10.0, 0.1, None),  # fitted before qualifiers
    ]
