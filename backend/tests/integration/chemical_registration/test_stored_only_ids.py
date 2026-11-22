"""Deciding vs stored-only IDs (CDD mapper spec 2026-11-18 §3a), real DB.

A stored-only ID (``"decides": False``) never matches a compound or batch and never
conflicts: it is stored when no other compound/batch holds the text, otherwise
skipped with a warning. Each scenario runs through both pipelines (``run_rows``).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from temporalio.converter import DataConverter

from cellar.infrastructure.temporal.activities.dtos import ChunkInput, ChunkItem
from tests.integration.chemical_registration import test_row_batch as rb
from tests.integration.chemical_registration.test_row_batch import Run, Ws

# The phase 1 fixtures: a fresh workspace, and each scenario run by both pipelines.
ws = rb.ws
run_rows = rb.run_rows


def cdd_row(
    name: str | None,
    smiles: str | None = None,
    *,
    ids: Sequence[tuple[str, str]] = (),
    batch: Sequence[tuple[str, str]] = (),
    stored_ids: Sequence[tuple[str, str]] = (),
    stored_batch: Sequence[tuple[str, str]] = (),
    **fields: object,
) -> dict:
    """``rb.row`` plus stored-only compound/batch IDs, (value, Source) pairs."""
    r = rb.row(name, smiles, ids=ids, batch=batch, **fields)
    r["external_ids"] += [
        {"identifier": i, "identifier_type": "custom", "source": s, "decides": False}
        for i, s in stored_ids
    ]
    r["batch_ids"] += [{"identifier": i, "source": s, "decides": False} for i, s in stored_batch]
    return r


async def _reg(session_factory, molecule_id: uuid.UUID) -> str:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        return (
            await s.execute(
                sa.text("SELECT registration_number FROM molecules WHERE id = :m"),
                {"m": molecule_id},
            )
        ).scalar_one()


def _compound_warning(value: str, holder: str, this: str) -> str:
    return f"'{value}' is already an ID of {holder}; not stored on {this}"


def _batch_warning(value: str, holder: str, this: str) -> str:
    return f"'{value}' is already an ID of batch {holder}; not stored on {this}"


async def test_stored_only_compound_id_held_elsewhere_is_skipped_not_conflict(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    """Review Focus 1: an Alternate Name equal to another compound's synonym."""
    (holder,) = await run_rows([rb.row("HOLDER-1", "CCCCCCCCCCN", ids=[("CPD000136367", "Syn")])])

    (out,) = await run_rows(
        [
            cdd_row(
                "SACC-RF1",
                "CCCCCCCCCCCN",
                stored_ids=[
                    ("CPD000136367", "Alternate Names"),
                    ("ALT-FREE-1", "Alternate Names"),
                ],
            )
        ]
    )

    assert out.error is None
    assert out.molecule_id not in (None, holder.molecule_id)
    ids = await rb._compound_ids(session_factory, out.molecule_id)
    assert ("ALT-FREE-1", "custom", "Alternate Names") in ids
    assert all(i[0] != "CPD000136367" for i in ids)
    assert out.warnings == [
        _compound_warning(
            "CPD000136367",
            await _reg(session_factory, holder.molecule_id),
            await _reg(session_factory, out.molecule_id),
        )
    ]
    assert out.batch_id is not None  # the row imports in full


async def test_undisclosed_rows_sharing_a_stored_only_id_stay_two_compounds(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    """Review Focus 2: a shared label must not fold two undisclosed compounds into one."""
    label = ("Benzimidazole series", "Alternate Names")
    first, second = await run_rows(
        [cdd_row("SACC-U1", stored_ids=[label]), cdd_row("SACC-U2", stored_ids=[label])]
    )

    assert [first.error, second.error] == [None, None]
    mols = await rb._molecules(session_factory, ws)
    assert sorted(name for _, name, _ in mols) == ["SACC-U1", "SACC-U2"]
    assert {status for _, _, status in mols} == {"undisclosed"}
    assert first.molecule_id != second.molecule_id
    assert first.warnings == []
    assert second.warnings == [
        _compound_warning(
            label[0],
            await _reg(session_factory, first.molecule_id),
            await _reg(session_factory, second.molecule_id),
        )
    ]


async def test_stored_only_batch_id_held_elsewhere_is_skipped_batch_still_created(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    (holder,) = await run_rows(
        [rb.row("BH-1", "CCCCCCCCCCO", batch=[("BH-1-001", "CDD batch ID"), ("LGCY-1", "Legacy")])]
    )

    (out,) = await run_rows(
        [
            cdd_row(
                "BH-2",
                "CCCCCCCCCCCO",
                batch=[("BH-2-001", "CDD batch ID")],
                stored_batch=[("LGCY-1", "Legacy"), ("LGCY-2", "Legacy")],
            )
        ]
    )

    assert out.error is None  # a deciding LGCY-1 would be "(another compound)"
    assert out.batch_id not in (None, holder.batch_id)
    batches = await rb._batches(session_factory, ws)
    assert batches[out.batch_id].real == {
        "BH-2-001": ("custom", "CDD batch ID"),
        "LGCY-2": ("custom", "Legacy"),
    }
    assert "LGCY-1" in batches[holder.batch_id].real
    assert out.warnings == [_batch_warning("LGCY-1", holder.batch_number, out.batch_number)]


async def test_deciding_ids_still_match_as_in_phase_1(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    """Deciding IDs find the compound and batch; free stored-only IDs fill them in;
    a stored-only ID alone never finds a batch."""
    numeric = {"identifier": "13250", "source": "CDD import", "identifier_type": "cdd_batch_id"}
    first_row = rb.row("FILL-1", "CCCCCCCCCCCCO", batch=[("FILL-1-001", "CDD batch ID")])
    first_row["batch_ids"].append(numeric)
    (first,) = await run_rows([first_row])

    again, other_batch = await run_rows(
        [
            cdd_row(
                "FILL-1",
                "CCCCCCCCCCCCO",
                batch=[("FILL-1-001", "CDD batch ID")],
                stored_ids=[("ALT-9", "Alternate Names")],
                stored_batch=[("LGCY-9", "Legacy")],
            ),
            cdd_row(
                "FILL-1",
                "CCCCCCCCCCCCO",
                batch=[("FILL-1-002", "CDD batch ID")],
                stored_batch=[("LGCY-9", "Legacy")],
            ),
        ]
    )

    assert (again.error, again.warnings) == (None, [])
    assert (again.molecule_id, again.batch_id) == (first.molecule_id, first.batch_id)
    assert ("ALT-9", "custom", "Alternate Names") in await rb._compound_ids(
        session_factory, first.molecule_id
    )
    batches = await rb._batches(session_factory, ws)
    assert batches[first.batch_id].real == {
        "FILL-1-001": ("custom", "CDD batch ID"),
        "13250": ("cdd_batch_id", "CDD import"),
        "LGCY-9": ("custom", "Legacy"),
    }
    # LGCY-9 is on FILL-1-001's batch; it does not pull the 002 row onto it.
    assert other_batch.error is None
    assert other_batch.batch_id not in (None, first.batch_id)
    assert other_batch.warnings == [
        _batch_warning("LGCY-9", first.batch_number, other_batch.batch_number)
    ]
    assert len(await rb._molecules(session_factory, ws)) == 1


def test_chunk_item_with_decides_survives_temporal_serialization() -> None:
    """The worker receives ChunkInput through Temporal's JSON converter, which
    rejects a bool where the type hint says str."""
    row = cdd_row("SER-1", stored_ids=[("A", "S")], stored_batch=[("B", "S")])
    item = ChunkItem(row_index=0, **row)
    chunk = ChunkInput(workspace_id="w", submitted_by="u", items=[item])
    conv = DataConverter.default.payload_converter

    (back,) = conv.from_payloads(conv.to_payloads([chunk]), [ChunkInput])

    assert back.items[0].external_ids[-1]["decides"] is False
    assert back.items[0].batch_ids[-1]["decides"] is False


async def test_stored_only_compound_id_matches_holders_case_insensitively(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    """Compound lookup by identifier ignores case, so a case variant on a second
    compound would make it ambiguous; the compound's own IDs never count."""
    (a,) = await run_rows([rb.row("CMP-A", "CCCCCCCCCCCCCN", ids=[("A-SYN-1", "Syn")])])
    (b,) = await run_rows([rb.row("CMP-B", "CCCCCCCCCCCCCCN", ids=[("Rifampicin", "Syn")])])

    (again,) = await run_rows(
        [
            cdd_row(
                "CMP-A",
                "CCCCCCCCCCCCCN",
                stored_ids=[("rifampicin", "Alternate Names"), ("a-syn-1", "Alternate Names")],
            )
        ]
    )

    assert again.error is None and again.molecule_id == a.molecule_id
    assert again.warnings == [
        _compound_warning(
            "rifampicin",
            await _reg(session_factory, b.molecule_id),
            await _reg(session_factory, a.molecule_id),
        )
    ]
    ids = {i[0] for i in await rb._compound_ids(session_factory, a.molecule_id)}
    assert "rifampicin" not in ids
    assert "a-syn-1" not in ids  # A-SYN-1 is already A's own; no second copy
