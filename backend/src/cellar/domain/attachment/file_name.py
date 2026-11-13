"""Choosing a free attachment file name on an entity."""

from __future__ import annotations

import re
from collections.abc import Collection

_NUMBERED = re.compile(r"^(.*) \((\d+)\)$")


def numbered_file_name(name: str, taken: Collection[str]) -> str:
    """``name`` if it is free, else ``stem (N).ext`` with the lowest free N from 2.

    The number goes before the last extension; a name with no extension gets
    `` (N)`` appended. A stem already ending in `` (N)`` counts on from it
    rather than nesting a second number.
    """
    if name not in taken:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    else:
        ext = f".{ext}"
    n = 2
    if (m := _NUMBERED.match(stem)) is not None:
        stem, n = m.group(1), int(m.group(2)) + 1
    while (candidate := f"{stem} ({n}){ext}") in taken:
        n += 1
    return candidate
