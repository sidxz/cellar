"""GetProtocolPlateQcAverages: plate QC averaged over a protocol's plates."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.get_protocol_plate_qc_averages import (
    GetProtocolPlateQcAverages,
    GetProtocolPlateQcAveragesQuery,
    Spread,
)
from cellar.domain.shared.errors import NotFoundError
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()
PID = uuid.uuid4()
RD = uuid.uuid4()


def _entry(z, pos, neg, fits=None):
    e = {"z_prime": z, "pos_mean": pos, "pos_sd": 1.0, "neg_mean": neg, "neg_sd": 1.0}
    if fits is not None:
        e["control_fits"] = fits
    return e


def _fit(value, role="positive_control", molecule="m", curve_class="full"):
    return {
        "role": role,
        "molecule_id": molecule,
        "label": "IC50",
        "value": value,
        "curve_class": curve_class,
    }


async def _call(qc_list, auth=None):
    reader = AsyncMock()
    reader.plate_qc_metrics.return_value = qc_list
    uc = GetProtocolPlateQcAverages(reader=reader)
    result = await uc(
        GetProtocolPlateQcAveragesQuery(workspace_id=WS, protocol_id=PID),
        auth=auth or FakeAuth(role="viewer", workspace_id=WS),
    )
    return result, reader


@pytest.mark.asyncio
async def test_each_readout_layer_averages_its_plates() -> None:
    run1 = {
        "z_prime": {"legacy": {}},
        "plates": {
            "p1": {
                str(RD): {
                    "raw": _entry(0.8, 0.07, 0.65),
                    "percent_inhibition": _entry(0.8, 100.0, 0.0, [_fit(0.3)]),
                }
            },
            "p2": {
                str(RD): {"percent_inhibition": _entry(0.6, 98.0, 4.0, [_fit(0.6), _fit(None)])}
            },
        },
    }
    run2 = {"plates": {"p3": {str(RD): {"percent_inhibition": _entry(None, 102.0, -4.0)}}}}
    legacy_only = {"z_prime": {"p9": {"z_prime": 0.5}}}

    result, reader = await _call([run1, run2, legacy_only, {"plates": "junk"}])

    assert isinstance(result, Success)
    reader.plate_qc_metrics.assert_awaited_once_with(WS, PID)
    by_layer = {(a.readout_definition_id, a.layer): a for a in result.unwrap()}
    assert set(by_layer) == {(RD, "raw"), (RD, "percent_inhibition")}
    inh = by_layer[(RD, "percent_inhibition")]
    assert inh.z_prime == Spread(mean=pytest.approx(0.7), sd=pytest.approx(0.1414, abs=1e-4), n=2)
    assert inh.pos_mean == Spread(mean=100.0, sd=2.0, n=3)
    assert inh.neg_mean == Spread(mean=0.0, sd=4.0, n=3)
    assert [(f.role, f.molecule_id, f.label, f.value) for f in inh.control_fits] == [
        (
            "positive_control",
            "m",
            "IC50",
            Spread(mean=pytest.approx(0.45), sd=pytest.approx(0.2121, abs=1e-4), n=2),
        )
    ]
    raw = by_layer[(RD, "raw")]
    assert raw.z_prime == Spread(mean=0.8, sd=None, n=1)
    assert raw.control_fits == []


@pytest.mark.asyncio
async def test_control_potencies_average_per_compound_over_distinct_plates() -> None:
    p1 = [_fit(1.0, molecule="a"), _fit(100.0, molecule="b"), _fit(3.0, molecule="a")]
    p2 = [_fit(None, molecule="a", curve_class="inactive"), _fit(200.0, molecule="b")]
    qc = {
        "plates": {
            "p1": {str(RD): {"raw": _entry(0.8, 1.0, 0.0, p1)}},
            "p2": {str(RD): {"raw": _entry(0.8, 1.0, 0.0, p2)}},
        }
    }

    [avg] = (await _call([qc]))[0].unwrap()

    assert [(f.molecule_id, f.value) for f in avg.control_fits] == [
        ("a", Spread(mean=2.0, sd=None, n=1)),  # p1's two fits are one plate; p2's inactive
        ("b", Spread(mean=150.0, sd=pytest.approx(70.71, abs=0.01), n=2)),
    ]


@pytest.mark.asyncio
async def test_an_unknown_protocol_is_not_found() -> None:
    result, _ = await _call(None)
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_another_workspace_is_refused() -> None:
    with pytest.raises(NotFoundError):
        await _call([], auth=FakeAuth(role="viewer", workspace_id=uuid.uuid4()))
