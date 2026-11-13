"""ListInstrumentFileFormats: the instrument files the import reads, for the upload step.

Reads no database, so it has no unit of work: the formats are the registered readers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.instrument_export import InstrumentReaders
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True)
class InstrumentFileFormat:
    id: str
    label: str
    hint: str


@dataclass(frozen=True, kw_only=True)
class ListInstrumentFileFormatsQuery(Query):
    workspace_id: uuid.UUID


class ListInstrumentFileFormats:
    def __init__(self, readers: InstrumentReaders) -> None:
        self._readers = readers

    async def __call__(
        self, input: ListInstrumentFileFormatsQuery, auth: AuthContext | None = None
    ) -> Result[tuple[InstrumentFileFormat, ...], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        return Success(tuple(InstrumentFileFormat(r.id, r.label, r.hint) for r in self._readers))
