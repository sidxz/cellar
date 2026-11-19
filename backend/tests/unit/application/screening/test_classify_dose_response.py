"""ClassifyDoseResponseCurve: a scientist sets a class by hand, recorded in the audit trail."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.classify_dose_response import (
    ClassifyDoseResponseCurve,
    ClassifyDoseResponseCurveCommand,
)
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass, CurveType
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()
USER = uuid.uuid4()


class _Uow:
    def __init__(self) -> None:
        self.session = object()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def commit(self):
        self.committed = True
        return []


def _curve(curve_class: CurveClass = CurveClass.PARTIAL) -> DoseResponseCurve:
    return DoseResponseCurve(
        workspace_id=WS,
        molecule_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        curve_type=CurveType.EC50,
        fitted_value=6.8,
        hill_slope=1.0,
        top=92.5,
        bottom=85.6,
        r_squared=0.69,
        num_points=20,
        curve_class=curve_class,
        raw_data=[],
    )


def _use_case(curve: DoseResponseCurve | None):
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=curve)
    repo.save = AsyncMock()
    audit = AsyncMock()
    uow = _Uow()
    return ClassifyDoseResponseCurve(uow=uow, curve_repo=repo, audit=audit), repo, audit, uow


def _command(curve_id: uuid.UUID, curve_class: str) -> ClassifyDoseResponseCurveCommand:
    return ClassifyDoseResponseCurveCommand(
        workspace_id=WS, curve_id=curve_id, curve_class=curve_class
    )


_EDITOR = FakeAuth(role="editor", workspace_id=WS, user_id=USER)


@pytest.mark.asyncio
@pytest.mark.parametrize("new_class", list(CurveClass))
async def test_a_class_set_by_hand_is_saved_and_audited(new_class: CurveClass):
    """Active at all doses is set and recorded like every other class."""
    curve = _curve(CurveClass.PARTIAL)
    uc, repo, audit, uow = _use_case(curve)

    result = await uc(_command(curve.id, new_class.value), auth=_EDITOR)

    assert isinstance(result, Success)
    assert result.unwrap().curve_class == new_class
    repo.save.assert_awaited_once_with(curve)
    assert uow.committed
    record = audit.record.await_args.kwargs
    assert (record["operation_type"], record["entity_type"], record["entity_id"]) == (
        OperationType.PROPERTY_EDIT,
        "DoseResponseCurve",
        curve.id,
    )
    assert (record["workspace_id"], record["user_id"], record["session"]) == (
        WS,
        USER,
        uow.session,
    )
    (entry,) = record["entries"]
    assert (entry.field_name, entry.action, entry.old_value, entry.new_value) == (
        "curve_class",
        AuditAction.UPDATE,
        "partial",
        new_class.value,
    )


@pytest.mark.asyncio
async def test_an_unknown_class_is_refused_and_nothing_is_recorded():
    curve = _curve()
    uc, repo, audit, _ = _use_case(curve)

    result = await uc(_command(curve.id, "potent"), auth=_EDITOR)

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)
    repo.save.assert_not_awaited()
    audit.record.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_missing_curve_is_not_found():
    uc, _, audit, _ = _use_case(None)

    result = await uc(_command(uuid.uuid4(), "active_all_doses"), auth=_EDITOR)

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
    audit.record.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_viewer_cannot_change_a_class():
    curve = _curve()
    uc, *_ = _use_case(curve)
    with pytest.raises(AuthorizationError):
        await uc(
            _command(curve.id, "active_all_doses"),
            auth=FakeAuth(role="viewer", workspace_id=WS, user_id=USER),
        )


@pytest.mark.asyncio
async def test_a_class_change_needs_someone_to_record():
    curve = _curve()
    uc, *_ = _use_case(curve)
    with pytest.raises(AuthorizationError):
        await uc(_command(curve.id, "active_all_doses"), auth=None)
