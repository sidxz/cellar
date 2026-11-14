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


# ---- Series values (descriptive per-batch values from a window) ----


@pytest.mark.parametrize("threshold", [0.0, -1.0, float("inf"), float("nan")])
def test_lowest_shift_threshold_must_be_positive_and_finite(threshold):
    with pytest.raises(ValidationError):
        _cfg(measure=MeltMeasure.LOWEST_SHIFT_CONCENTRATION, threshold=threshold)


def test_threshold_only_on_lowest_shift_concentration():
    with pytest.raises(ValidationError):
        _cfg(measure=MeltMeasure.DELTA_TM, threshold=2.0)
    with pytest.raises(ValidationError):
        _cfg(measure=MeltMeasure.LOWEST_SHIFT_CONCENTRATION)


def test_concentration_only_on_delta_tm_at_concentration():
    with pytest.raises(ValidationError):
        _cfg(measure=MeltMeasure.MAX_DELTA_TM, concentration=50.0)
    with pytest.raises(ValidationError):
        _cfg(measure=MeltMeasure.DELTA_TM_AT_CONCENTRATION)
    for bad in [0.0, -5.0, float("inf")]:
        with pytest.raises(ValidationError):
            _cfg(measure=MeltMeasure.DELTA_TM_AT_CONCENTRATION, concentration=bad)


def test_to_dict_omits_unset_parameters():
    d = _cfg(measure=MeltMeasure.TM).to_dict()
    assert "threshold" not in d and "concentration" not in d


@pytest.mark.parametrize(
    "over",
    [
        dict(measure=MeltMeasure.MAX_DELTA_TM),
        dict(measure=MeltMeasure.LOWEST_SHIFT_CONCENTRATION, threshold=2.0),
        dict(measure=MeltMeasure.DELTA_TM_AT_CONCENTRATION, concentration=50.0),
    ],
)
def test_series_measures_round_trip(over):
    c = _cfg(**over)
    assert c.measure.is_series
    assert MeltReadoutConfig.from_dict(c.to_dict()) == c


def test_per_position_measures_are_not_series():
    assert not MeltMeasure.TM.is_series and not MeltMeasure.DELTA_TM.is_series


def _at(c: float, name: str | None = None) -> ReadoutDefinition:
    return _melt_rd(
        name or f"ΔTm at {c:g} µM (Main)",
        melt_config=_cfg(measure=MeltMeasure.DELTA_TM_AT_CONCENTRATION, concentration=c),
    )


def test_window_allows_two_delta_tm_at_different_concentrations():
    p = _protocol()
    p.add_readout_definition(_at(10.0))
    p.add_readout_definition(_at(50.0))
    assert len([r for r in p.readout_definitions if r.melt_config]) == 2


def test_window_refuses_same_measure_and_parameter():
    p = _protocol()
    p.add_readout_definition(_at(50.0))
    with pytest.raises(ValidationError, match="Temperature window 'Main'"):
        p.add_readout_definition(_at(50.0, name="Again"))


def _lowest(unit: str | None, **over) -> ReadoutDefinition:
    return _melt_rd(
        "Lowest shifting conc. (Main, ±2 °C)",
        unit=unit,
        melt_config=_cfg(measure=MeltMeasure.LOWEST_SHIFT_CONCENTRATION, threshold=2.0),
        **over,
    )


def test_lowest_shift_concentration_unit_must_be_dose_unit():
    p = _protocol()
    with pytest.raises(ValidationError, match="dose unit"):
        p.add_readout_definition(_lowest("°C"))
    p.add_readout_definition(_lowest(p.dose_unit.value))


def test_series_values_other_than_lowest_need_celsius():
    with pytest.raises(ValidationError, match="°C"):
        _melt_rd("Max ΔTm (Main)", unit="uM", melt_config=_cfg(measure=MeltMeasure.MAX_DELTA_TM))


def test_geometric_mean_only_for_lowest_shift_concentration():
    with pytest.raises(ValidationError, match="geometric mean"):
        _melt_rd(
            "Max ΔTm (Main)",
            aggregation=ReadoutAggregation.GEOMETRIC_MEAN,
            melt_config=_cfg(measure=MeltMeasure.MAX_DELTA_TM),
        )
    _lowest("uM", aggregation=ReadoutAggregation.GEOMETRIC_MEAN)


def test_series_readout_names():
    p = _protocol()
    p.add_readout_definition(_melt_rd("Tm (Main)"))
    p.add_readout_definition(
        _melt_rd("Max ΔTm (Main)", melt_config=_cfg(measure=MeltMeasure.MAX_DELTA_TM))
    )
    p.add_readout_definition(_at(50.0))
    assert p.series_readout_names() == frozenset({"Max ΔTm (Main)", "ΔTm at 50 µM (Main)"})


def test_lowest_shift_concentration_unit_cannot_be_edited_away_from_dose_unit():
    p = _protocol()
    rd = _lowest(p.dose_unit.value)
    p.add_readout_definition(rd)
    with pytest.raises(ValidationError, match="dose unit"):
        p.update_readout_definition(rd.id, unit="nM")
