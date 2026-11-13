"""The file upload routes read at most one byte past the size limit."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from returns.result import Failure

from cellar.application.screening.instrument_export import MAX_INSTRUMENT_FILE_BYTES
from cellar.domain.shared.errors import ValidationError
from cellar.interface.routes.run_import import import_instrument_file, preview_instrument_file
from cellar.interface.routes.run_positions import resolve_layout_file


class HugeUpload:
    """An upload far over the limit; records how much the route asked for."""

    filename = "big.csv"
    content_type = "text/csv"

    def __init__(self) -> None:
        self.asked: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.asked.append(size)
        return b"x" * (MAX_INSTRUMENT_FILE_BYTES + 1 if size < 0 else size)


class Refusing:
    def __init__(self) -> None:
        self.content_lengths: list[int] = []

    async def __call__(self, query, auth=None):  # type: ignore[no-untyped-def]
        self.content_lengths.append(len(query.content))
        return Failure(ValidationError("File is larger than 20 MB"))


AUTH = SimpleNamespace(workspace_id=uuid.uuid4())


@pytest.mark.parametrize(
    "call",
    [
        lambda uc, f: resolve_layout_file(uuid.uuid4(), AUTH, uc, f),  # type: ignore[arg-type]
        lambda uc, f: preview_instrument_file(uuid.uuid4(), AUTH, uc, f),  # type: ignore[arg-type]
        lambda uc, f: import_instrument_file(
            uuid.uuid4(),
            AUTH,  # type: ignore[arg-type]
            uc,
            f,
            '{"positions": []}',
        ),
    ],
    ids=["layout", "instrument-preview", "instrument-import"],
)
async def test_route_reads_at_most_one_byte_past_the_limit(call):  # type: ignore[no-untyped-def]
    upload, uc = HugeUpload(), Refusing()
    with pytest.raises(ValidationError):
        await call(uc, upload)
    assert upload.asked == [MAX_INSTRUMENT_FILE_BYTES + 1]
    assert uc.content_lengths == [MAX_INSTRUMENT_FILE_BYTES + 1]
