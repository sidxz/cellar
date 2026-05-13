"""Tests for audit & compliance enums."""

from cellar.domain.audit_compliance.enums import OperationType


def test_admin_hard_delete_value():
    """Test that ADMIN_HARD_DELETE operation type resolves correctly."""
    assert OperationType.ADMIN_HARD_DELETE.value == "admin_hard_delete"
    assert OperationType("admin_hard_delete") == OperationType.ADMIN_HARD_DELETE
