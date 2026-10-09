"""The assay format a form gives a new protocol: one rule for the create and its name preview."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from returns.result import Failure, Result, Success

from cellar.domain.screening_assay.assay_format import assay_format_for_targets
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.repository import ProtocolFormRepository


async def assay_format_from_form(
    forms: ProtocolFormRepository,
    targets: TargetRepository,
    workspace_id: uuid.UUID,
    form_id: uuid.UUID | None,
    target_ids: Sequence[uuid.UUID],
    annotations: Mapping[str, Sequence[object]],
) -> Result[OntologyTerm | None, DomainError]:
    """For a form whose format follows the target, when no format was picked: the targets'
    format, else the form's own. None otherwise (the dialog sends any other form's format)."""
    if form_id is None or annotations.get("assay_format"):
        return Success(None)
    form = await forms.find_by_id_in_workspace(workspace_id, form_id)
    if form is None:
        return Failure(NotFoundError("ProtocolForm", str(form_id)))
    if not form.assay_format_from_target:
        return Success(None)
    found = await targets.find_by_ids(workspace_id, list(target_ids)) if target_ids else []
    fmt = assay_format_for_targets(t.target_type for t in found)
    if fmt is None:
        fmt = next(
            (
                OntologyTerm(
                    term_id=t["term_id"],
                    label=t["label"],
                    ontology_source=t["ontology_source"],
                    uri=t.get("uri"),
                )
                for d in form.ontology_defaults
                if d.slot_name == "assay_format"
                for t in d.terms
            ),
            None,
        )
    return Success(fmt)
