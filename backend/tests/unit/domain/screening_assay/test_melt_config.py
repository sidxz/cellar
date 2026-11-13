"""Melt configuration on a readout definition: validation, derived flag, window agreement."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, ValidationError
from tests.unit.domain.screening_assay.test_protocol import _make_protocol


def _cfg(**over) -> MeltReadoutConfig:
    args = dict(
        window=" Main ", measure=MeltMeasure.DELTA_TM, channel_key="ratio", low=50.0, high=85.0
    )
    args.update(over)
    return MeltReadoutConfig(**args)


def _melt_rd(name: str = "Tm (Main)", **over) -> ReadoutDefinition:
    args = dict(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        aggregation=ReadoutAggregation.MEAN,
        melt_config=_cfg(measure=MeltMeasure.TM),
    )
    args.update(over)
    return ReadoutDefinition(**args)


def test_melt_config_round_trips_and_validates():
    c = _cfg()
    assert c.window == "Main" and MeltReadoutConfig.from_dict(c.to_dict()) == c
    for bad in [
        dict(low=85.0, high=50.0),
        dict(low=float("nan")),
        dict(window=""),
        dict(window="x" * 61),
        dict(channel_key=" "),
    ]:
        with pytest.raises(ValidationError):
            _cfg(**bad)


@pytest.mark.parametrize(
    "over",
    [
        dict(data_type=ReadoutDataType.TEXT),
        dict(unit="%"),
        dict(unit=None),
        dict(is_calculated=True, calculation_formula="[A]"),
        dict(normalizations=frozenset({ReadoutNormalization.PERCENT_INHIBITION})),
        dict(aggregation=ReadoutAggregation.GEOMETRIC_MEAN),
        dict(dose_response_config=DoseResponseConfig(CurveType.IC50, "Tm (Main)")),
    ],
)
def test_melt_readout_must_be_numeric_celsius_without_formula_or_normalization(over):
    with pytest.raises(ValidationError, match="Tm \\(Main\\)"):
        _melt_rd(**over)


def test_melt_readout_is_derived():
    plain = ReadoutDefinition(
        protocol_id=uuid.uuid4(), name="A", data_type=ReadoutDataType.NUMERIC
    )
    calc = ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name="B",
        data_type=ReadoutDataType.NUMERIC,
        is_calculated=True,
        calculation_formula="[A]",
    )
    assert _melt_rd().is_derived and calc.is_derived and not plain.is_derived


def _protocol():
    return _make_protocol(uuid.uuid4(), uuid.uuid4())


def test_window_readouts_must_agree_and_differ_in_measure():
    p = _protocol()
    p.add_readout_definition(_melt_rd("Tm (Main)"))
    p.add_readout_definition(
        _melt_rd("ΔTm (Main)", melt_config=_cfg(measure=MeltMeasure.DELTA_TM))
    )
    with pytest.raises(ValidationError, match="Temperature window 'Main'"):
        p.add_readout_definition(_melt_rd("Tm again", melt_config=_cfg(measure=MeltMeasure.TM)))
    p2 = _protocol()
    p2.add_readout_definition(_melt_rd("Tm (Main)"))
    with pytest.raises(ValidationError, match="Temperature window 'Main'"):
        p2.add_readout_definition(
            _melt_rd("ΔTm (Main)", melt_config=_cfg(measure=MeltMeasure.DELTA_TM, high=90.0))
        )
    # A different window name is independent.
    p2.add_readout_definition(
        _melt_rd("Tm (Low)", melt_config=_cfg(window="Low", measure=MeltMeasure.TM, high=60.0))
    )


def test_changing_melt_config_on_active_protocol_needs_a_new_version():
    p = _protocol()
    rd = _melt_rd()
    p.add_readout_definition(rd)
    p.publish()
    with pytest.raises(ConflictError, match="melt_config"):
        p.update_readout_definition(rd.id, melt_config=_cfg(measure=MeltMeasure.TM, high=90.0))
