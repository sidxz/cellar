"""Build identity for the running backend image.

Resolves version, git SHA, and build date from environment variables baked
into the image at build time, with safe fallbacks for local/dev runs.

Pure: no settings dependency and no I/O beyond ``os.environ`` and
``importlib.metadata``. The runtime ``environment`` (dev/staging/prod) is a
settings concern and is intentionally NOT resolved here — the ``/version``
route composes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import metadata


@dataclass(frozen=True)
class BuildInfo:
    """Identity of the running build."""

    version: str
    git_sha: str
    build_date: str


def _resolve_version() -> str:
    env = os.environ.get("CELLAR_VERSION")
    if env:
        return env
    try:
        return metadata.version("cellar")
    except metadata.PackageNotFoundError:
        return "0.0.0+dev"


def build_info() -> BuildInfo:
    """Return the running build's identity."""
    return BuildInfo(
        version=_resolve_version(),
        git_sha=os.environ.get("CELLAR_GIT_SHA", "unknown"),
        build_date=os.environ.get("CELLAR_BUILD_DATE", "unknown"),
    )
