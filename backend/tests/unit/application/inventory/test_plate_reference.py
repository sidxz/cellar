"""Unit tests for resolve_plate_reference — barcode chain, then unique label (S15 §5.1)."""

from __future__ import annotations

import uuid

import pytest

from cellar.application.inventory.plate_reference import resolve_plate_reference
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_registered_plate_repository import FakeRegisteredPlateRepository

WORKSPACE_ID = uuid.uuid4()


def _make_plate(
    barcode: str, label: str, workspace_id: uuid.UUID = WORKSPACE_ID
) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=workspace_id,
        barcode=Barcode(value=barcode),
        plate_label=label,
        format=PlateFormat.F96,
        plate_type=PlateType.COMPOUND_STORAGE,
        registered_by=uuid.uuid4(),
    )


class TestResolvePlateReference:
    async def test_exact_barcode_wins_over_label(self) -> None:
        by_barcode = _make_plate("SAC3-014-3070", "Other")
        by_label = _make_plate("000001", "SAC3-014-3070")
        repo = FakeRegisteredPlateRepository([by_label, by_barcode])

        out = await resolve_plate_reference(repo, WORKSPACE_ID, "SAC3-014-3070")

        assert out is by_barcode

    async def test_short_numeric_resolves_zero_padded_barcode(self) -> None:
        plate = _make_plate("000123", "Padded")
        repo = FakeRegisteredPlateRepository([plate])

        out = await resolve_plate_reference(repo, WORKSPACE_ID, "123")

        assert out is plate

    async def test_unique_label_resolves_after_barcode_miss(self) -> None:
        plate = _make_plate("000042", "SAC3-014-3070")
        repo = FakeRegisteredPlateRepository([plate, _make_plate("000043", "Unrelated")])

        out = await resolve_plate_reference(repo, WORKSPACE_ID, "  SAC3-014-3070 ")

        assert out is plate

    async def test_ambiguous_label_resolves_to_none(self) -> None:
        repo = FakeRegisteredPlateRepository(
            [_make_plate("000001", "Dup"), _make_plate("000002", "Dup")]
        )

        assert await resolve_plate_reference(repo, WORKSPACE_ID, "Dup") is None

    async def test_label_lookup_is_workspace_scoped(self) -> None:
        mine = _make_plate("000001", "Shared")
        repo = FakeRegisteredPlateRepository(
            [mine, _make_plate("000002", "Shared", workspace_id=uuid.uuid4())]
        )

        assert await resolve_plate_reference(repo, WORKSPACE_ID, "Shared") is mine

    async def test_unknown_reference_resolves_to_none(self) -> None:
        repo = FakeRegisteredPlateRepository([_make_plate("000001", "Known")])

        assert await resolve_plate_reference(repo, WORKSPACE_ID, "NOPE") is None

    @pytest.mark.parametrize("raw", ["", "   "])
    async def test_blank_resolves_to_none(self, raw: str) -> None:
        repo = FakeRegisteredPlateRepository([_make_plate("000001", "Known")])

        assert await resolve_plate_reference(repo, WORKSPACE_ID, raw) is None
