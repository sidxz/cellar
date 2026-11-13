"""Unit tests for ListInstrumentFileFormats."""

from __future__ import annotations

import pytest

from cellar.application.screening.instrument_export import InstrumentReaders
from cellar.application.screening.list_instrument_file_formats import (
    InstrumentFileFormat,
    ListInstrumentFileFormats,
    ListInstrumentFileFormatsQuery,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError
from tests.fakes.fake_auth import FakeAuth


class _Reader:
    def __init__(self, id: str, label: str, hint: str) -> None:
        self.id = id
        self.label = label
        self.hint = hint

    def recognises(self, content: bytes, filename: str) -> bool:  # pragma: no cover
        return False

    def read(self, content: bytes, filename: str):  # type: ignore[no-untyped-def]  # pragma: no cover
        raise NotImplementedError


READERS = InstrumentReaders(
    (_Reader("b", "Format B", "Export format B"), _Reader("a", "Format A", "Export format A"))
)


async def _list(auth: FakeAuth, workspace_id=None):  # type: ignore[no-untyped-def]
    query = ListInstrumentFileFormatsQuery(workspace_id=workspace_id or auth.workspace_id)
    return await ListInstrumentFileFormats(readers=READERS)(query, auth=auth)


async def test_lists_each_reader_in_registry_order():
    out = (await _list(FakeAuth())).unwrap()
    assert out == (
        InstrumentFileFormat(id="b", label="Format B", hint="Export format B"),
        InstrumentFileFormat(id="a", label="Format A", hint="Export format A"),
    )


async def test_a_viewer_can_list():
    assert len((await _list(FakeAuth(role="viewer"))).unwrap()) == 2


async def test_no_role_raises_authorization_error():
    with pytest.raises(AuthorizationError):
        await _list(FakeAuth(role="none"))


async def test_other_workspace_raises_not_found():
    auth = FakeAuth()
    with pytest.raises(NotFoundError):
        await _list(auth, workspace_id=FakeAuth().workspace_id)
