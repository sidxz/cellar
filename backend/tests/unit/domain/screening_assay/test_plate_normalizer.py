"""Tests for PlateNormalizer domain service."""

from __future__ import annotations

import uuid

import pytest

from chem_vault.domain.screening_assay.enums import ReadoutNormalization, WellType
from chem_vault.domain.screening_assay.plate_normalizer import NormalizedValue, PlateNormalizer
from chem_vault.domain.screening_assay.run import Well
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_well(well_type: WellType, row: str, column: int, **kwargs) -> Well:
    return Well(
        plate_id=uuid.uuid4(),
        row=row,
        column=column,
        well_type=well_type,
        **kwargs,
    )


def _sample(row: str = "A", col: int = 1, **kwargs) -> Well:
    return _make_well(WellType.SAMPLE, row, col, **kwargs)


def _neg_ctrl(row: str = "B", col: int = 1, **kwargs) -> Well:
    return _make_well(WellType.NEGATIVE_CONTROL, row, col, **kwargs)


def _pos_ctrl(row: str = "C", col: int = 1, **kwargs) -> Well:
    return _make_well(WellType.POSITIVE_CONTROL, row, col, **kwargs)


def _blank(row: str = "D", col: int = 1, **kwargs) -> Well:
    return _make_well(WellType.BLANK, row, col, **kwargs)


# ---------------------------------------------------------------------------
# TestNoneNormalization
# ---------------------------------------------------------------------------


class TestNoneNormalization:
    def test_returns_empty_list(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample()
        n = _neg_ctrl()
        raw = {s.id: 50.0, n.id: 100.0}

        result = normalizer.normalize([s, n], raw, ReadoutNormalization.NONE)

        assert result == []

    def test_returns_empty_list_with_no_wells(self) -> None:
        normalizer = PlateNormalizer()
        result = normalizer.normalize([], {}, ReadoutNormalization.NONE)

        assert result == []


# ---------------------------------------------------------------------------
# TestPercentInhibition
# ---------------------------------------------------------------------------


class TestPercentInhibition:
    """100 * (pos_ctrl_mean - sample) / (pos_ctrl_mean - neg_ctrl_mean).

    Convention (consistent with PERCENT_ACTIVATION): POS anchors max signal
    (0% inhibition), NEG anchors min signal (100% inhibition).
    """

    def test_basic_calculation(self) -> None:
        """POS=100 (uninhibited), NEG=0 (inhibited), sample=50 → 50% inhibition."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

        assert len(values) == 1
        # 100 * (100 - 50) / (100 - 0) = 50.0
        assert values[0].normalized_value == pytest.approx(50.0)
        assert values[0].original_value == 50.0

    def test_realistic_nadd_setup(self) -> None:
        """NadD-Sumo: POS=0.652 (DMSO/uninhibited), NEG=0.067 (reference inhibitor)."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 0.3595, n.id: 0.067, p.id: 0.652}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

        # 100 * (0.652 - 0.3595) / (0.652 - 0.067) = 100 * 0.2925/0.585 = 50.0
        assert values[0].normalized_value == pytest.approx(50.0)

    def test_zero_inhibition_at_pos_control(self) -> None:
        """Sample == POS control (max signal/uninhibited) → 0% inhibition."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 100.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

        assert values[0].normalized_value == pytest.approx(0.0)

    def test_full_inhibition_at_neg_control(self) -> None:
        """Sample == NEG control (min signal/inhibited) → 100% inhibition."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 0.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

        assert values[0].normalized_value == pytest.approx(100.0)

    def test_multiple_controls_averaged(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n1 = _neg_ctrl("B", 1)
        n2 = _neg_ctrl("B", 2)
        p1 = _pos_ctrl("C", 1)
        p2 = _pos_ctrl("C", 2)
        # pos_mean = 100, neg_mean = 0, sample = 40 → 100*(100-40)/(100-0) = 60
        raw = {s.id: 40.0, n1.id: -10.0, n2.id: 10.0, p1.id: 80.0, p2.id: 120.0}

        values = normalizer.normalize(
            [s, n1, n2, p1, p2], raw, ReadoutNormalization.PERCENT_INHIBITION
        )

        assert len(values) == 1
        assert values[0].normalized_value == pytest.approx(60.0)

    def test_multiple_samples(self) -> None:
        normalizer = PlateNormalizer()
        s1 = _sample("A", 1)
        s2 = _sample("A", 2)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        # POS=100, NEG=0
        raw = {s1.id: 25.0, s2.id: 75.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize(
            [s1, s2, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION
        )

        assert len(values) == 2
        normalized = {v.well_id: v.normalized_value for v in values}
        # 100 * (100-25)/100 = 75; 100 * (100-75)/100 = 25
        assert normalized[s1.id] == pytest.approx(75.0)
        assert normalized[s2.id] == pytest.approx(25.0)

    def test_missing_neg_ctrl_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, p.id: 0.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

    def test_missing_pos_ctrl_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        raw = {s.id: 50.0, n.id: 100.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, n], raw, ReadoutNormalization.PERCENT_INHIBITION)

    def test_neg_ctrl_not_in_raw_values_raises(self) -> None:
        """Well exists but has no raw value entry."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, p.id: 0.0}  # n.id intentionally absent

        with pytest.raises(ValidationError):
            normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

    def test_zero_denominator_raises(self) -> None:
        """neg_ctrl_mean == pos_ctrl_mean → division by zero."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, n.id: 100.0, p.id: 100.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

    def test_batch_id_propagated(self) -> None:
        normalizer = PlateNormalizer()
        batch_id = uuid.uuid4()
        s = _sample("A", 1, batch_id=batch_id)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, n.id: 100.0, p.id: 0.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

        assert values[0].batch_id == batch_id

    def test_control_wells_excluded_from_output(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, n.id: 100.0, p.id: 0.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_INHIBITION)

        well_ids = {v.well_id for v in values}
        assert n.id not in well_ids
        assert p.id not in well_ids

    def test_pos_low_convention_swaps_anchors(self) -> None:
        """LOW convention: lab labels known-inhibitor wells as POS (low signal),
        DMSO wells as NEG (high signal). The formula must swap anchors so a
        sample matching the DMSO control still reads as 0% inhibition."""
        from chem_vault.domain.screening_assay.enums import PosControlSignal

        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        # POS = inhibitor (low raw signal), NEG = DMSO (high raw signal)
        p = _pos_ctrl("B", 1)
        n = _neg_ctrl("C", 1)
        raw = {s.id: 100.0, p.id: 0.0, n.id: 100.0}  # sample at DMSO level

        values = normalizer.normalize(
            [s, p, n], raw, ReadoutNormalization.PERCENT_INHIBITION,
            PosControlSignal.LOW,
        )
        # Sample == high-anchor (NEG under LOW convention) → 0% inhibition
        assert values[0].normalized_value == pytest.approx(0.0)

        # Sample at the inhibitor level → 100% inhibition
        raw2 = {s.id: 0.0, p.id: 0.0, n.id: 100.0}
        values2 = normalizer.normalize(
            [s, p, n], raw2, ReadoutNormalization.PERCENT_INHIBITION,
            PosControlSignal.LOW,
        )
        assert values2[0].normalized_value == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# TestPercentActivation
# ---------------------------------------------------------------------------


class TestPercentActivation:
    """100 * ((sample - neg_ctrl_mean) / (pos_ctrl_mean - neg_ctrl_mean))."""

    def test_basic_calculation(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        # neg=0, pos=100, sample=50 → 100 * (50-0)/(100-0) = 50.0
        raw = {s.id: 50.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_ACTIVATION)

        assert len(values) == 1
        assert values[0].normalized_value == pytest.approx(50.0)

    def test_fully_activated(self) -> None:
        """Sample == pos_ctrl → 100% activation."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 100.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_ACTIVATION)

        assert values[0].normalized_value == pytest.approx(100.0)

    def test_no_activation(self) -> None:
        """Sample == neg_ctrl → 0% activation."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 0.0, n.id: 0.0, p.id: 100.0}

        values = normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_ACTIVATION)

        assert values[0].normalized_value == pytest.approx(0.0)

    def test_multiple_controls_averaged(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n1 = _neg_ctrl("B", 1)
        n2 = _neg_ctrl("B", 2)
        p1 = _pos_ctrl("C", 1)
        p2 = _pos_ctrl("C", 2)
        # neg_mean = (0 + 20) / 2 = 10, pos_mean = (80 + 120) / 2 = 100
        # 100 * (50 - 10) / (100 - 10) = 100 * 40/90 ≈ 44.444
        raw = {s.id: 50.0, n1.id: 0.0, n2.id: 20.0, p1.id: 80.0, p2.id: 120.0}

        values = normalizer.normalize(
            [s, n1, n2, p1, p2], raw, ReadoutNormalization.PERCENT_ACTIVATION
        )

        assert len(values) == 1
        assert values[0].normalized_value == pytest.approx(100.0 * 40.0 / 90.0)

    def test_missing_neg_ctrl_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, p.id: 100.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_ACTIVATION)

    def test_missing_pos_ctrl_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        raw = {s.id: 50.0, n.id: 0.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, n], raw, ReadoutNormalization.PERCENT_ACTIVATION)

    def test_zero_denominator_raises(self) -> None:
        """pos_ctrl_mean == neg_ctrl_mean → division by zero."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        raw = {s.id: 50.0, n.id: 100.0, p.id: 100.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, n, p], raw, ReadoutNormalization.PERCENT_ACTIVATION)

    def test_pos_low_convention_swaps_anchors(self) -> None:
        from chem_vault.domain.screening_assay.enums import PosControlSignal

        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        # LOW: NEG=DMSO (high signal=baseline), POS=activator hit (low signal=ceiling)
        n = _neg_ctrl("B", 1)
        p = _pos_ctrl("C", 1)
        # neg=100 (high anchor), pos=0 (low anchor), sample=50 → 50% activation
        raw = {s.id: 50.0, n.id: 100.0, p.id: 0.0}

        values = normalizer.normalize(
            [s, n, p], raw, ReadoutNormalization.PERCENT_ACTIVATION,
            PosControlSignal.LOW,
        )
        assert values[0].normalized_value == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# TestPercentControl
# ---------------------------------------------------------------------------


class TestPercentControl:
    """100 * (sample / high_anchor_mean).

    Baseline is the high-signal anchor (uninhibited / DMSO reference).
    Under the default ``pos_control_signal=HIGH`` convention that's the
    POSITIVE_CONTROL wells.
    """

    def test_basic_calculation(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        # 100 * 60 / 100 = 60.0
        raw = {s.id: 60.0, p.id: 100.0}

        values = normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert len(values) == 1
        assert values[0].normalized_value == pytest.approx(60.0)

    def test_equal_to_control(self) -> None:
        """Sample == high-anchor → 100% of control."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        raw = {s.id: 100.0, p.id: 100.0}

        values = normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert values[0].normalized_value == pytest.approx(100.0)

    def test_multiple_pos_ctrls_averaged(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        # high_mean = (80 + 120) / 2 = 100
        # 100 * 50 / 100 = 50.0
        raw = {s.id: 50.0, p1.id: 80.0, p2.id: 120.0}

        values = normalizer.normalize([s, p1, p2], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert values[0].normalized_value == pytest.approx(50.0)

    def test_missing_high_anchor_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        raw = {s.id: 50.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s], raw, ReadoutNormalization.PERCENT_CONTROL)

    def test_zero_high_anchor_mean_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        raw = {s.id: 50.0, p.id: 0.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_CONTROL)

    def test_multiple_samples(self) -> None:
        normalizer = PlateNormalizer()
        s1 = _sample("A", 1)
        s2 = _sample("A", 2)
        p = _pos_ctrl("B", 1)
        raw = {s1.id: 25.0, s2.id: 75.0, p.id: 100.0}

        values = normalizer.normalize([s1, s2, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert len(values) == 2
        normalized = {v.well_id: v.normalized_value for v in values}
        assert normalized[s1.id] == pytest.approx(25.0)
        assert normalized[s2.id] == pytest.approx(75.0)

    def test_pos_low_convention_swaps_baseline(self) -> None:
        """When pos_control_signal=LOW, the lab labels DMSO as NEG. The
        baseline therefore comes from NEG_CONTROL wells, not POS."""
        from chem_vault.domain.screening_assay.enums import PosControlSignal

        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        # In LOW convention: NEG = DMSO/uninhibited (high signal = baseline);
        # POS = known inhibitor (low signal, irrelevant for % Control).
        n = _neg_ctrl("B", 1)
        raw = {s.id: 60.0, n.id: 100.0}

        values = normalizer.normalize(
            [s, n], raw, ReadoutNormalization.PERCENT_CONTROL,
            PosControlSignal.LOW,
        )
        assert values[0].normalized_value == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# TestZScore
# ---------------------------------------------------------------------------


class TestZScore:
    """(sample - high_anchor_mean) / high_anchor_stdev.

    Baseline distribution comes from the high-signal anchor — same convention
    as PERCENT_CONTROL.
    """

    def test_basic_calculation(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        # high = [90, 110] → mean=100, stdev=~14.142, z = (150-100)/14.142 ≈ 3.535
        import statistics

        raw = {s.id: 150.0, p1.id: 90.0, p2.id: 110.0}
        expected_mean = statistics.mean([90.0, 110.0])
        expected_stdev = statistics.stdev([90.0, 110.0])
        expected_z = (150.0 - expected_mean) / expected_stdev

        values = normalizer.normalize([s, p1, p2], raw, ReadoutNormalization.Z_SCORE)

        assert len(values) == 1
        assert values[0].normalized_value == pytest.approx(expected_z)

    def test_at_mean_gives_zero_z(self) -> None:
        """Sample at the high-anchor mean → Z = 0."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        raw = {s.id: 100.0, p1.id: 90.0, p2.id: 110.0}

        values = normalizer.normalize([s, p1, p2], raw, ReadoutNormalization.Z_SCORE)

        assert values[0].normalized_value == pytest.approx(0.0)

    def test_negative_z_score(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        import statistics

        raw = {s.id: 50.0, p1.id: 90.0, p2.id: 110.0}
        expected = (50.0 - statistics.mean([90.0, 110.0])) / statistics.stdev([90.0, 110.0])

        values = normalizer.normalize([s, p1, p2], raw, ReadoutNormalization.Z_SCORE)

        assert values[0].normalized_value == pytest.approx(expected)

    def test_only_one_high_anchor_raises(self) -> None:
        """stdev requires n >= 2 — single control must fail."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        raw = {s.id: 50.0, p.id: 100.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, p], raw, ReadoutNormalization.Z_SCORE)

    def test_no_high_anchor_raises(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        raw = {s.id: 50.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s], raw, ReadoutNormalization.Z_SCORE)

    def test_zero_stdev_raises(self) -> None:
        """All high-anchor values identical → stdev == 0."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        raw = {s.id: 50.0, p1.id: 100.0, p2.id: 100.0}

        with pytest.raises(ValidationError):
            normalizer.normalize([s, p1, p2], raw, ReadoutNormalization.Z_SCORE)

    def test_multiple_high_anchors(self) -> None:
        """Three high-anchor wells — correct mean and stdev used."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        p3 = _pos_ctrl("B", 3)
        import statistics

        vals = [80.0, 100.0, 120.0]
        raw = {s.id: 110.0, p1.id: vals[0], p2.id: vals[1], p3.id: vals[2]}
        expected = (110.0 - statistics.mean(vals)) / statistics.stdev(vals)

        values = normalizer.normalize([s, p1, p2, p3], raw, ReadoutNormalization.Z_SCORE)

        assert values[0].normalized_value == pytest.approx(expected)

    def test_pos_low_convention_uses_neg_anchor(self) -> None:
        """Under LOW convention NEG_CONTROL holds the high signal, so it
        becomes the baseline distribution."""
        from chem_vault.domain.screening_assay.enums import PosControlSignal
        import statistics

        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        n1 = _neg_ctrl("B", 1)
        n2 = _neg_ctrl("B", 2)
        raw = {s.id: 150.0, n1.id: 90.0, n2.id: 110.0}
        expected = (150.0 - statistics.mean([90.0, 110.0])) / statistics.stdev([90.0, 110.0])

        values = normalizer.normalize(
            [s, n1, n2], raw, ReadoutNormalization.Z_SCORE,
            PosControlSignal.LOW,
        )
        assert values[0].normalized_value == pytest.approx(expected)

    def test_control_wells_not_in_output(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        raw = {s.id: 50.0, p1.id: 90.0, p2.id: 110.0}

        values = normalizer.normalize([s, p1, p2], raw, ReadoutNormalization.Z_SCORE)

        well_ids = {v.well_id for v in values}
        assert p1.id not in well_ids
        assert p2.id not in well_ids


# ---------------------------------------------------------------------------
# Cross-cutting: NormalizedValue fields
# ---------------------------------------------------------------------------


class TestNormalizedValueFields:
    def test_well_id_is_set(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        raw = {s.id: 50.0, p.id: 100.0}

        values = normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert values[0].well_id == s.id

    def test_original_value_preserved(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        raw = {s.id: 42.5, p.id: 100.0}

        values = normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert values[0].original_value == 42.5

    def test_molecule_id_is_none(self) -> None:
        """molecule_id is always None — PlateNormalizer does not resolve molecules."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        raw = {s.id: 50.0, p.id: 100.0}

        values = normalizer.normalize([s, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert values[0].molecule_id is None

    def test_sample_with_no_raw_value_excluded(self) -> None:
        """Sample wells without a raw value entry are silently skipped."""
        normalizer = PlateNormalizer()
        s1 = _sample("A", 1)
        s2 = _sample("A", 2)
        p = _pos_ctrl("B", 1)
        raw = {s1.id: 50.0, p.id: 100.0}  # s2 has no raw value

        values = normalizer.normalize([s1, s2, p], raw, ReadoutNormalization.PERCENT_CONTROL)

        assert len(values) == 1
        assert values[0].well_id == s1.id


# ---------------------------------------------------------------------------
# TestNormalizeMany — multi-emit normalization fan-out
# ---------------------------------------------------------------------------


class TestNormalizeMany:
    def test_emits_one_result_set_per_formula(self) -> None:
        """Readout def with {%inh, z_score} computes both views off the same plate."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        # Z-score requires >= 2 high-signal control wells with non-zero stdev.
        p1 = _pos_ctrl("B", 1)
        p2 = _pos_ctrl("B", 2)
        n = _neg_ctrl("C", 1)
        raw = {s.id: 50.0, p1.id: 100.0, p2.id: 90.0, n.id: 0.0}

        result = normalizer.normalize_many(
            [s, p1, p2, n],
            raw,
            frozenset(
                {
                    ReadoutNormalization.PERCENT_INHIBITION,
                    ReadoutNormalization.Z_SCORE,
                }
            ),
        )

        assert set(result.keys()) == {
            ReadoutNormalization.PERCENT_INHIBITION,
            ReadoutNormalization.Z_SCORE,
        }
        assert len(result[ReadoutNormalization.PERCENT_INHIBITION]) == 1
        assert len(result[ReadoutNormalization.Z_SCORE]) == 1

    def test_empty_set_returns_empty_dict(self) -> None:
        normalizer = PlateNormalizer()
        s = _sample()
        result = normalizer.normalize_many([s], {s.id: 1.0}, frozenset())
        assert result == {}

    def test_each_formula_independent_of_others(self) -> None:
        """Same input, single-formula and multi-formula calls give identical output."""
        normalizer = PlateNormalizer()
        s = _sample("A", 1)
        p = _pos_ctrl("B", 1)
        n = _neg_ctrl("C", 1)
        raw = {s.id: 50.0, p.id: 100.0, n.id: 0.0}

        single = normalizer.normalize(
            [s, p, n], raw, ReadoutNormalization.PERCENT_INHIBITION
        )
        many = normalizer.normalize_many(
            [s, p, n], raw, frozenset({ReadoutNormalization.PERCENT_INHIBITION})
        )

        assert many[ReadoutNormalization.PERCENT_INHIBITION] == single
