from __future__ import annotations

from datetime import date, datetime

import pytest

from cellar.domain.inventory.enums import LoanItemStatus, PlateStatus, PlateType
from scripts.migrate_legacy_plate_tracker import (
    LegacyAccount, LegacySet, build_account_email_map, compose_set_description,
    due_date_from, map_loan_item_status, map_plate_status, map_plate_type,
)


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
