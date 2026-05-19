"""Tests for audit & compliance enums."""

from cellar.domain.audit_compliance.enums import OperationType


def test_admin_hard_delete_value():
    """Test that ADMIN_HARD_DELETE operation type resolves correctly."""
    assert OperationType.ADMIN_HARD_DELETE.value == "admin_hard_delete"
    assert OperationType("admin_hard_delete") == OperationType.ADMIN_HARD_DELETE


def test_curve_point_exclusion_is_a_valid_op_type():
    """Test that CURVE_POINT_EXCLUSION operation type resolves correctly."""
    assert OperationType.CURVE_POINT_EXCLUSION.value == "curve_point_exclusion"
    assert OperationType("curve_point_exclusion") == OperationType.CURVE_POINT_EXCLUSION
