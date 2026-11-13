"""Guard: one run, one shape.

A run is either **welled** — it has plates whose wells carry the measurements —
or **well-less**, holding summary rows keyed by compound/batch alone. Mixing the
two inside one run leaves every downstream reader (curve fitting, plate QC,
exports) guessing where a value came from, so each import path refuses the shape
it is not.

Computed rows never count towards "well-less": the calculation engine writes
calculated readouts well-less on welled runs by design.
"""

from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.repository import ReadoutDataRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError


def refuse_if_welled(run: Run) -> ConflictError | None:
    """Summary (well-less) import onto a run that already has plates/wells."""
    if run.wells:
        return ConflictError(
            f"Run {run.id} has {len(run.plates)} plate(s) with wells; "
            "well-less summary results cannot be imported onto it"
        )
    return None


async def refuse_if_wellless(
    repo: ReadoutDataRepository,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
) -> ConflictError | None:
    """Plate paths onto a run that already holds well-less summary rows."""
    if await repo.has_wellless_rows(workspace_id, run_id):
        return ConflictError(
            f"Run {run_id} holds well-less summary results; "
            "plate setup and plate import cannot be applied to it"
        )
    return None


def refuse_if_not_plate_holder(run: Run) -> ConflictError | None:
    """Plate-shaped imports onto a run whose holder is not a plate.

    Those paths address positions as plate wells (row letter + column), which
    would put values on the wrong kind of position.
    """
    if any(p.holder_kind is not HolderKind.PLATE for p in run.plates):
        return ConflictError(
            "This run's holder is not a plate, so plate imports are not available for it."
        )
    return None
