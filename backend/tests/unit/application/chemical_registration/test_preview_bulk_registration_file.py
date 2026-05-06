"""Tests for PreviewBulkRegistrationFile use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.preview_bulk_registration_file import (
    ParsedItemDTO,
    PreviewBulkRegistrationFile,
    PreviewBulkRegistrationFileQuery,
)
from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat
from chem_vault.domain.shared.errors import ValidationError


class StubParser:
    def __init__(self, items: list[ParsedItemDTO]) -> None:
        self.items = items
        self.calls: list[tuple[str, BulkRegistrationFileFormat]] = []

    def parse(
        self,
        *,
        content: bytes,
        filename: str,
        file_format: BulkRegistrationFileFormat,
    ) -> list[ParsedItemDTO]:
        self.calls.append((filename, file_format))
        return list(self.items)


@dataclass
class StubAuth:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:  # pragma: no cover - simple
        return True


@pytest.fixture
def auth() -> StubAuth:
    return StubAuth(user_id=uuid.uuid4(), workspace_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_preview_returns_items_and_counts(auth: StubAuth) -> None:
    parsed = [
        ParsedItemDTO(row_index=0, name="A", smiles="C"),
        ParsedItemDTO(row_index=1, name="B", smiles=None, error="bad"),
        ParsedItemDTO(row_index=2, name="C", smiles="CC"),
    ]
    parser = StubParser(parsed)
    uc = PreviewBulkRegistrationFile(parser=parser)

    result = await uc(
        PreviewBulkRegistrationFileQuery(
            workspace_id=auth.workspace_id,
            filename="x.csv",
            content=b"a,b,c\n1,2,3\n",
            file_format=BulkRegistrationFileFormat.CSV,
        ),
        auth=auth,
    )
    assert isinstance(result, Success)
    outcome = result.unwrap()
    assert outcome.total_count == 3
    assert outcome.error_count == 1
    assert len(outcome.items) == 3
    assert parser.calls == [("x.csv", BulkRegistrationFileFormat.CSV)]


@pytest.mark.asyncio
async def test_preview_rejects_empty_file(auth: StubAuth) -> None:
    uc = PreviewBulkRegistrationFile(parser=StubParser([]))
    result = await uc(
        PreviewBulkRegistrationFileQuery(
            workspace_id=auth.workspace_id,
            filename="x.csv",
            content=b"",
            file_format=BulkRegistrationFileFormat.CSV,
        ),
        auth=auth,
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)


@pytest.mark.asyncio
async def test_preview_rejects_oversize_file(auth: StubAuth) -> None:
    uc = PreviewBulkRegistrationFile(parser=StubParser([]))
    huge = b"x" * (51 * 1024 * 1024)
    result = await uc(
        PreviewBulkRegistrationFileQuery(
            workspace_id=auth.workspace_id,
            filename="x.csv",
            content=huge,
            file_format=BulkRegistrationFileFormat.CSV,
        ),
        auth=auth,
    )
    assert isinstance(result, Failure)
    assert "50 MB" in str(result.failure())


@pytest.mark.asyncio
async def test_preview_rejects_when_parser_returns_zero_records(
    auth: StubAuth,
) -> None:
    uc = PreviewBulkRegistrationFile(parser=StubParser([]))
    result = await uc(
        PreviewBulkRegistrationFileQuery(
            workspace_id=auth.workspace_id,
            filename="x.csv",
            content=b"header_only",
            file_format=BulkRegistrationFileFormat.CSV,
        ),
        auth=auth,
    )
    assert isinstance(result, Failure)
    assert "no records" in str(result.failure())
