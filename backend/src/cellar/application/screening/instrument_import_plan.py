"""Planning helpers shared by the instrument file preview and import.

Pure functions over an ``InstrumentExport`` plus the one refusal both requests
apply before reading the file.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from cellar.application.screening.instrument_export import InstrumentExport
from cellar.application.screening.run_shape import refuse_if_wellless
from cellar.domain.screening_assay.enums import ReadoutDataType, RunStatus
from cellar.domain.screening_assay.holder import position_label, row_letters
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.repository import ReadoutDataRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.shared.units import canonical_unit

_BRACKETED_SUFFIX = re.compile(r"(.*?)\s*\([^()]*\)")


@dataclass(frozen=True)
class ReportedSeries:
    """One distinct (channel, kind, ordinal) the file reports values for."""

    channel: str
    kind: str
    ordinal: int
    label: str
    unit: str
    count: int

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.channel, self.kind, self.ordinal)


def reported_series(export: InstrumentExport) -> tuple[list[ReportedSeries], list[str]]:
    """Group reported values into series, in order of first appearance.

    Values naming a channel the export does not declare are skipped, with one
    warning per (channel, label).
    """
    declared = {c.key for c in export.channels}
    series: dict[tuple[str, str, int], ReportedSeries] = {}
    warnings: dict[tuple[str, str], str] = {}
    for v in export.reported:
        if v.channel not in declared:
            warnings.setdefault(
                (v.channel, v.label),
                f"Reported value '{v.label}' belongs to a signal the file has no traces for. "
                "It is skipped.",
            )
            continue
        key = (v.channel, v.kind, v.ordinal)
        found = series.get(key)
        series[key] = (
            replace(found, count=found.count + 1)
            if found
            else ReportedSeries(v.channel, v.kind, v.ordinal, v.label, v.unit, 1)
        )
    return list(series.values()), list(warnings.values())


def missing_curve_warnings(export: InstrumentExport, keys: Iterable[tuple[int, int]]) -> list[str]:
    """One warning per (row, column) position and declared channel the file has no curve for."""
    have = {(c.row, c.column, c.channel) for c in export.curves}
    return [
        f"{position_label(export.holder.kind, row_letters(row), column)} has no "
        f"{channel.label} trace in the file. Mapped reported values can still be imported."
        for row, column in keys
        for channel in export.channels
        if (row, column, channel.key) not in have
    ]


def readout_mapping_error(
    series: ReportedSeries, definition: ReadoutDefinition | None
) -> ValidationError | None:
    """Why ``series`` cannot be written into ``definition``, or None when it can."""
    if definition is None:
        return ValidationError(
            f"The readout chosen for '{series.label}' is not on the run's protocol"
        )
    if definition.data_type != ReadoutDataType.NUMERIC:
        return ValidationError(f"Readout '{definition.name}' is not numeric")
    if definition.is_calculated:
        return ValidationError(
            f"Readout '{definition.name}' is calculated; values cannot be imported into it"
        )
    series_unit = canonical_unit(series.unit)
    if definition.unit != series_unit:
        return ValidationError(
            f"Readout '{definition.name}' is in '{definition.unit or 'no unit'}' "
            f"but '{series.label}' is in '{series_unit or 'no unit'}'"
        )
    return None


def suggest_readout(
    series: ReportedSeries, definitions: Sequence[ReadoutDefinition]
) -> uuid.UUID | None:
    """The readout named like the series (ignoring case) that can take its values."""
    name = series.label.strip().casefold()
    return next(
        (
            d.id
            for d in definitions
            if d.name.casefold() == name and readout_mapping_error(series, d) is None
        ),
        None,
    )


def label_lookup_candidates(label: str) -> list[str]:
    """Identifiers to try for a position label: the label, then the part before a "(...)"."""
    text = label.strip()
    if not text:
        return []
    match = _BRACKETED_SUFFIX.fullmatch(text)
    if match and match.group(1):
        return [text, match.group(1)]
    return [text]


async def refuse_instrument_import(
    run: Run, readout_repo: ReadoutDataRepository
) -> ConflictError | None:
    """Why ``run`` cannot take an instrument file, or None when it can."""
    if run.is_locked:
        return ConflictError("Cannot import into a locked run")
    if run.status not in (RunStatus.DRAFT, RunStatus.IN_PROGRESS):
        return ConflictError(
            f"Cannot import into a run in status '{run.status.value}'. "
            "Only draft or in-progress runs accept an instrument file."
        )
    if (wellless := await refuse_if_wellless(readout_repo, run.workspace_id, run.id)) is not None:
        return wellless
    if run.plates:
        return ConflictError(
            "This run already has a holder. Reset the run's data first, then import again."
        )
    return None
