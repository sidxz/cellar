"""The layer a curve is fitted on, resolved one way for fitting and for reading."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest

from cellar.application.screening._response_scale import curve_fitted_layer, fitted_layer
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveType,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition

PI, Z = ReadoutNormalization.PERCENT_INHIBITION, ReadoutNormalization.Z_SCORE


def _protocol(normalizations, y_normalization=None) -> tuple[Protocol, uuid.UUID]:
    pid = uuid.uuid4()
    protocol = Protocol.create(
        workspace_id=uuid.uuid4(),
        name="DR",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=pid,
                name="Signal",
                data_type=ReadoutDataType.NUMERIC,
                normalizations=frozenset(normalizations),
            ),
            ReadoutDefinition(
                protocol_id=pid,
                name="IC50",
                data_type=ReadoutDataType.DOSE_RESPONSE,
                dose_response_config=DoseResponseConfig(
                    curve_type=CurveType.IC50,
                    y_readout_name="Signal",
                    y_normalization=y_normalization if y_normalization in normalizations else None,
                ),
            ),
        ],
    )
    dr = next(rd for rd in protocol.readout_definitions if rd.name == "IC50")
    assert dr.dose_response_config is not None
    # A stored curve's config may still name a layer its readout no longer calculates.
    dr.dose_response_config = replace(dr.dose_response_config, y_normalization=y_normalization)
    return protocol, dr.id


@pytest.mark.parametrize(
    ("normalizations", "y_normalization", "layer"),
    [
        ({PI}, None, "percent_inhibition"),  # the Y readout's primary layer
        ({PI, Z}, Z, "z_score"),  # the one the config names
        (set(), None, None),  # raw
        (set(), PI, None),  # a stale name on a readout that calculates no layer
    ],
)
def test_a_curve_reads_the_layer_its_readout_is_fitted_on(normalizations, y_normalization, layer):
    protocol, dr_id = _protocol(normalizations, y_normalization)
    assert curve_fitted_layer(protocol, dr_id) == layer


def test_no_layer_for_a_readout_that_is_gone_or_a_calculated_y():
    protocol, dr_id = _protocol({PI})
    assert curve_fitted_layer(protocol, uuid.uuid4()) is None
    assert curve_fitted_layer(None, dr_id) is None
    y = next(rd for rd in protocol.readout_definitions if rd.name == "Signal")
    y.is_calculated = True
    assert fitted_layer(None, y) is None


def test_a_stored_row_resolves_like_the_domain_readout():
    """SQL readers pass the stored config's string and the Y readout's row as is."""

    from types import SimpleNamespace

    row = SimpleNamespace(normalizations=["none", "percent_inhibition"], is_calculated=False)
    assert fitted_layer(None, row) == "percent_inhibition"
    assert fitted_layer("percent_inhibition", row) == "percent_inhibition"
