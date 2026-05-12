"""Test fixtures scoped to the admin-delete unit tests."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from cellar.application.admin.admin_delete_registry import _REGISTRY


@pytest.fixture(autouse=True)
def _admin_delete_registry_isolation() -> Iterator[None]:
    """Snapshot and restore the admin-delete registry around each test."""
    snapshot = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)
