import pytest

from chem_vault.application.admin.admin_delete_registry import (
    AdminDeleteEntry,
    all_entity_types,
    get_entry,
    register_admin_delete,
    _REGISTRY,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear and restore registry state around each test."""
    snapshot = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


def _dummy_resolver():
    """Dummy resolver for testing."""
    return object()


def test_register_and_lookup():
    """Test that we can register and retrieve an entry."""
    register_admin_delete(
        entity_type="vocabulary",
        table="controlled_vocabularies",
        label_field="name",
        repo_resolver=_dummy_resolver,
    )
    e = get_entry("vocabulary")
    assert e is not None
    assert e.entity_type == "vocabulary"
    assert e.table == "controlled_vocabularies"
    assert e.label_field == "name"
    assert e.repo_resolver is _dummy_resolver


def test_double_register_raises():
    """Test that registering the same entity_type twice raises RuntimeError."""
    register_admin_delete(
        entity_type="x", table="x", label_field=None, repo_resolver=_dummy_resolver
    )
    with pytest.raises(RuntimeError, match="x already registered"):
        register_admin_delete(
            entity_type="x", table="x", label_field=None, repo_resolver=_dummy_resolver
        )


def test_all_entity_types_sorted():
    """Test that all_entity_types returns a sorted list."""
    register_admin_delete(
        entity_type="b", table="b", label_field=None, repo_resolver=_dummy_resolver
    )
    register_admin_delete(
        entity_type="a", table="a", label_field=None, repo_resolver=_dummy_resolver
    )
    assert all_entity_types() == ["a", "b"]


def test_get_nonexistent_returns_none():
    """Test that get_entry returns None for nonexistent entity_type."""
    assert get_entry("nonexistent") is None


def test_admin_delete_entry_frozen():
    """Test that AdminDeleteEntry is frozen (immutable)."""
    entry = AdminDeleteEntry(
        entity_type="test",
        table="test_table",
        label_field="name",
        repo_resolver=_dummy_resolver,
    )
    with pytest.raises(AttributeError):
        entry.entity_type = "changed"  # type: ignore


def test_register_with_null_label_field():
    """Test registration with label_field=None."""
    register_admin_delete(
        entity_type="no_label",
        table="some_table",
        label_field=None,
        repo_resolver=_dummy_resolver,
    )
    e = get_entry("no_label")
    assert e is not None
    assert e.label_field is None
