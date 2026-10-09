"""RequestTarget — create a missing target in prot-cellar from the target picker.

prot-cellar owns the catalog and has no approval step (decision P10), so the
target is created there directly with the requester's own forwarded tokens
(never a service identity), then upserted into the local mirror at once so the
picker can select it without waiting for the next sync.

Protein targets (single protein, domain) need exactly one component in
prot-cellar; the chemist names the protein by UniProt accession or entry name
and the adapter resolves it. Multi-component types (complex, family, PPI) are
not requestable here.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.screening.sync_targets import mirror_target
from cellar.application.screening.target_source import NewTarget, TargetSource
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.screening_assay.target import Target
from cellar.domain.shared.errors import DomainError, ValidationError
from cellar.domain.shared.protocol_naming import NCBITAXON

NEEDS_PROTEIN = frozenset({TargetType.SINGLE_PROTEIN, TargetType.DOMAIN})
REQUESTABLE_TYPES = NEEDS_PROTEIN | {
    TargetType.ORGANISM,
    TargetType.CELL_LINE,
    TargetType.TISSUE,
    TargetType.NUCLEIC_ACID,
    TargetType.UNKNOWN,
}
_TAXON_RE = re.compile(rf"^{re.escape(NCBITAXON)}(\d+)$")
_CHEMBL_RE = re.compile(r"^CHEMBL\d+$")


@dataclass(frozen=True, kw_only=True)
class RequestTargetCommand(Command):
    workspace_id: uuid.UUID
    name: str
    target_type: str
    organism_term_id: str
    organism_label: str
    chembl_id: str | None = None
    protein_identifier: str | None = None
    forwarded_headers: Mapping[str, str] = field(default_factory=dict)


class RequestTarget:
    def __init__(self, uow: UnitOfWork, repo: TargetRepository, source: TargetSource) -> None:
        self._uow = uow
        self._repo = repo
        self._source = source

    async def __call__(
        self, input: RequestTargetCommand, auth: AuthContext | None = None
    ) -> Result[Target, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        validated = _new_target(input)
        if isinstance(validated, Failure):
            return validated

        try:
            created = await self._source.create_target(
                validated.unwrap(), forwarded_headers=input.forwarded_headers
            )
        except DomainError as exc:  # the adapter's documented failures
            return Failure(exc)

        target = mirror_target(created, input.workspace_id)
        async with self._uow:
            await self._repo.save(target)
            await self._uow.commit()
        return Success(target)


def _new_target(input: RequestTargetCommand) -> Result[NewTarget, DomainError]:
    name = input.name.strip()
    if not name:
        return Failure(ValidationError("Give the target a name"))
    try:
        target_type = TargetType(input.target_type)
    except ValueError:
        target_type = None
    if target_type not in REQUESTABLE_TYPES:
        return Failure(
            ValidationError(f"Target type '{input.target_type}' can't be requested here")
        )
    taxon = _TAXON_RE.match(input.organism_term_id.strip())
    if taxon is None:
        return Failure(
            ValidationError(
                "Pick the organism from the NCBITaxon list; a typed organism name "
                "can't be matched in ProtCellar"
            )
        )
    protein = (input.protein_identifier or "").strip() or None
    if target_type in NEEDS_PROTEIN and protein is None:
        return Failure(
            ValidationError("A protein target needs its UniProt accession or entry name")
        )
    chembl_id = (input.chembl_id or "").strip().upper() or None
    if chembl_id is not None and not _CHEMBL_RE.match(chembl_id):
        return Failure(ValidationError(f"'{input.chembl_id}' is not a ChEMBL id (CHEMBL…)"))
    return Success(
        NewTarget(
            name=name,
            target_type=target_type.value,
            organism_tax_id=int(taxon.group(1)),
            organism_label=input.organism_label.strip(),
            chembl_id=chembl_id,
            protein_identifier=protein if target_type in NEEDS_PROTEIN else None,
        )
    )
