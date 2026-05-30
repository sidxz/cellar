"""WellAssignment value object — what occupies a single well on a RegisteredPlate.

Harmonizes the inventory well representation with the screening side: every well
carries a structured role (the shared :class:`WellType`) plus an optional batch
reference and concentration (the shared :class:`Concentration` VO).

Serializes to a flat primitive dict for JSONB storage in
``RegisteredPlate.well_map`` — keeping the same ``batch_id`` /
``concentration_value`` / ``concentration_unit`` keys the molecule→plates read
model already reads, with ``well_type`` added.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from cellar.domain.shared.enums import ConcentrationUnit, WellType
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import Concentration


class WellAssignment(BaseModel):
    """What occupies a single well on a registered plate.

    Immutable value object, equality by value. Stored inside the plate's
    ``well_map`` JSONB keyed by position string (e.g. ``"A1"``).
    """

    model_config = ConfigDict(frozen=True)

    well_type: WellType = WellType.SAMPLE
    batch_id: uuid.UUID | None = None
    concentration: Concentration | None = None
    # Passthrough for CDD imports where the source batch could not be resolved
    # to an internal batch — preserved so re-sync / audit keep the reference.
    cdd_batch_id_unresolved: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WellAssignment:
        """Build from a flat primitive dict (API input or a JSONB row).

        Raises :class:`ValidationError` on a malformed unit / role / batch id.
        """
        raw_batch = data.get("batch_id")
        if raw_batch:
            try:
                batch_id: uuid.UUID | None = uuid.UUID(str(raw_batch))
            except ValueError as exc:
                raise ValidationError(
                    f"Invalid batch_id '{raw_batch}' (expected a resolved UUID)"
                ) from exc
        else:
            batch_id = None

        conc_value = data.get("concentration_value")
        conc_unit = data.get("concentration_unit")
        # A non-positive value means "no concentration" — Concentration requires > 0.
        if conc_value is not None and conc_value > 0 and conc_unit is not None:
            try:
                concentration: Concentration | None = Concentration(
                    value=conc_value, unit=ConcentrationUnit(conc_unit)
                )
            except ValueError as exc:
                raise ValidationError(f"Invalid concentration unit '{conc_unit}'") from exc
        else:
            concentration = None

        raw_type = data.get("well_type")
        if raw_type:
            try:
                well_type = WellType(raw_type)
            except ValueError as exc:
                raise ValidationError(f"Invalid well_type '{raw_type}'") from exc
        else:
            well_type = WellType.SAMPLE

        return cls(
            well_type=well_type,
            batch_id=batch_id,
            concentration=concentration,
            cdd_batch_id_unresolved=data.get("cdd_batch_id_unresolved"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Render to a flat primitive dict for JSONB storage.

        Preserves the flat ``batch_id`` / ``concentration_value`` /
        ``concentration_unit`` keys the read-model SQL relies on, adding
        ``well_type``.
        """
        out: dict[str, Any] = {
            "batch_id": str(self.batch_id) if self.batch_id else None,
            "concentration_value": self.concentration.value if self.concentration else None,
            "concentration_unit": self.concentration.unit.value if self.concentration else None,
            "well_type": self.well_type.value,
        }
        if self.cdd_batch_id_unresolved is not None:
            out["cdd_batch_id_unresolved"] = self.cdd_batch_id_unresolved
        return out
