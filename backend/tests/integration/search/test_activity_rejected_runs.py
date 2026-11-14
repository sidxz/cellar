"""Rejected runs never make a compound match a search."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

JAN, FEB, APR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 4, 1)


async def _matches(session_factory, workspace_id, criterion) -> set[uuid.UUID]:
    reader = SQLAlchemyMoleculeReader(session_factory)
    query = {"logic": "and", "criteria": [criterion]}
    found = {m.id for m in await reader.search_by_query(workspace_id, query)}
    assert await reader.count_by_query(workspace_id, query) == len(found)
    return found


@pytest.fixture
async def world(uow, workspace_id):
    """Protocol P: run OK (Jan) and REJECTED (Apr, newest). Compound `kept` is
    measured in both, `rejected_only` only in the rejected run."""
    async with uow:
        s = uow.session
        o = await seed.org(s, workspace_id)
        kept = await seed.molecule(s, workspace_id, o, "kept", **seed.descriptors(300.0))
        rejected_only = await seed.molecule(s, workspace_id, o, "rej", **seed.descriptors(300.0))
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, unit="%")
        counter_p = await seed.protocol(s, workspace_id)
        dr = await seed.readout_def(s, p, data_type="dose_response")
        counter_dr = await seed.readout_def(s, counter_p, data_type="dose_response")
        ok = await seed.run(s, workspace_id, p, JAN)
        bad = await seed.run(s, workspace_id, p, APR, status="rejected")
        counter_run = await seed.run(s, workspace_id, counter_p, JAN)
        await seed.readout(s, workspace_id, ok, rd, kept, 80.0)
        await seed.readout(s, workspace_id, bad, rd, kept, 10.0)
        await seed.readout(s, workspace_id, bad, rd, rejected_only, 90.0)
        await seed.curve(s, workspace_id, p, bad, rejected_only, dr, fitted_value=0.01)
        await seed.curve(
            s, workspace_id, counter_p, counter_run, rejected_only, counter_dr, fitted_value=50.0
        )
        await uow.commit()
    return {
        "kept": kept,
        "rej": rejected_only,
        "p": p,
        "rd": rd,
        "dr": dr,
        "counter_dr": counter_dr,
    }


async def test_readout_where_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {
        "type": "activity",
        "protocol_id": str(world["p"]),
        "where": [
            {
                "source": "readout_data",
                "readout_definition_id": str(world["rd"]),
                "operator": "gt",
                "value": 50,
            }
        ],
    }
    assert await _matches(session_factory, workspace_id, criterion) == {world["kept"]}


async def test_presence_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {"type": "activity", "protocol_id": str(world["p"])}
    assert await _matches(session_factory, workspace_id, criterion) == {world["kept"]}


async def test_curve_where_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {
        "type": "activity",
        "protocol_id": str(world["p"]),
        "where": [
            {
                "source": "dr_curve",
                "readout_definition_id": str(world["dr"]),
                "operator": "lt",
                "value": 1,
            }
        ],
    }
    assert await _matches(session_factory, workspace_id, criterion) == set()


async def test_curve_class_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {
        "type": "activity",
        "protocol_id": str(world["p"]),
        "where": [
            {
                "source": "curve_class",
                "readout_definition_id": "",
                "operator": "eq",
                "curve_classes": ["full"],
            }
        ],
    }
    assert await _matches(session_factory, workspace_id, criterion) == set()


async def test_latest_run_skips_the_rejected_newest_run(session_factory, workspace_id, world):
    criterion = {
        "type": "activity",
        "protocol_id": str(world["p"]),
        "run_scope": {"mode": "latest"},
    }
    assert await _matches(session_factory, workspace_id, criterion) == {world["kept"]}


async def test_every_run_ignores_a_rejected_counterexample(session_factory, workspace_id, world):
    criterion = {
        "type": "activity",
        "protocol_id": str(world["p"]),
        "run_scope": {"mode": "all"},
        "where": [
            {
                "source": "readout_data",
                "readout_definition_id": str(world["rd"]),
                "operator": "gt",
                "value": 50,
            }
        ],
    }
    assert await _matches(session_factory, workspace_id, criterion) == {world["kept"]}


async def test_any_protocol_potency_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {
        "type": "activity",
        "protocol_id": None,
        "where": [
            {"source": "dr_curve", "readout_definition_id": "", "operator": "lt", "value": 1}
        ],
    }
    assert await _matches(session_factory, workspace_id, criterion) == set()


async def test_selectivity_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {
        "type": "selectivity",
        "target_readout_definition_id": str(world["dr"]),
        "counter_readout_definition_id": str(world["counter_dr"]),
        "ratio_operator": "gte",
        "ratio_value": 10,
    }
    assert await _matches(session_factory, workspace_id, criterion) == set()


async def test_run_date_ignores_rejected_runs(session_factory, workspace_id, world):
    criterion = {"type": "run_date", "date_from": "2026-03-01", "date_to": "2026-05-01"}
    assert await _matches(session_factory, workspace_id, criterion) == set()
