"""Manual QC verdict on a campaign cell: apply rule and carry rule."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
    QcApplyOutcome,
)
from cellar.domain.research_organization.enums import QcVerdict, ValueQualifier
from cellar.domain.shared.errors import ValidationError

R1, R2 = uuid.uuid4(), uuid.uuid4()
U1, U2 = uuid.uuid4(), uuid.uuid4()
T1 = datetime(2026, 11, 1, tzinfo=UTC)
T2 = datetime(2026, 11, 2, tzinfo=UTC)
V, F = QcVerdict.VERIFIED, QcVerdict.FAILED


def _cell(**overrides) -> CampaignMeasurement:
    kw = {
        "result_id": uuid.uuid4(),
        "channel_id": uuid.uuid4(),
        "value": 1.0,
        "value_qualifier": ValueQualifier.EQ,
        "unit": "uM",
        "protocol_name_snapshot": "P",
        "protocol_version_snapshot": 1,
        "contributing_run_ids": [R1],
    }
    kw.update(overrides)
    return CampaignMeasurement(**kw)


def _nd(**overrides) -> CampaignMeasurement:
    return _cell(
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="",
        source_curve_id=uuid.uuid4(),
        **overrides,
    )


def _apply(cell, verdict, *, by=U1, at=T1, note=None, overwrite=False):
    return cell.apply_qc_verdict(verdict, by=by, at=at, note=note, overwrite=overwrite)


def test_holds_result():
    for q in (ValueQualifier.EQ, ValueQualifier.LT, ValueQualifier.GT):
        assert _cell(value_qualifier=q).holds_result
    assert _nd().holds_result
    assert _cell(
        value=None, value_qualifier=ValueQualifier.ND, unit="", curve_snapshot={"top": 1}
    ).holds_result
    assert not _cell(value=None, value_qualifier=ValueQualifier.ND, unit="").holds_result
    assert not _cell(value=None, value_qualifier=ValueQualifier.EXCLUDED, unit="").holds_result


def test_verify_not_tested_cell_changes_and_stamps():
    c = _cell()
    assert _apply(c, V, note="looked") is QcApplyOutcome.CHANGED
    assert (c.qc_verdict, c.qc_verdict_by, c.qc_verdict_at, c.qc_verdict_note) == (
        V,
        U1,
        T1,
        "looked",
    )


def test_same_verdict_is_unchanged_and_keeps_stamp():
    c = _cell()
    _apply(c, V)
    assert _apply(c, V, by=U2, at=T2) is QcApplyOutcome.UNCHANGED
    assert (c.qc_verdict_by, c.qc_verdict_at) == (U1, T1)


def test_same_verdict_with_overwrite_and_new_note_restamps():
    c = _cell()
    _apply(c, V)
    assert _apply(c, V, by=U2, at=T2, note="n", overwrite=True) is QcApplyOutcome.CHANGED
    assert (c.qc_verdict_by, c.qc_verdict_at, c.qc_verdict_note) == (U2, T2, "n")


def test_other_verdict_without_overwrite_is_kept():
    c = _cell()
    _apply(c, F)
    assert _apply(c, V, by=U2, at=T2) is QcApplyOutcome.KEPT
    assert c.qc_verdict == F


def test_other_verdict_with_overwrite_changes():
    c = _cell()
    _apply(c, F)
    assert _apply(c, V, by=U2, at=T2, overwrite=True) is QcApplyOutcome.CHANGED
    assert (c.qc_verdict, c.qc_verdict_by) == (V, U2)


def test_clear_ignores_overwrite():
    c = _cell()
    _apply(c, V, note="x")
    assert _apply(c, None) is QcApplyOutcome.CHANGED
    assert (c.qc_verdict, c.qc_verdict_by, c.qc_verdict_at, c.qc_verdict_note) == (
        None,
        None,
        None,
        None,
    )
    assert _apply(_cell(), None) is QcApplyOutcome.UNCHANGED


def test_no_result_cell_is_never_marked():
    c = _cell(value=None, value_qualifier=ValueQualifier.ND, unit="")
    assert _apply(c, V) is QcApplyOutcome.NO_RESULT
    assert _apply(c, None) is QcApplyOutcome.NO_RESULT
    assert c.qc_verdict is None


def test_note_with_clear_is_rejected():
    with pytest.raises(ValidationError):
        _apply(_cell(), None, note="why")


def test_note_over_limit_is_rejected():
    with pytest.raises(ValidationError):
        _apply(_cell(), V, note="x" * 2001)
    c = _cell()
    _apply(c, V, note="x" * 2000)
    assert len(c.qc_verdict_note) == 2000


def test_blank_note_is_none():
    c = _cell()
    _apply(c, V, note="   ")
    assert c.qc_verdict_note is None


def _verified(cell):
    _apply(cell, V, note="ok")
    return cell


def test_carry_keeps_on_same_reading():
    old = _verified(_cell(test_concentration_value=10.0, test_concentration_unit="uM"))
    new = _cell(
        value=1.0 + 1e-12,
        unit="µM",
        contributing_run_ids=[R2, R1],
        test_concentration_value=10.0,
        test_concentration_unit="uM",
    )
    old.contributing_run_ids = [R1, R2]
    assert new.carry_qc_verdict_from(old) is True
    assert (new.qc_verdict, new.qc_verdict_by, new.qc_verdict_at, new.qc_verdict_note) == (
        V,
        U1,
        T1,
        "ok",
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (_cell(), _cell(value=1.1)),
        (_cell(), _cell(value_qualifier=ValueQualifier.GT)),
        (_cell(), _cell(unit="nM")),
        (_cell(), _cell(contributing_run_ids=[R1, R2])),
        (_nd(test_concentration_value=10.0), _nd(test_concentration_value=20.0)),
        (_cell(), _cell(concentration_series=True)),
    ],
    ids=["value", "qualifier", "unit", "runs", "test_concentration", "series"],
)
def test_carry_clears_on(old, new):
    _verified(old)
    old.contributing_run_ids = [R1]
    assert new.carry_qc_verdict_from(old) is False
    assert new.qc_verdict is None


def test_carry_on_nd_ignores_unit():
    old = _verified(_nd())
    old.unit = "-"
    new = _nd()
    new.unit = "uM"
    new.contributing_run_ids = old.contributing_run_ids = [R1]
    assert new.carry_qc_verdict_from(old) is True


def test_carry_from_not_tested_is_false():
    assert _cell().carry_qc_verdict_from(_cell()) is False
