"""Tests for compute_formula_weight -- parent MW plus salt MW times stoichiometry."""

from __future__ import annotations

import pytest

from cellar.application.inventory.salt_matcher import compute_formula_weight


class TestComputeFormulaWeight:
    def test_basic_calculation(self) -> None:
        # parent MW 180.16 + HCl 36.46 * 1
        assert compute_formula_weight(180.16, 36.46, 1) == pytest.approx(216.62)

    def test_stoichiometry_2(self) -> None:
        # parent MW 180.16 + HCl 36.46 * 2
        assert compute_formula_weight(180.16, 36.46, 2) == pytest.approx(253.08)

    def test_zero_salt_returns_parent(self) -> None:
        assert compute_formula_weight(180.16, 0.0, 1) == pytest.approx(180.16)
