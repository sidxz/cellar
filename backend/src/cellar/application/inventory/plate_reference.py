"""Resolve a barcode-or-label reference to an inventory plate (S15 spec §5.1).

Barcode chain first (``resolve_barcode``: exact → zero-pad-to-6 → strip
leading zeros), then an exact ``plate_label`` match accepted only when
exactly one plate carries that label. Shared by run-file import auto-link
and the manual run-plate link so both agree on what a reference means.
"""

from __future__ import annotations

import uuid

from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import RegisteredPlateRepository


async def resolve_plate_reference(
    repo: RegisteredPlateRepository, workspace_id: uuid.UUID, raw: str
) -> RegisteredPlate | None:
    plate = await resolve_barcode(repo, workspace_id, raw)
    if plate is not None:
        return plate
    label = raw.strip()
    if not label:
        return None
    by_label = await repo.find_by_label(workspace_id, label)
    return by_label[0] if len(by_label) == 1 else None
