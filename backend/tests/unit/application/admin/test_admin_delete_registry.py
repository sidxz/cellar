import pytest

from chem_vault.application.admin.admin_delete_registry import (
    AdminDeleteEntry,
    all_entity_types,
    get_entry,
    register_admin_delete,
)


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
