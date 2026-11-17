"""Plate geometry: format → dimensions, row labels → index, well reading order."""

from __future__ import annotations

import pytest

from cellar.domain.screening_assay.plate_geometry import plate_dimensions, row_index, well_order


def _frontend_row_label(index: int) -> str:
    """Mirror of ``rowLabel`` in frontend/src/features/screening-assay/lib/plate-dimensions.ts."""
    if index < 26:
        return chr(65 + index)
    return chr(65 + index // 26 - 1) + chr(65 + index % 26)


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("6", (2, 3)),
        ("12", (3, 4)),
        ("24", (4, 6)),
        ("48", (6, 8)),
        ("96", (8, 12)),
        ("384", (16, 24)),
        ("1536", (32, 48)),
    ],
)
def test_plate_dimensions_by_format(fmt: str, expected: tuple[int, int]) -> None:
    assert plate_dimensions(fmt, None, None) == expected


def test_holder_size_wins_over_format() -> None:
    assert plate_dimensions("384", 1, 24) == (1, 24)
    assert plate_dimensions(None, 1, 24) == (1, 24)


def test_unknown_format_without_holder_is_none() -> None:
    assert plate_dimensions("weird", None, None) is None
    assert plate_dimensions(None, None, None) is None


@pytest.mark.parametrize(("label", "expected"), [("A", 0), ("P", 15), ("AA", 26), ("AF", 31)])
def test_row_index(label: str, expected: int) -> None:
    assert row_index(label) == expected


def test_row_index_round_trips_frontend_labels() -> None:
    for i in range(48):
        assert row_index(_frontend_row_label(i)) == i


def test_well_order_is_one_based_row_major() -> None:
    assert well_order("A", 1, 24) == 1
    assert well_order("A", 2, 24) == 2
    assert well_order("B", 1, 24) == 25
    assert well_order("B", 3, 24) == 27
    assert well_order("P", 24, 24) == 384
