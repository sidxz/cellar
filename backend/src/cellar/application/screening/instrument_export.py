"""Instrument-neutral description of an instrument file, and the reader protocol.

Readers (infrastructure) turn an instrument's export into an ``InstrumentExport``.
Nothing downstream of a reader sees the file or the instrument's own layout.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from returns.result import Failure, Result, Success

from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.shared.errors import ValidationError

MAX_INSTRUMENT_FILE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class HolderLayout:
    kind: HolderKind  # CASSETTE or PLATE
    rows: int  # 1 for a cassette
    columns: int  # for a cassette: highest position number in the file


@dataclass(frozen=True)
class ExportPosition:
    row: int  # 1-based; always 1 for a cassette
    column: int  # 1-based
    label: str  # sample name typed at the instrument, verbatim; may be ""


@dataclass(frozen=True)
class ExportChannel:
    key: str  # stable within the reader, e.g. "ratio"
    label: str  # for display, e.g. "Ratio 350/330"
    x_unit: str  # e.g. "°C"
    y_unit: str | None
    x_label: str | None = None  # name of the x quantity, e.g. "Temperature"


@dataclass(frozen=True)
class ExportCurve:
    row: int
    column: int
    channel: str  # ExportChannel.key
    x: tuple[float, ...]
    y: tuple[float, ...]


@dataclass(frozen=True)
class ReportedValue:
    row: int
    column: int
    channel: str
    kind: str  # neutral: "transition" or "onset"
    ordinal: int  # 1-based, as numbered by the instrument
    label: str  # the instrument's own name for it
    value: float
    unit: str


@dataclass(frozen=True)
class InstrumentExport:
    reader: str  # the reader's id
    holder: HolderLayout
    positions: tuple[ExportPosition, ...]
    channels: tuple[ExportChannel, ...]
    curves: tuple[ExportCurve, ...]
    reported: tuple[ReportedValue, ...]
    settings: Mapping[str, str]  # run settings found in the file, for display


class InstrumentFileError(ValueError):
    """A reader recognised the file but cannot read it. The message is shown to the user."""


class InstrumentReader(Protocol):
    id: str
    label: str  # shown to the user: the format recognised, and the list of supported formats

    def recognises(self, content: bytes, filename: str) -> bool: ...

    def read(self, content: bytes, filename: str) -> InstrumentExport: ...


class InstrumentReaders(tuple[InstrumentReader, ...]):
    """The readers the import tries, in order. A tuple subclass only so dependency injection has a type to bind."""  # noqa: E501


def read_instrument_file(
    readers: InstrumentReaders, content: bytes, filename: str
) -> Result[tuple[InstrumentReader, InstrumentExport], ValidationError]:
    """Read the file with the first reader that recognises it."""
    if len(content) > MAX_INSTRUMENT_FILE_BYTES:
        return Failure(ValidationError("File is larger than 20 MB"))
    reader = next((r for r in readers if r.recognises(content, filename)), None)
    if reader is None:
        return Failure(
            ValidationError(
                "Unrecognised instrument file. Supported formats: "
                + "; ".join(r.label for r in readers)
            )
        )
    try:
        return Success((reader, reader.read(content, filename)))
    except InstrumentFileError as exc:
        return Failure(ValidationError(str(exc)))
