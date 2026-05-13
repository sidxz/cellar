from cellar.application.admin.admin_delete_registry import (
    AdminDeleteEntry,
    all_entity_types,
    get_entry,
    register_admin_delete,
)


def test_register_and_lookup():
    """Test that we can register and retrieve an entry."""
    register_admin_delete(
        entity_type="vocabulary",
        table="controlled_vocabularies",
        label_field="name",
    )
    e = get_entry("vocabulary")
    assert e is not None
    assert e.entity_type == "vocabulary"
    assert e.table == "controlled_vocabularies"
    assert e.label_field == "name"


def test_double_register_is_idempotent():
    """Re-registering the same entity_type silently keeps the first entry.

    Idempotence supports test setups that build multiple DI containers in
    one process; production registers only once at startup.
    """
    register_admin_delete(
        entity_type="x", table="x", label_field=None
    )
    register_admin_delete(
        entity_type="x", table="other", label_field="name"
    )
    e = get_entry("x")
    assert e is not None
    assert e.table == "x"  # first registration wins


def test_all_entity_types_sorted():
    """Test that all_entity_types returns a sorted list."""
    register_admin_delete(
        entity_type="b", table="b", label_field=None
    )
    register_admin_delete(
        entity_type="a", table="a", label_field=None
    )
    assert all_entity_types() == ["a", "b"]
