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

import pytest

_CASCADE_MODULES = [
    "chem_vault.infrastructure.cascade.rules_screening_assay",
    "chem_vault.infrastructure.cascade.rules_research_organization",
    "chem_vault.infrastructure.cascade.rules_audit_compliance",
    "chem_vault.infrastructure.cascade.rules_chemical_registration",
    "chem_vault.infrastructure.cascade.rules_inventory",
]

# SQLAlchemy model modules that must be in Base.metadata for the runner to work.
_MODEL_MODULES = [
    "chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models",
    "chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models",
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
    # We detect this by checking whether the registry is empty after a dummy import;
    # the simplest approach is to evict and re-import unconditionally — the register
    # calls are idempotent (they check for duplicates).
    from chem_vault.infrastructure.cascade.registry import get_rules_for_parent
    if not get_rules_for_parent("protocols"):
        # Registry was cleared — force re-import of all cascade modules.
        for mod_name in _CASCADE_MODULES:
            sys.modules.pop(mod_name, None)
        for mod_name in _CASCADE_MODULES:
            importlib.import_module(mod_name)
