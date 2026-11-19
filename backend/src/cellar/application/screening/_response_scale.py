"""The value layer a dose-response curve is fitted on, and the % scale that layer is read on.

Every fit path (a run's fit, the keeping-edits refit, a curve's refit and its preview)
resolves both here, so a flat curve is judged against the same scale wherever it is fitted.
"""

from __future__ import annotations

import uuid

from cellar.domain.screening_assay.curve_fitting import ResponseScale
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import ReadoutNormalization, primary_normalization
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition

# Layers whose effect rises from 0 % (no effect) to 100 % (full effect). % of control is
# left out: whether it rises or falls depends on the protocol's control convention.
_RISING_PERCENT = frozenset(
    {ReadoutNormalization.PERCENT_INHIBITION, ReadoutNormalization.PERCENT_ACTIVATION}
)


def response_scale_for(layer: str | None) -> ResponseScale | None:
    """The scale a fitted layer is read on: 0-100 % for % inhibition and % activation;
    ``None`` (no scale) for raw signal, Z-score and % of control."""
    return ResponseScale() if layer in _RISING_PERCENT else None


def fitted_layer(config: DoseResponseConfig, y_rd: ReadoutDefinition) -> str | None:
    """The normalization layer a curve of ``config`` is fitted on: the one it names, else
    its Y readout's primary one. ``None`` for the raw layer (a readout that calculates no
    layer, whatever layer a stored config still names) and for a calculated readout's
    formula values."""
    primary = primary_normalization(y_rd.normalizations)
    if y_rd.is_calculated or primary is None:
        return None
    return config.y_normalization or primary


def curve_response_scale(
    protocol: Protocol | None, readout_definition_id: uuid.UUID
) -> ResponseScale | None:
    """The scale of the layer a stored curve of ``readout_definition_id`` (its protocol's
    dose-response readout) is fitted on; ``None`` when the readout is gone."""
    rds = protocol.readout_definitions if protocol is not None else []
    config = next((rd.dose_response_config for rd in rds if rd.id == readout_definition_id), None)
    y_rd = next((rd for rd in rds if config and rd.name == config.y_readout_name), None)
    if config is None or y_rd is None:
        return None
    return response_scale_for(fitted_layer(config, y_rd))
