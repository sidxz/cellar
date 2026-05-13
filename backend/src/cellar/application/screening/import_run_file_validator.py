"""Control-layout validation helpers for the run-file importer.

Extracted from ``import_run_file.py`` to isolate the protocol /
plate-template / well-type validation rules from the use case
orchestration.

Two layers:

- ``_load_templates_by_format`` (+ ``_build_template_lookup``) — given a
  protocol's ``control_layouts`` map and the set of plate formats seen
  in the upload, load each referenced ``PlateTemplate`` and project its
  designation map into a ``WellType`` lookup keyed by well label.
- ``_validate_controls_required`` — protocol-level gate: any readout
  whose normalization depends on controls (PERCENT_INHIBITION /
  PERCENT_ACTIVATION / PERCENT_CONTROL / Z_SCORE) requires a control
  layout for every plate format used in the file; missing layouts
  become user-visible validation errors.
"""

from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ReadoutNormalization, WellType
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.domain.screening_assay.protocol import Protocol as AssayProtocol
from cellar.domain.screening_assay.repository import PlateTemplateRepository
from cellar.domain.shared.enums import PlateFormat


_DESIGNATION_TO_WELL_TYPE: dict[str, WellType] = {
    "compound": WellType.SAMPLE,
    "positive_control": WellType.POSITIVE_CONTROL,
    "negative_control": WellType.NEGATIVE_CONTROL,
    "blank": WellType.BLANK,
}


def _build_template_lookup(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    templates_by_id: dict[uuid.UUID, PlateTemplate],
) -> dict[PlateFormat, dict[str, WellType]]:
    out: dict[PlateFormat, dict[str, WellType]] = {}
    for fmt in set(plate_formats.values()):
        tmpl_id = protocol.control_layouts.get(fmt.value)
        if tmpl_id is None:
            continue
        tmpl = templates_by_id.get(tmpl_id)
        if tmpl is None:
            continue
        per_well: dict[str, WellType] = {}
        for well_key, designation in (tmpl.template_map or {}).items():
            wt = _DESIGNATION_TO_WELL_TYPE.get(str(designation))
            if wt is not None:
                per_well[str(well_key)] = wt
        out[fmt] = per_well
    return out


async def _load_templates_by_format(
    protocol: AssayProtocol,
    plate_formats: dict[str, PlateFormat],
    workspace_id: uuid.UUID,
    plate_template_repo: PlateTemplateRepository,
) -> dict[PlateFormat, dict[str, WellType]]:
    used_fmts = set(plate_formats.values())
    templates_by_id: dict[uuid.UUID, PlateTemplate] = {}
    for fmt in used_fmts:
        tmpl_id = protocol.control_layouts.get(fmt.value)
        if tmpl_id is None or tmpl_id in templates_by_id:
            continue
        tmpl = await plate_template_repo.find_by_id_in_workspace(workspace_id, tmpl_id)
        if tmpl is not None:
            templates_by_id[tmpl_id] = tmpl
    return _build_template_lookup(protocol, plate_formats, templates_by_id)


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
    templates: dict[PlateFormat, dict[str, WellType]],
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
        per_well = templates.get(fmt)
        if not per_well:
            errors.append(
                f"Protocol uses control-based normalization but no Control Layout "
                f"is configured for {fmt.value}-well plates. Configure one on the "
                f"protocol's Design tab."
            )
    return errors
