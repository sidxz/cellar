"""The value layer a dose-response curve is fitted on, and the % scale that layer is read on.

Every fit path (a run's fit, the keeping-edits refit, a curve's refit and its preview) and
every reader that says which layer a curve shows (``fitted_layer`` on the curve payloads)
resolves it here, so fitting and reading can never disagree.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Protocol as _Protocol

from cellar.domain.screening_assay.curve_fitting import ResponseScale
from cellar.domain.screening_assay.enums import ReadoutNormalization, primary_normalization
from cellar.domain.screening_assay.protocol import Protocol

# Layers whose effect rises from 0 % (no effect) to 100 % (full effect). % of control is
# left out: whether it rises or falls depends on the protocol's control convention.
_RISING_PERCENT = frozenset(
    {ReadoutNormalization.PERCENT_INHIBITION, ReadoutNormalization.PERCENT_ACTIVATION}
)


class YReadout(_Protocol):
    """A curve's Y readout as a domain ``ReadoutDefinition`` or a stored row has it."""

    normalizations: Iterable[str]
    is_calculated: bool


def response_scale_for(layer: str | None) -> ResponseScale | None:
    """The scale a fitted layer is read on: 0-100 % for % inhibition and % activation;
    ``None`` (no scale) for raw signal, Z-score and % of control."""
    return ResponseScale() if layer in _RISING_PERCENT else None


def fitted_layer(y_normalization: str | None, y_rd: YReadout) -> str | None:
    """The normalization layer a curve is fitted on: the one its config names
    (``y_normalization``), else its Y readout's primary one. ``None`` for the raw layer
    (a readout that calculates no layer, whatever layer a stored config still names) and
    for a calculated readout's formula values."""
    primary = primary_normalization(y_rd.normalizations)
    if y_rd.is_calculated or primary is None:
        return None
    return str(y_normalization) if y_normalization else primary


def curve_fitted_layer(protocol: Protocol | None, readout_definition_id: uuid.UUID) -> str | None:
    """The layer a curve of ``readout_definition_id`` (its protocol's dose-response
    readout) is fitted on, from the protocol as it is now; ``None`` for the raw layer or
    when the readout is gone."""
    rds = protocol.readout_definitions if protocol is not None else []
    config = next((rd.dose_response_config for rd in rds if rd.id == readout_definition_id), None)
    y_rd = next((rd for rd in rds if config and rd.name == config.y_readout_name), None)
    if config is None or y_rd is None:
        return None
    return fitted_layer(config.y_normalization, y_rd)


def curve_response_scale(
    protocol: Protocol | None, readout_definition_id: uuid.UUID
) -> ResponseScale | None:
    """The scale of the layer a stored curve of ``readout_definition_id`` is fitted on."""
    return response_scale_for(curve_fitted_layer(protocol, readout_definition_id))
