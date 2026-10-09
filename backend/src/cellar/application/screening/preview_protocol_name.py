"""Live name preview while a protocol is created or corrected; discriminator suggestions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.protocol_naming_service import (
    MISSING_FIELD_LABELS,
    ProtocolNameService,
)
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import NameSibling, ProtocolRepository
from cellar.domain.shared.errors import DomainError, ValidationError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.shared.protocol_naming import with_discriminator


@dataclass(frozen=True, kw_only=True)
class PreviewProtocolNameQuery(Query):
    workspace_id: uuid.UUID
    category: str | None
    target_ids: list[uuid.UUID] = field(default_factory=list)
    ontology_annotations: dict[str, list[dict]] = field(default_factory=dict)
    discriminator: str | None = None
    # The protocol being corrected, so it does not clash with itself.
    protocol_id: uuid.UUID | None = None
    # Discriminators proposed for the bare siblings, keyed by sibling protocol id.
    sibling_discriminators: dict[uuid.UUID, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ListDiscriminatorsQuery(Query):
    workspace_id: uuid.UUID
    base: str | None = None
    q: str | None = None


@dataclass(frozen=True)
class SiblingRename:
    protocol_id: uuid.UUID
    code: str | None
    name: str | None
    error: str | None


@dataclass(frozen=True)
class NamePreview:
    name: str
    base: str
    missing: list[str]
    missing_labels: list[str]
    clash: NameSibling | None
    siblings: list[NameSibling]
    needs_discriminator: bool
    discriminator_error: str | None
    discriminator_in_pattern: bool
    sibling_renames: list[SiblingRename]


class PreviewProtocolName:
    def __init__(
        self, uow: UnitOfWork, protocol_repo: ProtocolRepository, names: ProtocolNameService
    ) -> None:
        self._uow = uow
        self._protocols = protocol_repo
        self._names = names

    async def __call__(
        self, input: PreviewProtocolNameQuery, auth: AuthContext | None = None
    ) -> Result[NamePreview, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            discriminator_error = None
            try:
                discriminator = await self._names.clean_discriminator(
                    input.workspace_id, input.discriminator
                )
            except ValidationError as exc:
                discriminator, discriminator_error = None, exc.message
            exclude_code = None
            if input.protocol_id is not None:
                existing = await self._protocols.find_by_id_in_workspace(
                    input.workspace_id, input.protocol_id
                )
                exclude_code = existing.code if existing else None
            annotations = {
                slot: [
                    OntologyTerm(
                        term_id=t["term_id"],
                        label=t["label"],
                        ontology_source=t["ontology_source"],
                        uri=t.get("uri"),
                    )
                    for t in terms
                ]
                for slot, terms in input.ontology_annotations.items()
            }
            d = await self._names.derive(
                input.workspace_id,
                category=input.category,
                target_ids=input.target_ids,
                annotations=annotations,
                discriminator=discriminator,
                exclude_code=exclude_code,
            )
            renames: list[SiblingRename] = []
            taken = {d.rendered.name.lower()} | {
                s.name.lower()
                for s in d.siblings
                if s.protocol_id not in input.sibling_discriminators
            }
            for s in d.bare_siblings:
                raw = input.sibling_discriminators.get(s.protocol_id)
                if not raw or not raw.strip():
                    continue
                try:
                    cleaned = await self._names.clean_discriminator(input.workspace_id, raw)
                except ValidationError as exc:
                    renames.append(SiblingRename(s.protocol_id, s.code, None, exc.message))
                    continue
                name = with_discriminator(d.rendered.base, cleaned)
                error = "Same name as another protocol" if name.lower() in taken else None
                taken.add(name.lower())
                renames.append(SiblingRename(s.protocol_id, s.code, name, error))
        return Success(
            NamePreview(
                name=d.rendered.name,
                base=d.rendered.base,
                missing=list(d.rendered.missing),
                missing_labels=[MISSING_FIELD_LABELS.get(m, m) for m in d.rendered.missing],
                clash=d.clash,
                siblings=list(d.siblings),
                needs_discriminator=d.needs_discriminator,
                discriminator_error=discriminator_error,
                discriminator_in_pattern=d.rendered.discriminator_in_pattern,
                sibling_renames=renames,
            )
        )


class ListDiscriminators:
    """Discriminators already in use, for the picker (same base name first when given)."""

    def __init__(self, uow: UnitOfWork, protocol_repo: ProtocolRepository) -> None:
        self._uow = uow
        self._protocols = protocol_repo

    async def __call__(
        self, input: ListDiscriminatorsQuery, auth: AuthContext | None = None
    ) -> Result[list[str], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(
                await self._protocols.list_discriminators(
                    input.workspace_id, base=input.base, q=input.q
                )
            )
