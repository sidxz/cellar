"""Tests for test helper utilities — verify they work before other tests use them."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from returns.result import Failure, Success

from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from tests.helpers.assertions import (
    assert_event_emitted,
    assert_result_err,
    assert_result_ok,
)


@dataclass(frozen=True, kw_only=True)
class FakeEvent(DomainEvent):
    molecule_name: str = "aspirin"


class TestAssertResultOk:
    def test_success(self) -> None:
        result = Success(42)
        assert assert_result_ok(result) == 42

    def test_failure_raises(self) -> None:
        result = Failure(NotFoundError("Molecule"))
        with pytest.raises(AssertionError, match="Expected Success"):
            assert_result_ok(result)


class TestAssertResultErr:
    def test_failure(self) -> None:
        result = Failure(NotFoundError("Molecule"))
        err = assert_result_err(result)
        assert isinstance(err, NotFoundError)

    def test_failure_with_type_check(self) -> None:
        result = Failure(NotFoundError("Molecule"))
        err = assert_result_err(result, NotFoundError)
        assert isinstance(err, NotFoundError)

    def test_failure_wrong_type(self) -> None:
        result = Failure(NotFoundError("Molecule"))
        with pytest.raises(AssertionError, match="Expected ValidationError"):
            assert_result_err(result, ValidationError)

    def test_success_raises(self) -> None:
        result = Success(42)
        with pytest.raises(AssertionError, match="Expected Failure"):
            assert_result_err(result)


class TestAssertEventEmitted:
    def test_event_found(self) -> None:
        events: list[DomainEvent] = [
            FakeEvent(aggregate_id=uuid.uuid4(), aggregate_type="molecule", workspace_id=uuid.uuid4())
        ]
        result = assert_event_emitted(events, FakeEvent)
        assert isinstance(result, FakeEvent)

    def test_event_not_found(self) -> None:
        events: list[DomainEvent] = []
        with pytest.raises(AssertionError, match="No FakeEvent"):
            assert_event_emitted(events, FakeEvent)

    def test_field_check_passes(self) -> None:
        events: list[DomainEvent] = [
            FakeEvent(
                aggregate_id=uuid.uuid4(),
                aggregate_type="molecule",
                workspace_id=uuid.uuid4(),
                molecule_name="caffeine",
            )
        ]
        result = assert_event_emitted(events, FakeEvent, molecule_name="caffeine")
        assert result.molecule_name == "caffeine"

    def test_field_check_fails(self) -> None:
        events: list[DomainEvent] = [
            FakeEvent(aggregate_id=uuid.uuid4(), aggregate_type="molecule", workspace_id=uuid.uuid4())
        ]
        with pytest.raises(AssertionError, match="molecule_name"):
            assert_event_emitted(events, FakeEvent, molecule_name="wrong")

