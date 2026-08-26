"""Build identity for the running backend image.

Resolves version, git SHA and build date from the environment the image (CI)
or ``make dev`` (``scripts/build-info.sh``) baked in. ``APP_*`` is the shared
name family with the frontend; ``CELLAR_*`` is accepted for older deployments.
With nothing set every value is the honest dev fallback — ``pyproject.toml``
is deliberately NOT consulted: it is a placeholder, git tags are the source
of truth (RELEASING.md).

Pure: no settings dependency and no I/O beyond ``os.environ``. The runtime
``environment`` (dev/staging/prod) is a settings concern and is intentionally
NOT resolved here — the ``/version`` route composes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEV_VERSION = "0.0.0+dev"


@dataclass(frozen=True)
class BuildInfo:
    """Identity of the running build."""

    version: str
    git_sha: str
    build_date: str


def _env(*names: str, default: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def build_info() -> BuildInfo:
    """Return the running build's identity."""
    return BuildInfo(
        version=_env("APP_VERSION", "CELLAR_VERSION", default=DEV_VERSION),
        git_sha=_env("APP_GIT_SHA", "CELLAR_GIT_SHA", default="unknown"),
        build_date=_env("APP_BUILD_DATE", "CELLAR_BUILD_DATE", default="unknown"),
    )
