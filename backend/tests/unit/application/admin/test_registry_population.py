"""Test that admin-delete registry is populated during DI bootstrap."""

import pytest

from chem_vault.application.admin.admin_delete_registry import (
    all_entity_types,
    get_entry,
)
from chem_vault.infrastructure.persistence.settings import DatabaseSettings


@pytest.fixture
def test_settings() -> DatabaseSettings:
    """Minimal settings with a dummy URL (no real DB needed for wiring tests)."""
    return DatabaseSettings(database_url="postgresql+asyncpg://x:x@localhost:5432/x")


def test_vocabulary_registered_after_di_init(test_settings: DatabaseSettings):
    """Test that vocabulary is registered as admin-deletable after DI init."""
    from chem_vault.infrastructure.di.container import create_container

    create_container(test_settings)  # triggers all register_*() calls

    assert "vocabulary" in all_entity_types()
    entry = get_entry("vocabulary")
    assert entry is not None
    assert entry.entity_type == "vocabulary"
    assert entry.table == "controlled_vocabularies"
    assert entry.label_field == "name"
    assert entry.repo_resolver is not None
