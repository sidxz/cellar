from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from scripts.migrate_legacy_plate_tracker import (
    LegacyAccount,
    LegacyActivity,
    LegacyData,
    LegacyLibrary,
    LegacyLocation,
    LegacyPlate,
    LegacySet,
    LegacySetParent,
    LegacyTransaction,
    LegacyTransactionPlate,
    LocationSpec,
    build_account_email_map,
    compose_set_description,
    due_date_from,
    format_for_plate,
    full_name,
    map_loan_item_status,
    map_plate_status,
    map_plate_type,
    open_transactions,
    parse_system_line,
    plan_closed_loans,
    plan_comments,
    plan_group_tree,
    plan_loans,
    plan_locations,
)

from cellar.domain.inventory.enums import CommentTarget, LoanItemStatus, PlateStatus, PlateType
from cellar.domain.shared.enums import PlateFormat


def _acct(uin: int, netid: str, email: str | None, alt: str | None = None) -> LegacyAccount:
    return LegacyAccount(uin=uin, netid=netid, email=email, alt_email=alt,
                         first_name=None, last_name=None)


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
    assert "Solubilized" not in out and "Ann Lee" not in out
    assert "DMSO 10mM" in out


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


def test_format_for_plate_prefers_plate_then_set_then_96() -> None:
    formats = {2501: -1, 2507: 96, 2509: 384}
    p384 = LegacyPlate(1, None, "000001", "P1", "Active", "MASTER", 10, 2509)
    pinv = LegacyPlate(2, None, "000002", "P2", "Active", "MASTER", 10, 2501)
    pnone = LegacyPlate(3, None, "000003", "P3", "Active", "MASTER", 10, None)
    s384 = LegacySet(1, "MASTER_TWIN", "S", "Dry", None, None, 10, 2509)
    assert format_for_plate(p384, None, formats) is PlateFormat.F384
    assert format_for_plate(pinv, s384, formats) is PlateFormat.F384
    assert format_for_plate(pinv, None, formats) is PlateFormat.F96
    assert format_for_plate(pnone, None, formats) is PlateFormat.F96


def test_full_name_falls_back_to_netid_then_uin() -> None:
    assert full_name(_acct(1, "jdoe", "j@x.org")) == "jdoe"
    assert full_name(LegacyAccount(2, "", None, None, " Jane ", "Doe")) == "Jane Doe"
    assert full_name(LegacyAccount(3, "", None, None, None, None)) == "UIN 3"


def test_plan_locations_skips_unknown_and_dedupes() -> None:
    legacy = LegacyData(
        locations=[
            LegacyLocation(100001, "1148", "4"),
            LegacyLocation(100002, "1148", "4"),
            LegacyLocation(100003, "UNKNOWN", "UNKNOWN"),
            LegacyLocation(100004, "1203", "3"),
        ]
    )
    specs, alias = plan_locations(legacy)
    assert [(s.room_no, s.freezer) for s in specs] == [("1148", "4"), ("1203", "3")]
    assert alias == {100002: 100001}
    assert specs[0] == LocationSpec(100001, "1148", "4")


def test_open_transactions_filters_closed() -> None:
    now = datetime(2026, 8, 1)
    legacy = LegacyData(
        transactions=[
            LegacyTransaction(5001, "OPEN", 1, now),
            LegacyTransaction(5002, "CLOSED", 1, now),
        ]
    )
    assert [t.transaction_id for t in open_transactions(legacy)] == [5001]


def test_compose_set_description_no_longer_folds_state_and_scientist() -> None:
    s = LegacySet(
        1, "VENDOR", "sac1-vendor-X", "Solubilized", 7, "Compounds selected by T.", 10,
        2507, 100001, 0.0, 10.0, 17606, "file.sdf", "Purchased from Asinex",
    )
    desc = compose_set_description(s, {7: "Jane Doe"})
    assert desc is not None
    assert "Solubilized" not in desc and "Jane" not in desc
    assert "Compounds selected by T." in desc
    assert "file.sdf" in desc and "Purchased from Asinex" in desc


def test_plan_group_tree_carries_metadata() -> None:
    legacy = LegacyData(
        libraries=[LegacyLibrary(10, "Lib A", "SacchettiniLibrary")],
        sets=[
            LegacySet(
                1, "VENDOR", "sac1-vendor-X", "Solubilized", 7, None, 10,
                2507, 100001, 55.0, 10.0, 17606, None, None,
            )
        ],
    )
    specs = plan_group_tree(legacy, {7: "Jane Doe"})
    vendor = next(g for g in specs if g.key == "set:1")
    assert (vendor.state, vendor.location_id, vendor.initial_volume_ul) == (
        "Solubilized", 100001, 55.0,
    )
    assert (vendor.initial_concentration_mm, vendor.compound_count, vendor.scientist) == (
        10.0, 17606, "Jane Doe",
    )


SYS = "(System Generated Comment) "


@pytest.mark.parametrize(
    "line, kind, name, status",
    [
        (SYS + "Plate AbbVie_QD-1-4084 has been approved. Please scan them out from vault",
         "plate", "AbbVie_QD-1-4084", LoanItemStatus.APPROVED),
        (SYS + "Plate X has been approved for check-in. Please scan them back to vault",
         "plate", "X", LoanItemStatus.RETURN_PENDING),
        (SYS + "Plate X Y has been scanned out from vault",
         "plate", "X Y", LoanItemStatus.CHECKED_OUT),
        (SYS + "Plate X has been scanned back in to the vault",
         "plate", "X", LoanItemStatus.RETURNED),
        (SYS + "Plate X has been denied.", "plate", "X", LoanItemStatus.DENIED),
        (SYS + "Status for TBAC-1 has been Overridden to 'Assigned' by Admin manpal",
         "plate", "TBAC-1", LoanItemStatus.CHECKED_OUT),
        (SYS + "Transaction closed, all plates are checked back in", "close", None, None),
        (SYS + "Transaction closed, status overridden by Admin dwight.baker", "close", None, None),
        (SYS + "All transaction's plates are denied. Transaction Closed", "close", None, None),
    ],
)
def test_parse_system_line(line, kind, name, status) -> None:
    parsed = parse_system_line(line)
    assert parsed is not None
    assert (parsed.kind, parsed.plate_name, parsed.status) == (kind, name, status)


def test_parse_system_line_rejects_human_and_unknown() -> None:
    assert parse_system_line("By Friday") is None
    assert parse_system_line(SYS + "Something new we never saw") is None


def _closed_legacy() -> LegacyData:
    t0 = datetime(2026, 5, 1, 9, 0)
    return LegacyData(
        plates=[LegacyPlate(1, None, "000001", "P1", "Active", "MASTER", 10),
                LegacyPlate(2, None, "000002", "P2", "Active", "MASTER", 10)],
        transactions=[LegacyTransaction(5001, "CLOSED", 7, t0)],
        accounts=[_acct(7, "jdoe", "j@tamu.edu")],
        activities=[
            LegacyActivity(1, "T_REQ_CMT", 5001, None, None,
                           SYS + "Plate P1 has been approved. Please scan them out from vault",
                           7, datetime(2026, 5, 1, 10, 0)),
            LegacyActivity(2, "T_REQ_CMT", 5001, None, None,
                           SYS + "Plate P2 has been denied.", 7, datetime(2026, 5, 1, 10, 1)),
            LegacyActivity(3, "T_CMT", 5001, None, None,
                           SYS + "Plate P1 has been scanned out from vault",
                           7, datetime(2026, 5, 2, 8, 0)),
            LegacyActivity(4, "T_CMT", 5001, None, None,
                           SYS + "Plate P1 has been scanned back in to the vault",
                           7, datetime(2026, 5, 9, 8, 0)),
            LegacyActivity(5, "T_CMT", 5001, None, None,
                           SYS + "Transaction closed, all plates are checked back in",
                           7, datetime(2026, 5, 9, 8, 1)),
            LegacyActivity(6, "T_CMT", 5001, None, None,
                           "1 ul used for nsp15 screening", 7, datetime(2026, 5, 3, 8, 0)),
            LegacyActivity(7, "SET_CMT", 5001, None, 1,
                           "[SET] sac1-vendor-X : 0.5 uL taken", 7, datetime(2026, 5, 9, 7, 0)),
            LegacyActivity(8, "PLATE_CMT", 5001, 1, 1,
                           "[PLATE] P1 : removed 12.5 uL", 7, datetime(2026, 5, 9, 7, 1)),
            LegacyActivity(9, "T_CMT", 5001, None, None,
                           SYS + "Weird unknown line", 7, datetime(2026, 5, 9, 9, 0)),
        ],
    )


def test_plan_closed_loans_reconstructs_items_and_timestamps() -> None:
    legacy = _closed_legacy()
    p1, p2, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    specs, unparsed = plan_closed_loans(
        legacy, {"P1": p1, "P2": p2}, {7: "j@tamu.edu"}, {"j@tamu.edu": user}, actor,
        {7: "Jane Doe"},
    )
    assert [u.act_id for u in unparsed] == [9]
    (spec,) = specs
    assert spec.transaction_id == 5001 and spec.requester_user_id == user
    assert spec.requester_name == "Jane Doe"
    assert spec.created_at == datetime(2026, 5, 1, 9, 0)
    assert spec.closed_at == datetime(2026, 5, 9, 8, 1)
    assert spec.due_date == datetime(2026, 5, 15).date()
    by_plate = {i.cellar_plate_id: i for i in spec.items}
    assert by_plate[p1].status is LoanItemStatus.RETURNED
    assert by_plate[p1].status_changed_at == datetime(2026, 5, 9, 8, 0)
    assert by_plate[p2].status is LoanItemStatus.DENIED
    assert by_plate[p2].status_changed_at == datetime(2026, 5, 1, 10, 1)


def test_plan_closed_loans_unmapped_requester_falls_back_to_actor() -> None:
    legacy = _closed_legacy()
    actor = uuid.uuid4()
    specs, _ = plan_closed_loans(
        legacy, {"P1": uuid.uuid4(), "P2": uuid.uuid4()}, {7: "j@tamu.edu"}, {}, actor,
        {7: "Jane Doe"},
    )
    assert specs[0].requester_user_id == actor and specs[0].requester_name == "Jane Doe"


def test_plan_comments_targets_and_prefix_stripping() -> None:
    legacy = _closed_legacy()
    loan, group, p1, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    specs = plan_comments(
        legacy, txn_loan_ids={5001: loan}, set_group_ids={1: group}, plate_ids={1: p1},
        account_email={7: "j@tamu.edu"}, user_map={"j@tamu.edu": user},
        account_names={7: "Jane Doe"},
    )
    assert len(specs) == 3  # the 6 system lines are not comments
    by_target = {(s.target_type, s.target_id): s for s in specs}
    loan_c = by_target[(CommentTarget.PLATE_LOAN, loan)]
    assert loan_c.body == "1 ul used for nsp15 screening"
    assert loan_c.loan_id == loan and loan_c.author_id == user
    assert by_target[(CommentTarget.PLATE_GROUP, group)].body == "0.5 uL taken"
    plate_c = by_target[(CommentTarget.PLATE, p1)]
    assert plate_c.body == "removed 12.5 uL" and plate_c.loan_id == loan
    assert plate_c.author_name == "Jane Doe"
    assert plate_c.created_at == datetime(2026, 5, 9, 7, 1)
