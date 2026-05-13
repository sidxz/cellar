"""PreviewBulkRegistrationFile — parse a bulk-registration upload without persisting.

Parsing-only use case used by the wizard's Preview step. Returns the list of
parsed rows (with per-row errors) so the user can verify what was detected
before kicking off the durable Temporal workflow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.query import Query
from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.domain.shared.errors import DomainError, ValidationError

# ---------------------------------------------------------------------------
# Application port — implemented by infrastructure parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedItemDTO:
    """Application-layer DTO for a single parsed row.

    Mirrors the infrastructure ``ParsedMoleculeItem`` so the application layer
    has no infra import.
    """

    row_index: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = field(default_factory=list)
    amount_value: float | None = None
    amount_unit: str = "mg"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    purity: float | None = None
    batch_source: str = "synthesized"
    appearance: str | None = None
    error: str | None = None


class BulkFileParserProtocol(Protocol):
    """Application-layer protocol for the chemical-file parser factory."""

    def parse(
        self,
        *,
        content: bytes,
        filename: str,
        file_format: BulkRegistrationFileFormat,
    ) -> list[ParsedItemDTO]: ...


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PreviewBulkRegistrationFileQuery(Query):
    workspace_id: uuid.UUID
    filename: str
    content: bytes
    file_format: BulkRegistrationFileFormat


@dataclass(frozen=True)
class PreviewBulkRegistrationFileOutcome:
    items: list[ParsedItemDTO]
    total_count: int
    error_count: int


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB — matches the start endpoint cap


class PreviewBulkRegistrationFile:
    def __init__(self, parser: BulkFileParserProtocol) -> None:
        self._parser = parser

    async def __call__(
        self,
        input: PreviewBulkRegistrationFileQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewBulkRegistrationFileOutcome, DomainError]:
        require_editor(auth)

        if not input.filename.strip():
            return Failure(ValidationError("filename is required"))
        if not input.content:
            return Failure(ValidationError("file is empty"))
        if len(input.content) > _MAX_FILE_BYTES:
            return Failure(ValidationError("file exceeds 50 MB cap"))

        items = self._parser.parse(
            content=input.content,
            filename=input.filename,
            file_format=input.file_format,
        )
        if not items:
            return Failure(ValidationError("file contains no records"))

        error_count = sum(1 for i in items if i.error is not None)

        return Success(
            PreviewBulkRegistrationFileOutcome(
                items=items,
                total_count=len(items),
                error_count=error_count,
            )
        )
