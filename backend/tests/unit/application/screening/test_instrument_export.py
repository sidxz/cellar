"""Unit tests for read_instrument_file: reader selection, size limit, reader errors."""

from __future__ import annotations

from cellar.application.screening.instrument_export import (
    MAX_INSTRUMENT_FILE_BYTES,
    HolderLayout,
    InstrumentExport,
    InstrumentFileError,
    InstrumentReaders,
    read_instrument_file,
)
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.shared.errors import ValidationError


def _export(reader_id: str) -> InstrumentExport:
    return InstrumentExport(
        reader=reader_id,
        holder=HolderLayout(HolderKind.CASSETTE, 1, 1),
        positions=(),
        channels=(),
        curves=(),
        reported=(),
        settings={},
    )


class _StubReader:
    def __init__(self, id: str, label: str, recognises: bool, error: str | None = None):
        self.id = id
        self.label = label
        self.hint = "Export format A"
        self._recognises = recognises
        self._error = error
        self.calls = 0

    def recognises(self, content: bytes, filename: str) -> bool:
        self.calls += 1
        return self._recognises

    def read(self, content: bytes, filename: str) -> InstrumentExport:
        self.calls += 1
        if self._error:
            raise InstrumentFileError(self._error)
        return _export(self.id)


def test_no_reader_recognising_lists_supported_formats():
    readers = InstrumentReaders(
        (_StubReader("a", "Format A", False), _StubReader("b", "Format B", False))
    )
    failure = read_instrument_file(readers, b"x", "f.bin").failure()
    assert isinstance(failure, ValidationError)
    assert "Format A" in str(failure) and "Format B" in str(failure)


def test_first_recognising_reader_wins():
    first, second = _StubReader("a", "Format A", True), _StubReader("b", "Format B", True)
    reader, export = read_instrument_file(
        InstrumentReaders((first, second)), b"x", "f.bin"
    ).unwrap()
    assert reader is first and export.reader == "a"
    assert second.calls == 0


def test_reader_error_becomes_validation_error():
    readers = InstrumentReaders((_StubReader("a", "Format A", True, "use the raw export"),))
    failure = read_instrument_file(readers, b"x", "f.bin").failure()
    assert isinstance(failure, ValidationError) and str(failure) == "use the raw export"


def test_file_over_20_mb_is_refused_without_calling_a_reader():
    reader = _StubReader("a", "Format A", True)
    content = b"\0" * (MAX_INSTRUMENT_FILE_BYTES + 1)
    failure = read_instrument_file(InstrumentReaders((reader,)), content, "f.bin").failure()
    assert isinstance(failure, ValidationError) and str(failure) == "File is larger than 20 MB"
    assert reader.calls == 0
