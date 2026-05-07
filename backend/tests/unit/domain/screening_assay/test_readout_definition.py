"""Tests for ReadoutDefinition.normalizations (set-valued) and ReadoutData.normalization_applied."""

from __future__ import annotations

import uuid

import pytest

from chem_vault.domain.screening_assay.enums import (
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.protocol import ReadoutDefinition
from chem_vault.domain.screening_assay.readout_data import ReadoutData


class TestReadoutDefinitionNormalizations:
    def test_supports_multiple_normalizations(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name="Raw Data",
            data_type=ReadoutDataType.NUMERIC,
            normalizations=frozenset(
                {
                    ReadoutNormalization.PERCENT_INHIBITION,
                    ReadoutNormalization.Z_SCORE,
                }
            ),
        )
        assert ReadoutNormalization.PERCENT_INHIBITION in rd.normalizations
        assert ReadoutNormalization.Z_SCORE in rd.normalizations
        assert len(rd.normalizations) == 2

    def test_empty_normalizations_means_raw_only(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
            normalizations=frozenset(),
        )
        assert rd.normalizations == frozenset()

    def test_default_normalizations_is_empty_frozenset(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        assert rd.normalizations == frozenset()

    # Tests for the legacy single-value `normalization=` kwarg removed —
    # the kwarg is gone; callers pass `normalizations=` directly.


class TestReadoutDataNormalizationApplied:
    def test_default_normalization_applied_is_none(self) -> None:
        rd = ReadoutData(
            workspace_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
        )
        assert rd.normalization_applied is None

    def test_normalization_applied_can_be_set(self) -> None:
        rd = ReadoutData(
            workspace_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            is_computed=True,
            normalization_applied=ReadoutNormalization.PERCENT_INHIBITION,
        )
        assert rd.normalization_applied == ReadoutNormalization.PERCENT_INHIBITION
