"""In-memory RegisteredPlateRepository for unit tests."""

from __future__ import annotations

import uuid

from cellar.domain.inventory.registered_plate import RegisteredPlate


class FakeRegisteredPlateRepository:
    """Dict-backed ``RegisteredPlateRepository`` — only the lookups unit tests need."""

    def __init__(self, plates: list[RegisteredPlate] | None = None) -> None:
        self._plates: dict[uuid.UUID, RegisteredPlate] = {p.id: p for p in plates or []}

    def _in_workspace(self, workspace_id: uuid.UUID) -> list[RegisteredPlate]:
        return [p for p in self._plates.values() if p.workspace_id == workspace_id]

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> RegisteredPlate | None:
        plate = self._plates.get(id)
        return plate if plate is not None and plate.workspace_id == workspace_id else None

    async def find_by_barcode(
        self, workspace_id: uuid.UUID, barcode: str
    ) -> RegisteredPlate | None:
        return next(
            (p for p in self._in_workspace(workspace_id) if p.barcode.value == barcode), None
        )

    async def find_by_label(self, workspace_id: uuid.UUID, label: str) -> list[RegisteredPlate]:
        return [p for p in self._in_workspace(workspace_id) if p.plate_label == label]

    async def save(self, aggregate: RegisteredPlate) -> None:
        self._plates[aggregate.id] = aggregate
