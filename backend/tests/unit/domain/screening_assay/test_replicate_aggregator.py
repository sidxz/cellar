"""Tests for ReplicateAggregator domain service."""

from __future__ import annotations

import math
import statistics
import uuid
from uuid import uuid4

import pytest

from chem_vault.domain.screening_assay.enums import ReadoutAggregation
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.replicate_aggregator import (
    AggregatedValue,
    ReplicateAggregator,
)
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import QualifiedValue
from returns.result import Failure, Success


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_readout_data(
    molecule_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    value: float,
) -> ReadoutData:
    return ReadoutData(
        workspace_id=uuid4(),
        run_id=uuid4(),
        molecule_id=molecule_id,
        batch_id=uuid4(),
        readout_definition_id=readout_definition_id,
        value=QualifiedValue(value=value),
    )


# ---------------------------------------------------------------------------
# TestMean
# ---------------------------------------------------------------------------


class TestMean:
    def test_mean_of_replicates(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 10.0),
            _make_readout_data(mol, rd, 20.0),
            _make_readout_data(mol, rd, 30.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        assert values[0].value == pytest.approx(20.0)
        assert values[0].count == 3
        assert values[0].stdev == pytest.approx(statistics.stdev([10.0, 20.0, 30.0]))
        assert values[0].molecule_id == mol
        assert values[0].readout_definition_id == rd

    def test_single_value_passthrough(self) -> None:
        """Single readout: count=1, stdev=None."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [_make_readout_data(mol, rd, 42.0)]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        assert values[0].value == pytest.approx(42.0)
        assert values[0].count == 1
        assert values[0].stdev is None

    def test_two_values_stdev_computed(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 5.0),
            _make_readout_data(mol, rd, 15.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert values[0].value == pytest.approx(10.0)
        assert values[0].count == 2
        assert values[0].stdev == pytest.approx(statistics.stdev([5.0, 15.0]))

    def test_none_value_readouts_skipped(self) -> None:
        """ReadoutData with value=None are silently skipped."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()

        # One readout with value, one without
        r1 = _make_readout_data(mol, rd, 100.0)
        r2 = ReadoutData(
            workspace_id=uuid4(),
            run_id=uuid4(),
            molecule_id=mol,
            batch_id=uuid4(),
            readout_definition_id=rd,
            value=None,
        )

        result = aggregator.aggregate([r1, r2], ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        assert values[0].value == pytest.approx(100.0)
        assert values[0].count == 1


# ---------------------------------------------------------------------------
# TestMedian
# ---------------------------------------------------------------------------


class TestMedian:
    def test_median_of_three_values(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 1.0),
            _make_readout_data(mol, rd, 5.0),
            _make_readout_data(mol, rd, 3.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEDIAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        # median of [1, 5, 3] = 3
        assert values[0].value == pytest.approx(3.0)
        assert values[0].count == 3

    def test_median_of_even_count(self) -> None:
        """Median of 4 values = average of middle two."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 1.0),
            _make_readout_data(mol, rd, 2.0),
            _make_readout_data(mol, rd, 3.0),
            _make_readout_data(mol, rd, 4.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEDIAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        # median of [1, 2, 3, 4] = 2.5
        assert values[0].value == pytest.approx(2.5)
        assert values[0].count == 4

    def test_single_value_median(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [_make_readout_data(mol, rd, 7.0)]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEDIAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert values[0].value == pytest.approx(7.0)
        assert values[0].count == 1
        assert values[0].stdev is None


# ---------------------------------------------------------------------------
# TestGeometricMean
# ---------------------------------------------------------------------------


class TestGeometricMean:
    def test_geometric_mean_of_two_values(self) -> None:
        """geo_mean(4, 16) = sqrt(64) = 8."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 4.0),
            _make_readout_data(mol, rd, 16.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.GEOMETRIC_MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        assert values[0].value == pytest.approx(8.0)
        assert values[0].count == 2

    def test_geometric_mean_of_three_values(self) -> None:
        """geo_mean(2, 8, 32) = exp(mean(ln(2), ln(8), ln(32)))."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 2.0),
            _make_readout_data(mol, rd, 8.0),
            _make_readout_data(mol, rd, 32.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.GEOMETRIC_MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        expected = math.exp(statistics.mean([math.log(2.0), math.log(8.0), math.log(32.0)]))
        assert values[0].value == pytest.approx(expected)

    def test_negative_value_fails(self) -> None:
        """Negative value → log undefined → Failure(ValidationError)."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 4.0),
            _make_readout_data(mol, rd, -1.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.GEOMETRIC_MEAN)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    def test_zero_value_fails(self) -> None:
        """Zero value → log(0) undefined → Failure(ValidationError)."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 4.0),
            _make_readout_data(mol, rd, 0.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.GEOMETRIC_MEAN)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    def test_single_positive_value_passthrough(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [_make_readout_data(mol, rd, 9.0)]

        result = aggregator.aggregate(readouts, ReadoutAggregation.GEOMETRIC_MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert values[0].value == pytest.approx(9.0)
        assert values[0].count == 1
        assert values[0].stdev is None


# ---------------------------------------------------------------------------
# TestMinMax
# ---------------------------------------------------------------------------


class TestMinMax:
    def test_min_of_replicates(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 50.0),
            _make_readout_data(mol, rd, 10.0),
            _make_readout_data(mol, rd, 30.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MIN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        assert values[0].value == pytest.approx(10.0)
        assert values[0].count == 3

    def test_max_of_replicates(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 50.0),
            _make_readout_data(mol, rd, 10.0),
            _make_readout_data(mol, rd, 30.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MAX)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 1
        assert values[0].value == pytest.approx(50.0)
        assert values[0].count == 3

    def test_single_value_min(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [_make_readout_data(mol, rd, 7.0)]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MIN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert values[0].value == pytest.approx(7.0)
        assert values[0].count == 1
        assert values[0].stdev is None

    def test_single_value_max(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [_make_readout_data(mol, rd, 7.0)]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MAX)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert values[0].value == pytest.approx(7.0)
        assert values[0].count == 1
        assert values[0].stdev is None

    def test_min_stdev_computed_for_multiple(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 2.0),
            _make_readout_data(mol, rd, 8.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MIN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert values[0].stdev == pytest.approx(statistics.stdev([2.0, 8.0]))


# ---------------------------------------------------------------------------
# TestNone
# ---------------------------------------------------------------------------


class TestNone:
    def test_returns_empty_list(self) -> None:
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [
            _make_readout_data(mol, rd, 10.0),
            _make_readout_data(mol, rd, 20.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.NONE)

        assert isinstance(result, Success)
        assert result.unwrap() == []

    def test_returns_empty_list_with_no_readouts(self) -> None:
        aggregator = ReplicateAggregator()

        result = aggregator.aggregate([], ReadoutAggregation.NONE)

        assert isinstance(result, Success)
        assert result.unwrap() == []

    def test_returns_empty_list_regardless_of_readouts(self) -> None:
        """NONE always returns empty, even with lots of readouts."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd = uuid4()
        readouts = [_make_readout_data(mol, rd, float(i)) for i in range(10)]

        result = aggregator.aggregate(readouts, ReadoutAggregation.NONE)

        assert isinstance(result, Success)
        assert result.unwrap() == []


# ---------------------------------------------------------------------------
# TestMultipleMolecules
# ---------------------------------------------------------------------------


class TestMultipleMolecules:
    def test_groups_by_molecule_id(self) -> None:
        """Two molecules, same readout_definition_id → two separate AggregatedValues."""
        aggregator = ReplicateAggregator()
        mol_a = uuid4()
        mol_b = uuid4()
        rd = uuid4()

        readouts = [
            _make_readout_data(mol_a, rd, 10.0),
            _make_readout_data(mol_a, rd, 20.0),
            _make_readout_data(mol_b, rd, 5.0),
            _make_readout_data(mol_b, rd, 15.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 2

        by_mol = {v.molecule_id: v for v in values}
        assert by_mol[mol_a].value == pytest.approx(15.0)  # mean(10, 20)
        assert by_mol[mol_b].value == pytest.approx(10.0)  # mean(5, 15)

    def test_groups_by_readout_definition_id(self) -> None:
        """Same molecule, two different readout_definition_ids → two groups."""
        aggregator = ReplicateAggregator()
        mol = uuid4()
        rd_1 = uuid4()
        rd_2 = uuid4()

        readouts = [
            _make_readout_data(mol, rd_1, 100.0),
            _make_readout_data(mol, rd_1, 200.0),
            _make_readout_data(mol, rd_2, 5.0),
            _make_readout_data(mol, rd_2, 15.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 2

        by_rd = {v.readout_definition_id: v for v in values}
        assert by_rd[rd_1].value == pytest.approx(150.0)  # mean(100, 200)
        assert by_rd[rd_2].value == pytest.approx(10.0)   # mean(5, 15)

    def test_groups_by_molecule_and_readout_definition(self) -> None:
        """2 molecules × 2 readout_definitions → 4 groups."""
        aggregator = ReplicateAggregator()
        mol_a = uuid4()
        mol_b = uuid4()
        rd_1 = uuid4()
        rd_2 = uuid4()

        readouts = [
            # mol_a, rd_1 → mean=3
            _make_readout_data(mol_a, rd_1, 2.0),
            _make_readout_data(mol_a, rd_1, 4.0),
            # mol_a, rd_2 → mean=9
            _make_readout_data(mol_a, rd_2, 8.0),
            _make_readout_data(mol_a, rd_2, 10.0),
            # mol_b, rd_1 → mean=11
            _make_readout_data(mol_b, rd_1, 10.0),
            _make_readout_data(mol_b, rd_1, 12.0),
            # mol_b, rd_2 → mean=20
            _make_readout_data(mol_b, rd_2, 20.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        assert len(values) == 4

        by_key = {(v.molecule_id, v.readout_definition_id): v for v in values}
        assert by_key[(mol_a, rd_1)].value == pytest.approx(3.0)
        assert by_key[(mol_a, rd_2)].value == pytest.approx(9.0)
        assert by_key[(mol_b, rd_1)].value == pytest.approx(11.0)
        assert by_key[(mol_b, rd_2)].value == pytest.approx(20.0)

    def test_geometric_mean_fails_on_one_bad_group(self) -> None:
        """If any group contains a non-positive value, the whole call fails."""
        aggregator = ReplicateAggregator()
        mol_a = uuid4()
        mol_b = uuid4()
        rd = uuid4()

        readouts = [
            _make_readout_data(mol_a, rd, 4.0),  # good group
            _make_readout_data(mol_a, rd, 16.0),
            _make_readout_data(mol_b, rd, -1.0),  # bad group
            _make_readout_data(mol_b, rd, 8.0),
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.GEOMETRIC_MEAN)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    def test_counts_per_group_are_independent(self) -> None:
        """Each group tracks its own count independently."""
        aggregator = ReplicateAggregator()
        mol_a = uuid4()
        mol_b = uuid4()
        rd = uuid4()

        readouts = [
            _make_readout_data(mol_a, rd, 10.0),
            _make_readout_data(mol_a, rd, 20.0),
            _make_readout_data(mol_a, rd, 30.0),  # count=3
            _make_readout_data(mol_b, rd, 5.0),   # count=1
        ]

        result = aggregator.aggregate(readouts, ReadoutAggregation.MEAN)

        assert isinstance(result, Success)
        values = result.unwrap()
        by_mol = {v.molecule_id: v for v in values}

        assert by_mol[mol_a].count == 3
        assert by_mol[mol_a].stdev is not None

        assert by_mol[mol_b].count == 1
        assert by_mol[mol_b].stdev is None
