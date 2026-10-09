"""Terms protocols already use in one annotation slot: the picker's "Used here" group."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.protocol_naming import NamingContext, NamingTerm, short_label
from cellar.domain.workspace_config.repository import NamingLabelRepository


@dataclass(frozen=True, kw_only=True)
class ListTermsInUseQuery(Query):
    workspace_id: uuid.UUID
    slot: str


@dataclass(frozen=True)
class TermInUse:
    term_id: str
    label: str
    ontology_source: str
    uri: str | None
    short_label: str  # as protocol names render it: the admin's override, else the derived one
    protocol_count: int


class ListTermsInUse:
    def __init__(
        self, uow: UnitOfWork, protocol_repo: ProtocolRepository, label_repo: NamingLabelRepository
    ) -> None:
        self._uow = uow
        self._protocols = protocol_repo
        self._labels = label_repo

    async def __call__(
        self, input: ListTermsInUseQuery, auth: AuthContext | None = None
    ) -> Result[list[TermInUse], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            uses = await self._protocols.list_annotation_terms(input.workspace_id, (input.slot,))
            overrides = {
                label.term_id: label.short_label
                for label in await self._labels.find_by_workspace(input.workspace_id)
            }
        ctx = NamingContext(overrides_by_term=overrides)
        return Success(
            [
                TermInUse(
                    term_id=u.term_id,
                    label=u.label,
                    ontology_source=u.ontology_source,
                    uri=u.uri,
                    short_label=short_label(
                        NamingTerm(u.term_id, u.label, u.ontology_source), ctx
                    ),
                    protocol_count=u.protocol_count,
                )
                for u in uses
            ]
        )
