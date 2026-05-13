"""FastAPI dependency functions — resolve services from Lagom container.

Usage in route handlers::

    @router.post("/molecules")
    async def create_molecule(
        uow: UoWDep,
        dispatcher: EventDispatcherDep,
    ):
        ...

This package re-exports every ``*Dep`` alias and dependency function so
route modules can keep importing them from ``cellar.interface.dependencies``
without caring about the internal split.
"""

from __future__ import annotations

from ._admin import *  # noqa: F401, F403
from ._attachment import *  # noqa: F401, F403
from ._audit import *  # noqa: F401, F403
from ._cdd_import import *  # noqa: F401, F403
from ._chemical_registration import *  # noqa: F401, F403
from ._core import *  # noqa: F401, F403
from ._dashboard import *  # noqa: F401, F403
from ._inventory import *  # noqa: F401, F403
from ._research_organization import *  # noqa: F401, F403
from ._run_import import *  # noqa: F401, F403
from ._screening import *  # noqa: F401, F403
from ._workspace_config import *  # noqa: F401, F403

from . import (
    _admin,
    _attachment,
    _audit,
    _cdd_import,
    _chemical_registration,
    _core,
    _dashboard,
    _inventory,
    _research_organization,
    _run_import,
    _screening,
    _workspace_config,
)

__all__ = (
    _core.__all__
    + _admin.__all__
    + _audit.__all__
    + _workspace_config.__all__
    + _chemical_registration.__all__
    + _inventory.__all__
    + _screening.__all__
    + _research_organization.__all__
    + _attachment.__all__
    + _cdd_import.__all__
    + _dashboard.__all__
    + _run_import.__all__
)
