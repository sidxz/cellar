"""Instrument file readers. ``default_readers`` is the one place a new reader is registered."""

from __future__ import annotations

from cellar.application.screening.instrument_export import InstrumentReaders
from cellar.infrastructure.instrument_readers.prometheus_raw_xlsx import PrometheusRawXlsxReader


def default_readers() -> InstrumentReaders:
    return InstrumentReaders((PrometheusRawXlsxReader(),))
