"""Cascade integration test fixtures.

The unit test ``test_fk_coverage.py`` intentionally calls ``_clear_cascade_registry()``
and evicts cascade modules from ``sys.modules`` so that subsequent unit tests start
from a clean state.  When unit tests run *before* these integration tests in the same
pytest session, the cascade registry is empty and ``get_rules_for_parent()`` returns
nothing — breaking any test that expects children to appear in a cascade tree.

The autouse fixture below re-imports the cascade rule modules before *each* integration
test in this directory, ensuring the registry is always populated regardless of
test-collection ordering.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator

import pytest

_CASCADE_MODULES = [
    "cellar.infrastructure.cascade.rules_screening_assay",
    "cellar.infrastructure.cascade.rules_research_organization",
    "cellar.infrastructure.cascade.rules_audit_compliance",
    "cellar.infrastructure.cascade.rules_chemical_registration",
    "cellar.infrastructure.cascade.rules_inventory",
    "cellar.infrastructure.cascade.rules_attachment",
]

# SQLAlchemy model modules that must be in Base.metadata for the runner to work.
_MODEL_MODULES = [
    "cellar.infrastructure.persistence.sqlalchemy.screening_assay.models",
    "cellar.infrastructure.persistence.sqlalchemy.research_organization.models",
]


@pytest.fixture(autouse=True)
def _ensure_cascade_registry_populated() -> None:
    """Re-import cascade modules so the registry is always populated before each test.

    This is a no-op when modules are already present and the registry is non-empty;
    if the registry was cleared by ``test_fk_coverage.py``, it re-populates it.
    """
    # Models are idempotent — safe to import multiple times.
    for mod_name in _MODEL_MODULES:
        importlib.import_module(mod_name)

    # Cascade modules need to re-execute register_rules() if the registry was cleared.
    # register_rules() does not dedupe, so a module already in sys.modules must
    # never be re-imported outside the "registry was cleared" branch below —
    # that would append its rules a second time.
    from cellar.infrastructure.cascade.registry import get_rules_for_parent

    if not get_rules_for_parent("protocols"):
        # Registry was cleared — force re-import of all cascade modules.
        for mod_name in _CASCADE_MODULES:
            sys.modules.pop(mod_name, None)
        for mod_name in _CASCADE_MODULES:
            importlib.import_module(mod_name)
    else:
        # "protocols" has rules, but that only proves whichever module some
        # *other* test file happened to import at collection time (usually
        # rules_screening_assay) has run — not that every module has. Import
        # any module that has never fired yet; already-imported ones are left
        # alone so their rules aren't appended twice.
        for mod_name in _CASCADE_MODULES:
            if mod_name not in sys.modules:
                importlib.import_module(mod_name)


@pytest.fixture
def extra_rules() -> Iterator[Callable[..., None]]:
    """Register cascade rules for one test; the registry is restored afterwards."""
    from cellar.infrastructure.cascade.registry import (
        _clear_for_test,
        all_rules,
        register_rules,
    )

    snapshot = all_rules()
    yield register_rules
    _clear_for_test()
    register_rules(*snapshot)
