"""Unit tests for ``calculated_readout_error`` — the shared import guard."""

from __future__ import annotations

import uuid

from cellar.application.screening.readout_entry_guard import calculated_readout_error
from cellar.domain.screening_assay.enums import ReadoutDataType
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.shared.errors import ValidationError


def _rd(name: str, *, is_calculated: bool = False) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.NUMERIC,
        is_calculated=is_calculated,
        calculation_formula="[Raw] * 2" if is_calculated else None,
    )


class TestCalculatedReadoutError:
    def test_none_when_target_is_a_plain_readout(self) -> None:
        raw = _rd("Raw Data")

        assert calculated_readout_error([("Raw Data", raw.id)], {raw.id: raw}) is None

    def test_error_names_the_column_and_the_readout(self) -> None:
        raw = _rd("Raw Data")
        pct = _rd("Percent Inhibition", is_calculated=True)

        error = calculated_readout_error(
            [("Raw Data", raw.id), ("% Inhibition", pct.id)],
            {raw.id: raw, pct.id: pct},
        )

        assert isinstance(error, ValidationError)
        assert "% Inhibition" in str(error)
        assert "Percent Inhibition" in str(error)
        assert "calculated" in str(error)

    def test_none_for_an_unknown_id(self) -> None:
        # Protocol membership is the caller's check — an id we know nothing
        # about is not this guard's business.
        assert calculated_readout_error([("Mystery", uuid.uuid4())], {}) is None

    def test_none_for_an_empty_mapping(self) -> None:
        assert calculated_readout_error([], {}) is None
