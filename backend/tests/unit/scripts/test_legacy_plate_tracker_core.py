from __future__ import annotations

from datetime import date, datetime

import pytest
from scripts.migrate_legacy_plate_tracker import (
    LegacyAccount, LegacyData, LegacyLibrary, LegacySet, LegacySetParent,
    LegacyTransaction, LegacyTransactionPlate,
    build_account_email_map, compose_set_description, due_date_from,
    map_loan_item_status, map_plate_status, map_plate_type, plan_group_tree,
    plan_loans,
)

from cellar.domain.inventory.enums import LoanItemStatus, PlateStatus, PlateType


def _acct(uin: int, netid: str, email: str | None, alt: str | None = None) -> LegacyAccount:
    return LegacyAccount(uin=uin, netid=netid, email=email, alt_email=alt,
                         first_name="F", last_name="L")


def test_build_account_email_map_uses_email_and_skips_placeholders():
    accounts = [
        _acct(124007171, "sid", "sid@tamu.edu"),
        _acct(999, "AUTO_RAN999", "AUTO_RAN999"),   # placeholder → skip
        _acct(1000, "bob", None, alt="bob@x.org"),   # null email → fall back to alt_email
        _acct(1001, "nul", None),                    # no email at all → absent
    ]
    m = build_account_email_map(accounts)
    assert m == {124007171: "sid@tamu.edu", 1000: "bob@x.org"}


@pytest.mark.parametrize("role,expected", [
    ("MASTER", PlateType.MOTHER), ("SCREENING", PlateType.ASSAY),
    ("HIT_COLLECTION", PlateType.CHERRY_PICK), ("VENDOR", PlateType.COMPOUND_STORAGE),
])
def test_map_plate_type(role, expected):
    assert map_plate_type(role) == expected


def test_map_plate_type_unknown_raises():
    with pytest.raises(ValueError):
        map_plate_type("MASTER_TWIN")   # a set_type, never a plate_role


@pytest.mark.parametrize("status,expected_status,expected_tags", [
    ("Active", PlateStatus.STORED, []),
    ("AVAIL", PlateStatus.STORED, []),
    ("Inactive", PlateStatus.DEPLETED, ["legacy:inactive"]),
])
def test_map_plate_status(status, expected_status, expected_tags):
    assert map_plate_status(status) == (expected_status, expected_tags)


def test_map_plate_status_unknown_raises():
    with pytest.raises(ValueError):
        map_plate_status("Frozen")


def test_map_plate_status_returns_a_fresh_tag_list_each_call():
    first = map_plate_status("Inactive")[1]
    first.append("mutated")
    assert map_plate_status("Inactive")[1] == ["legacy:inactive"]


@pytest.mark.parametrize("p,expected", [
    ("COUT_REQ", LoanItemStatus.REQUESTED), ("ASSIGNED", LoanItemStatus.CHECKED_OUT),
    ("CIN_REQ", LoanItemStatus.RETURN_PENDING),
    ("COUT_WSCAN", LoanItemStatus.APPROVED),
    ("CIN_WSCAN", LoanItemStatus.RETURN_PENDING),
])
def test_map_loan_item_status(p, expected):
    assert map_loan_item_status(p) == expected


def test_map_loan_item_status_unknown_raises():
    with pytest.raises(ValueError):
        map_loan_item_status("BOGUS")


def test_due_date_is_last_activity_plus_14_days():
    assert due_date_from(datetime(2024, 1, 4, 11, 15)) == date(2024, 1, 18)


def test_compose_set_description_includes_state_scientist_conditions():
    s = LegacySet(set_id=1, set_type="SCREENING", set_name="S", set_state="Solubilized",
                  scientist=42, generating_conditions="DMSO 10mM", library_id=None)
    out = compose_set_description(s, {42: "Ann Lee"})
    assert "Solubilized" in out and "Ann Lee" in out and "DMSO 10mM" in out


def test_plan_group_tree_roots_by_library_and_nests_sets():
    legacy = LegacyData(
        libraries=[LegacyLibrary(10, "Lib A", "SacchettiniLibrary")],
        sets=[
            LegacySet(1, "MASTER_TWIN", "Parent Set", "Dry", None, None, 10),
            LegacySet(2, "SCREENING", "Child Set", "Solubilized", None, None, 10),
            LegacySet(3, "VENDOR", "Orphan Set", None, None, None, None),  # no library
        ],
        set_parents=[LegacySetParent(set_id=2, parent_id=1)],  # set2 child of set1
    )
    specs = plan_group_tree(legacy, {})
    by_key = {g.key: g for g in specs}
    assert by_key["lib:10"].parent_key is None and by_key["lib:10"].name == "Lib A"
    assert by_key["set:1"].parent_key == "lib:10"       # top-level set → library root
    assert by_key["set:2"].parent_key == "set:1"        # nested via SET_PARENT
    assert by_key["set:3"].parent_key is None           # orphan set → its own root
    # parents precede children
    order = [g.key for g in specs]
    assert order.index("lib:10") < order.index("set:1") < order.index("set:2")


def test_plan_loans_resolves_requester_maps_states_and_reports_unresolved():
    import uuid as _uuid
    p_ok = _uuid.uuid4()
    legacy = LegacyData(
        transactions=[
            LegacyTransaction(1, "OPEN", 42, datetime(2024, 1, 4)),
            LegacyTransaction(2, "OPEN", 77, datetime(2024, 2, 1)),  # requester has no email
        ],
        transaction_plates=[
            LegacyTransactionPlate(plate_id=10, p_status="ASSIGNED", transaction_id=1),
            LegacyTransactionPlate(plate_id=11, p_status="COUT_REQ", transaction_id=1),
            LegacyTransactionPlate(plate_id=12, p_status="CIN_REQ", transaction_id=2),
        ],
    )
    matched = {10: p_ok, 11: _uuid.uuid4(), 12: _uuid.uuid4()}
    account_email = {42: "ann@x.org"}   # 77 absent
    user_map = {"ann@x.org": _uuid.uuid4()}
    specs, unresolved = plan_loans(legacy, matched, account_email, user_map)
    assert len(specs) == 1 and specs[0].transaction_id == 1
    assert specs[0].due_date.isoformat() == "2024-01-18"
    targets = {i.cellar_plate_id: i.target for i in specs[0].items}
    assert targets[p_ok] == LoanItemStatus.CHECKED_OUT
    assert list(targets.values()).count(LoanItemStatus.REQUESTED) == 1
    assert [u.transaction_id for u in unresolved] == [2]
