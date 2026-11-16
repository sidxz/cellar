"""Control-layout validation helpers for the run-file importer.

Extracted from ``import_run_file.py`` to isolate the protocol /
plate-template / well-type validation rules from the use case
orchestration.

- ``_load_layouts`` — the control layouts a plate's well roles can come
  from, per plate format, highest precedence first: the run's own layout
  (``run.plate_template_id``, when its format matches the plate), then the
  protocol default (``protocol.control_layouts[format]``). The file's role
  column, when mapped, comes before both (decided per row in ``import_plan``).
- ``_validate_controls_required`` — protocol-level gate: any readout
  whose normalization depends on controls (PERCENT_INHIBITION /
  PERCENT_ACTIVATION / PERCENT_CONTROL / Z_SCORE) requires a control
  layout for every plate format used in the file; missing layouts
  become user-visible validation errors.
- ``_validate_well_roles`` — the gate the importer runs: the layout check
  above when roles come from layouts, the role-value check when they come
  from the file's role column.
- ``_role_disagreement_warnings`` / ``_swapped_controls`` — preview-only
  notes: role sources that disagree, and controls whose raw signal reads
  the wrong way round for the protocol's ``pos_control_signal``.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass

from cellar.application.screening.import_plan import _row_role
from cellar.application.screening.long_format_normalizer import (
    NormalizedTable,
    unknown_well_roles_message,
)
from cellar.domain.screening_assay.enums import (
    PosControlSignal,
    ReadoutNormalization,
    WellType,
)
from cellar.domain.screening_assay.plate_quality import PlateQualityCalculator
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.domain.screening_assay.protocol import Protocol as AssayProtocol
from cellar.domain.screening_assay.repository import PlateTemplateRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.enums import PlateFormat

_DESIGNATION_TO_WELL_TYPE: dict[str, WellType] = {
    "compound": WellType.SAMPLE,
    "positive_control": WellType.POSITIVE_CONTROL,
    "negative_control": WellType.NEGATIVE_CONTROL,
    "blank": WellType.BLANK,
}


@dataclass(frozen=True)
class PlateLayout:
    """One control layout a plate's well roles can come from."""

    name: str
    roles: dict[str, WellType]  # well key ("A1") -> role
    of_run: bool  # the run's own layout, else the protocol default

    @property
    def phrase(self) -> str:
        if self.of_run:
            return f'this run\'s layout "{self.name}"'
        return f'the protocol default "{self.name}"'


# Per plate format, highest precedence first.
LayoutsByFormat = dict[PlateFormat, tuple[PlateLayout, ...]]


def _layout(tmpl: PlateTemplate, *, of_run: bool) -> PlateLayout:
    roles: dict[str, WellType] = {}
    for well_key, designation in (tmpl.template_map or {}).items():
        wt = _DESIGNATION_TO_WELL_TYPE.get(str(designation))
        if wt is not None:
            roles[str(well_key)] = wt
    return PlateLayout(name=tmpl.name, roles=roles, of_run=of_run)


async def _load_layouts(
    protocol: AssayProtocol,
    run: Run,
    plate_formats: dict[str, PlateFormat],
    workspace_id: uuid.UUID,
    plate_template_repo: PlateTemplateRepository,
) -> LayoutsByFormat:
    run_tmpl = (
        await plate_template_repo.find_by_id_in_workspace(workspace_id, run.plate_template_id)
        if run.plate_template_id is not None
        else None
    )
    out: LayoutsByFormat = {}
    for fmt in set(plate_formats.values()):
        layouts: list[PlateLayout] = []
        if run_tmpl is not None and run_tmpl.format == fmt:
            layouts.append(_layout(run_tmpl, of_run=True))
        tmpl_id = protocol.control_layouts.get(fmt.value)
        if tmpl_id is not None and not (
            layouts and run_tmpl is not None and run_tmpl.id == tmpl_id
        ):
            tmpl = await plate_template_repo.find_by_id_in_workspace(workspace_id, tmpl_id)
            if tmpl is not None:
                layouts.append(_layout(tmpl, of_run=False))
        if layouts:
            out[fmt] = tuple(layouts)
    return out


def _normalization_requires_controls(rd_normalization: ReadoutNormalization) -> bool:
    return rd_normalization in (
        ReadoutNormalization.PERCENT_INHIBITION,
        ReadoutNormalization.PERCENT_ACTIVATION,
        ReadoutNormalization.PERCENT_CONTROL,
        ReadoutNormalization.Z_SCORE,
    )


def _validate_controls_required(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    layouts: LayoutsByFormat,
) -> list[str]:
    needs_controls = any(
        _normalization_requires_controls(n)
        for rd in protocol.readout_definitions
        for n in rd.normalizations
    )
    if not needs_controls:
        return []
    errors: list[str] = []
    seen_formats: set[PlateFormat] = set()
    for fmt in plate_formats.values():
        if fmt in seen_formats:
            continue
        seen_formats.add(fmt)
        if not any(layout.roles for layout in layouts.get(fmt, ())):
            errors.append(
                f"Protocol uses control-based normalization but no Control Layout "
                f"is configured for {fmt.value}-well plates. Configure one on the "
                f"protocol's Design tab."
            )
    return errors


def _validate_well_roles(
    protocol: AssayProtocol,
    normalized: NormalizedTable,
    layouts: LayoutsByFormat,
) -> list[str]:
    """Blocking errors about where the wells' roles come from.

    With the file's role column mapped, the file supplies every role: no
    control layout is needed, but every value must be one we know. Without
    it, a layout (the run's own or the protocol default) must cover the
    file's plate formats.
    """
    if normalized.well_role_column is None:
        return _validate_controls_required(protocol, normalized.plate_formats, layouts)
    if normalized.unknown_well_roles:
        return [
            unknown_well_roles_message(normalized.well_role_column, normalized.unknown_well_roles)
        ]
    return []


def _role_disagreement_warnings(
    disagreements: Counter[tuple[int, str, int, str]],
) -> tuple[str, ...]:
    """Non-blocking notes, in precedence order: a role source used differs from a lower one."""
    return tuple(
        f"Control roles from {used} differ from {other} on {n} well{'' if n == 1 else 's'}."
        for (_, used, _, other), n in sorted(disagreements.items())
    )


def _swapped_controls(
    normalized: NormalizedTable,
    layouts: LayoutsByFormat,
    readout_ids: Collection[uuid.UUID],
    pos_control_signal: PosControlSignal,
) -> tuple[str, ...]:
    """Plates whose controls read the wrong way round, one note per plate.

    Checked on the readouts normalized against controls (``readout_ids``):
    with ``HIGH`` the positive controls must read the higher raw signal, with
    ``LOW`` the lower. Only a clear separation counts — at least two wells per
    group and a Z' above 0 — so noisy or overlapping controls say nothing.
    """
    values: dict[tuple[str, uuid.UUID], dict[WellType, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in normalized.rows:
        fmt = normalized.plate_formats.get(row.plate_name)
        plate_layouts = layouts.get(fmt, ()) if fmt is not None else ()
        role = _row_role(row, plate_layouts[0].roles if plate_layouts else None)
        if role not in (WellType.POSITIVE_CONTROL, WellType.NEGATIVE_CONTROL):
            continue
        for rd_id, value in row.readouts.items():
            if rd_id in readout_ids and isinstance(value, float):
                values[(row.plate_name, rd_id)][role].append(value)

    reads = "higher" if pos_control_signal == PosControlSignal.HIGH else "lower"
    flagged: dict[str, str] = {}
    for (plate, _), by_role in values.items():
        pos = by_role[WellType.POSITIVE_CONTROL]
        neg = by_role[WellType.NEGATIVE_CONTROL]
        if plate in flagged or PlateQualityCalculator().compute(pos, neg).z_prime <= 0:
            continue
        pos_mean, neg_mean = statistics.mean(pos), statistics.mean(neg)
        if (pos_mean < neg_mean) == (pos_control_signal == PosControlSignal.HIGH):
            flagged[plate] = (
                f"Controls look swapped on plate {plate} (positive mean {pos_mean:.4g} vs "
                f"negative mean {neg_mean:.4g}; this protocol's positive controls read "
                f"the {reads} signal)."
            )
    return tuple(flagged.values())
