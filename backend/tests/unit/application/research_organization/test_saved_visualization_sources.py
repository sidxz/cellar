"""Saved view sources: checked strictly on save, resolved leniently on open (incl. compared
protocols)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from cellar.application.research_organization.saved_visualizations import (
    check_saved_source,
    resolve_saved_source,
)
from cellar.application.visualization.dataset_reader import RunInfo
from cellar.domain.shared.errors import NotFoundError

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
P, C1, C2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class _Reader:
    """Protocols and their run ids; anything else is unknown."""

    def __init__(self, protocols: dict[uuid.UUID, list[uuid.UUID]]) -> None:
        self._runs = {
            pid: [
                RunInfo(
                    rid, pid, date(2026, 11, 1), uuid.uuid4(), "approved", None, datetime.now(UTC)
                )
                for rid in rids
            ]
            for pid, rids in protocols.items()
        }

    async def runs_for_protocol(self, workspace_id, protocol_id):
        return self._runs.get(protocol_id)

    async def runs_by_ids(self, workspace_id, run_ids):
        return [r for runs in self._runs.values() for r in runs if r.id in run_ids]


def _source(*compare: dict) -> dict:
    return {"kind": "protocol", "protocol_id": str(P), "run_ids": None, "compare": list(compare)}


async def test_saving_names_every_compared_protocol():
    reader = _Reader({P: [], C1: [], C2: []})
    data = _source({"protocol_id": str(C1), "run_ids": None}, {"protocol_id": str(C2)})

    assert await check_saved_source(reader, WS, data, "compounds") == [P, C1, C2]


async def test_saving_with_an_unknown_compared_protocol_is_not_found():
    reader = _Reader({P: []})

    result = await check_saved_source(reader, WS, _source({"protocol_id": str(C1)}), "compounds")

    assert isinstance(result, NotFoundError)


async def test_a_deleted_compared_protocol_is_left_out_on_open():
    run = uuid.uuid4()
    reader = _Reader({P: [], C2: [run]})
    kept = {"protocol_id": str(C2), "run_ids": [str(run)]}

    source, lines = await resolve_saved_source(
        reader, WS, _source({"protocol_id": str(C1), "run_ids": None}, kept)
    )

    assert source == _source(kept)
    assert len(lines) == 1
    assert lines[0].startswith("1 ")


async def test_a_source_without_compare_opens_unchanged():
    reader = _Reader({P: []})
    data = {"kind": "protocol", "protocol_id": str(P), "run_ids": None}

    assert await resolve_saved_source(reader, WS, data) == (data, [])
