"""Unit tests for ResolvePositionLabels."""

from __future__ import annotations

import pytest

from cellar.application.screening.resolve_position_labels import (
    MAX_POSITION_LABELS,
    LabelMatch,
    ResolvePositionLabels,
    ResolvePositionLabelsQuery,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_resolve_layout_file import Harness, _batch, _molecule


async def resolve(h: Harness, *labels: str, auth: FakeAuth | None = None):  # type: ignore[no-untyped-def]
    uc = ResolvePositionLabels(
        uow=h.uow, run_repo=h.run_repo, molecule_repo=h.molecule_repo, batch_repo=h.batch_repo
    )
    query = ResolvePositionLabelsQuery(workspace_id=h.ws, run_id=h.run.id, labels=labels)
    return await uc(query, auth=auth or h.auth)


async def matches(h: Harness, *labels: str) -> tuple[LabelMatch, ...]:
    out = (await resolve(h, *labels)).unwrap()
    h.assert_nothing_written()
    return out


async def test_label_resolves_by_registration_number_then_by_identifier():
    by_reg, by_alias = _molecule("REG-0001", "A"), _molecule("REG-0002", "B")
    h = Harness(by_reg={"REG-0001": by_reg}, by_identifier={"SACC-0457698": by_alias})
    first, second = await matches(h, "REG-0001", "SACC-0457698")
    assert (first.label, second.label) == ("REG-0001", "SACC-0457698")
    assert first.compound is not None and second.compound is not None
    assert (
        first.compound.molecule_id,
        first.compound.molecule_name,
        first.compound.registration_number,
    ) == (by_reg.id, "A", "REG-0001")
    assert (second.compound.molecule_id, second.compound.registration_number) == (
        by_alias.id,
        "REG-0002",
    )
    h.molecule_repo.find_by_identifier.assert_awaited_once_with(h.ws, "SACC-0457698")


async def test_label_that_names_no_compound_comes_back_without_one():
    h = Harness()
    assert await matches(h, "DMSO", "160 CoA") == (
        LabelMatch("DMSO", None),
        LabelMatch("160 CoA", None),
    )


async def test_one_batch_is_filled_and_several_need_a_choice():
    m1, m2, m3 = _molecule("REG-0001"), _molecule("REG-0002"), _molecule("REG-0003")
    only = _batch(m1, "B-1")
    h = Harness(
        by_reg={"REG-0001": m1, "REG-0002": m2, "REG-0003": m3},
        batches=[only, _batch(m2, "B-2"), _batch(m2, "B-3")],
    )
    one, many, none = (m.compound for m in await matches(h, "REG-0001", "REG-0002", "REG-0003"))
    assert one is not None and many is not None and none is not None
    assert (one.batch_id, one.batch_number, one.needs_batch_choice) == (only.id, "B-1", False)
    assert (many.batch_id, many.batch_number, many.needs_batch_choice) == (None, None, True)
    assert (none.batch_id, none.needs_batch_choice) == (None, False)


async def test_a_label_is_never_read_as_a_batch():
    molecule = _molecule("REG-0001")
    h = Harness(by_reg={"REG-0001": molecule}, batches=[_batch(molecule, "B-1")])
    assert await matches(h, "B-1") == (LabelMatch("B-1", None),)
    h.batch_repo.find_by_batch_number.assert_not_awaited()


async def test_repeated_and_padded_labels_answer_once_and_blank_ones_not_at_all():
    molecule = _molecule("REG-0001")
    h = Harness(by_reg={"REG-0001": molecule})
    out = await matches(h, "REG-0001", " REG-0001 ", "", "   ", "DMSO", "REG-0001", "DMSO")
    assert [m.label for m in out] == ["REG-0001", "DMSO"]
    assert h.molecule_repo.find_by_registration_number.await_count == 2


async def test_more_labels_than_the_cap_are_refused_before_any_lookup():
    h = Harness()
    at_cap = await resolve(h, *(f"L{n}" for n in range(MAX_POSITION_LABELS)))
    assert len(at_cap.unwrap()) == MAX_POSITION_LABELS == 500
    h.run_repo.find_by_id_in_workspace.reset_mock()
    failure = (await resolve(h, *(["DMSO"] * (MAX_POSITION_LABELS + 1)))).failure()
    assert isinstance(failure, ValidationError)
    assert "500" in str(failure)
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_run_not_found():
    h = Harness(run_missing=True)
    assert isinstance((await resolve(h, "REG-0001")).failure(), NotFoundError)
    h.run_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.id)
    h.molecule_repo.find_by_registration_number.assert_not_awaited()


async def test_viewer_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await resolve(h, "REG-0001", auth=FakeAuth(role="viewer", workspace_id=h.ws))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await resolve(h, "REG-0001", auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
