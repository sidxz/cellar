"""Barcode scan/paste resolution — spec §7 fallback chain.

Exact match first; only when that misses: all-digits inputs shorter than 6
are left-padded with '0' to width 6 (legacy str_pad convention), then a
strip-leading-zeros variant. First hit wins (barcodes are workspace-unique,
so the chain is deterministic). Shared by loan requests now, kiosk scan in S5.
"""

from __future__ import annotations

import uuid

from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import RegisteredPlateRepository


def barcode_candidates(raw: str) -> list[str]:
    cleaned = raw.strip()
    if not cleaned:
        return []
    candidates = [cleaned]
    if cleaned.isdigit() and len(cleaned) < 6:
        candidates.append(cleaned.zfill(6))
    stripped = cleaned.lstrip("0")
    if stripped and stripped != cleaned:
        candidates.append(stripped)
    return candidates


async def resolve_barcode(
    repo: RegisteredPlateRepository, workspace_id: uuid.UUID, raw: str
) -> RegisteredPlate | None:
    for candidate in barcode_candidates(raw):
        plate = await repo.find_by_barcode(workspace_id, candidate)
        if plate is not None:
            return plate
    return None
