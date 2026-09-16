"""Unit tests for barcode scan/paste resolution (spec §7)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from cellar.application.inventory.barcode_resolution import (
    barcode_candidates,
    resolve_barcode,
)
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode

WORKSPACE_ID = uuid.uuid4()


def _make_plate(barcode: str) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=WORKSPACE_ID,
        barcode=Barcode(value=barcode),
        plate_label="Test Plate",
        format=PlateFormat.F96,
        plate_type=PlateType.COMPOUND_STORAGE,
        registered_by=uuid.uuid4(),
    )


class TestBarcodeCandidates:
    def test_short_numeric_pads_to_six(self) -> None:
        assert barcode_candidates("5261") == ["5261", "005261"]

    def test_six_digit_offers_stripped_variant(self) -> None:
        assert barcode_candidates("005261") == ["005261", "5261"]

    def test_non_numeric_is_exact_only(self) -> None:
        assert barcode_candidates("BC-01") == ["BC-01"]

    def test_strips_whitespace(self) -> None:
        assert barcode_candidates("  005261 ") == ["005261", "5261"]

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_input_yields_no_candidates(self, raw: str) -> None:
        assert barcode_candidates(raw) == []

    def test_single_zero_excludes_empty_stripped_variant(self) -> None:
        # lstrip("0") on "0" is "" — falsy, so it must NOT appear as a
        # third candidate (an empty-string barcode lookup is meaningless).
        assert barcode_candidates("0") == ["0", "000000"]


@pytest.mark.asyncio
class TestResolveBarcode:
    async def test_exact_match_wins_without_fallback(self) -> None:
        plate = _make_plate("5261")
        repo = AsyncMock()
        repo.find_by_barcode = AsyncMock(return_value=plate)

        out = await resolve_barcode(repo, WORKSPACE_ID, "5261")

        assert out is plate
        repo.find_by_barcode.assert_awaited_once_with(WORKSPACE_ID, "5261")

    async def test_falls_back_to_padded_candidate_in_order(self) -> None:
        plate = _make_plate("005261")

        async def _find(_ws: uuid.UUID, barcode: str) -> RegisteredPlate | None:
            return plate if barcode == "005261" else None

        repo = AsyncMock()
        repo.find_by_barcode = AsyncMock(side_effect=_find)

        out = await resolve_barcode(repo, WORKSPACE_ID, "5261")

        assert out is plate
        # Proves first-hit-wins order: exact "5261" tried (and missed)
        # before the padded "005261" fallback.
        tried = [call.args[1] for call in repo.find_by_barcode.await_args_list]
        assert tried == ["5261", "005261"]

    async def test_no_candidate_matches_returns_none(self) -> None:
        repo = AsyncMock()
        repo.find_by_barcode = AsyncMock(return_value=None)

        out = await resolve_barcode(repo, WORKSPACE_ID, "BC-999")

        assert out is None
        repo.find_by_barcode.assert_awaited_once_with(WORKSPACE_ID, "BC-999")
