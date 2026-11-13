"""Instrument and file-format names stay inside the reader package and its tests."""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"nanotemper|prometheus|capillar", re.IGNORECASE)
ALLOWED = (
    "src/cellar/infrastructure/instrument_readers/",
    "src/cellar/domain/screening_assay/holder.py",
    "tests/unit/infrastructure/instrument_readers/",
    "tests/helpers/instrument_workbook.py",
    "tests/unit/domain/screening_assay/test_holder.py",
    "tests/unit/test_instrument_boundary.py",
)


def test_instrument_names_stay_inside_the_reader():
    offenders = [
        rel
        for top in ("src", "tests", "alembic")
        for path in sorted((BACKEND / top).rglob("*.py"))
        if not (rel := path.relative_to(BACKEND).as_posix()).startswith(ALLOWED)
        and PATTERN.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
