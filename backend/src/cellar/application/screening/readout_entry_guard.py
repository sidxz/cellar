"""Guard: a calculated readout is derived, never entered by hand.

Shared by the import paths that let a chemist bind a file column to a readout
definition (summary import + plate import). A calculated readout's value comes
from its formula over the other readouts, so accepting an imported value would
silently produce a number the formula disagrees with.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping

from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.shared.errors import ValidationError


def calculated_readout_error(
    mapping_pairs: Iterable[tuple[str, uuid.UUID]],
    defs_by_id: Mapping[uuid.UUID, ReadoutDefinition],
) -> ValidationError | None:
    """Return an error for the first ``(header, readout_definition_id)`` pair
    bound to a calculated readout, else ``None``.

    Ids absent from ``defs_by_id`` are ignored — protocol membership is the
    caller's check, and it emits its own error for it.
    """
    for header, rd_id in mapping_pairs:
        definition = defs_by_id.get(rd_id)
        if definition is not None and definition.is_calculated:
            return ValidationError(
                f"Column '{header}' is mapped to readout '{definition.name}', "
                "which is calculated; calculated values are computed from other "
                "readouts and cannot be imported"
            )
    return None
