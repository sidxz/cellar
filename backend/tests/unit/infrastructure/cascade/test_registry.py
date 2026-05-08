import pytest
from chem_vault.domain.shared.cascade import (
    CascadeAction, CascadeRule, register_rules, get_rules_for_parent,
)
from chem_vault.domain.shared.cascade.registry import _clear_for_test


@pytest.fixture(autouse=True)
def _reset():
    _clear_for_test()


def test_register_and_lookup_by_parent():
    r = CascadeRule(
        child_table="runs", fk_column="protocol_id", parent_table="protocols",
        action=CascadeAction.CASCADE, label_field="name", display_label="Runs",
        recurse_into_entity="run",
    )
    register_rules(r)
    assert get_rules_for_parent("protocols") == [r]
    assert get_rules_for_parent("nonexistent") == []


def test_multiple_rules_same_parent():
    a = CascadeRule(child_table="a", fk_column="p_id", parent_table="p",
                    action=CascadeAction.CASCADE, display_label="A")
    b = CascadeRule(child_table="b", fk_column="p_id", parent_table="p",
                    action=CascadeAction.SET_NULL, display_label="B")
    register_rules(a, b)
    assert set(get_rules_for_parent("p")) == {a, b}
