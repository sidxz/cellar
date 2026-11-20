"""CDD vault rows through the worker, real DB (CDD mapper spec 2026-11-18 §3, §3a, §3b, §4).

Each run goes the way an import does: the export split into chunks (``_split_export``,
which also finds the labels), a chunk mapped (``load_export_chunk``), then
registered (``process_chunk``). Fixtures are synthetic, shaped like the real export.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from temporalio.testing import ActivityEnvironment

from cellar.application.cdd_import.registration_mapping import default_cdd_registration_mapping
from cellar.application.chemical_registration.bulk_column_mapping import ColumnMapping
from cellar.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from cellar.domain.workspace_config.data_source import get_default_template
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities, _split_export
from cellar.infrastructure.temporal.activities.dtos import (
    ChunkInput,
    ChunkItem,
    ChunkItemResult,
    LoadExportChunkInput,
    PlateChunkOutput,
)
from cellar.infrastructure.temporal.activities.plate_registration import (
    PlateRegistrationActivities,
)
from cellar.infrastructure.temporal.activities.registration import RegistrationActivities
from cellar.infrastructure.temporal.task_queues import CHUNK_SIZE
from tests.integration.chemical_registration.conftest import _ensure_org
from tests.integration.chemical_registration.test_row_batch import (
    PROCESSOR,
    Ws,
    _batches,
    _compound_ids,
    _Dispatcher,
    _molecules,
    _run_m105,
    _run_worker,
    row,
)

MAPPING: list[dict[str, Any]] = [
    *default_cdd_registration_mapping(),
    {
        "header": "molecule_fields.Alternate Names",
        "target": "compound_id",
        "source": "Alternate Names",
        "separator": ";",
    },
    {
        "header": "batch.batch_fields.LGCY Batch Name",
        "target": "batch_id",
        "source": "CDD legacy batch ID",
        "separator": None,
    },
]
ENTITY_MAPPINGS = [em.to_dict() for em in get_default_template("cdd_vault")]

NAME, SMILES = "SACC-0436536", "CC(=O)Nc1ccc(O)cc1"
LGCY_1, LGCY_2 = "MSD-946760565-001K001", "MSD-946760565-002K001"
LABEL = "Benzimidazole series"


def batch(bid: int, cdd_name: str, lgcy: str | None = None) -> dict:
    return {
        "id": bid,
        "name": cdd_name.rsplit("-", 1)[-1],
        "molecule_batch_identifier": cdd_name,
        "batch_fields": {"LGCY Batch Name": lgcy, "Batch Synonym": "DDU201703"},
        "salt_name": "Unknown Salt",
    }


def molecule(
    mid: int, name: str, smiles: str | None, *, alt: str | None = None, batches=()
) -> dict:
    obj: dict[str, Any] = {
        "id": mid,
        "name": name,
        "synonyms": [name],
        "modified_at": "2026-05-18T10:00:00Z",
        "molecule_fields": {"Alternate Names": alt} if alt else {},
        "batches": list(batches),
    }
    if smiles:
        obj["smiles"] = smiles
    return obj


MOL = molecule(
    7,
    NAME,
    SMILES,
    alt="Paracetamol; 103-90-2",
    batches=[batch(13250, f"{NAME}-001", LGCY_1), batch(13251, f"{NAME}-002", LGCY_2)],
)
IDS_001 = {
    f"{NAME}-001": ("custom", "CDD batch ID"),
    LGCY_1: ("custom", "CDD legacy batch ID"),
    "13250": ("cdd_batch_id", "CDD import"),
}
IDS_002 = {
    f"{NAME}-002": ("custom", "CDD batch ID"),
    LGCY_2: ("custom", "CDD legacy batch ID"),
    "13251": ("cdd_batch_id", "CDD import"),
}


@pytest.fixture
async def ws(session_factory) -> Ws:  # type: ignore[no-untyped-def]
    ws_id = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _ensure_org(uow.session, ws_id, ws_id)
        await uow.commit()
    return Ws(id=ws_id, org_id=ws_id, actor=uuid.uuid4())


@pytest.fixture
def run_cdd(session_factory, ws: Ws, tmp_path: Path):  # type: ignore[no-untyped-def]
    async def _run(objects: list[dict]) -> list[ChunkItemResult]:
        export_dir = tmp_path / uuid.uuid4().hex
        export_dir.mkdir()
        raw = export_dir / "raw_export.json"
        raw.write_text(json.dumps({"count": len(objects), "objects": objects}))
        _split_export(
            raw,
            export_dir,
            ColumnMapping.from_dict({"columns": MAPPING}),
            get_default_template("cdd_vault")[0],  # the molecule's vault id
        )
        env = ActivityEnvironment()
        chunk = await env.run(
            CddFetchActivities(None, None, None).load_export_chunk,  # type: ignore[arg-type]
            LoadExportChunkInput(
                storage_path=str(export_dir),
                offset=0,
                limit=CHUNK_SIZE,
                entity_mappings=ENTITY_MAPPINGS,
                registration_mapping=MAPPING,
            ),
        )
        activities = RegistrationActivities(
            session_factory, _Dispatcher(), PROCESSOR, MergeSideEffectRegistry()
        )
        out = await env.run(
            activities.process_chunk,
            ChunkInput(
                workspace_id=str(ws.id),
                originating_org_id=str(ws.org_id),
                submitted_by=str(ws.actor),
                items=[ChunkItem(**d) for d in chunk.items],
            ),
        )
        _run.report = out.report  # type: ignore[attr-defined]
        return out.results

    return _run


async def _custom_fields(session_factory, ws: Ws) -> dict[uuid.UUID, Any]:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        rows = await s.execute(
            sa.text("SELECT id, custom_fields FROM batches WHERE workspace_id = :ws"),
            {"ws": ws.id},
        )
        return dict(rows.all())  # type: ignore[arg-type]


async def _state(session_factory, ws: Ws):  # type: ignore[no-untyped-def]
    """Everything a re-run could add to: compounds and their IDs, batches and theirs."""
    mols = await _molecules(session_factory, ws)
    return (
        {m: await _compound_ids(session_factory, m) for m, _, _ in mols},
        await _batches(session_factory, ws),
        await _custom_fields(session_factory, ws),
    )


async def test_two_cdd_batches_become_two_batches(session_factory, ws: Ws, run_cdd) -> None:
    first, second = await run_cdd([MOL])

    assert [r.error for r in (first, second)] == [None, None]
    assert first.molecule_id == second.molecule_id
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2
    assert batches[uuid.UUID(first.batch_id)].real == IDS_001  # no Batch Synonym
    assert batches[uuid.UUID(second.batch_id)].real == IDS_002
    custom = await _custom_fields(session_factory, ws)
    assert custom[uuid.UUID(first.batch_id)] == {"cdd_batch_id": 13250}  # plates find it
    assert custom[uuid.UUID(second.batch_id)] == {"cdd_batch_id": 13251}
    ids = await _compound_ids(session_factory, uuid.UUID(first.molecule_id))
    assert {
        ("7", "cdd_molecule_id"),
        ("Paracetamol", "custom"),
        ("103-90-2", "cas_number"),
    } <= {(i, t) for i, t, _ in ids}


async def test_rerun_adds_nothing(session_factory, ws: Ws, run_cdd) -> None:
    first = await run_cdd([MOL])
    before = await _state(session_factory, ws)

    again = await run_cdd([MOL])

    assert [r.error for r in again] == [None, None]
    assert [r.warnings for r in again] == [[], []]
    assert [r.batch_id for r in again] == [r.batch_id for r in first]
    assert await _state(session_factory, ws) == before


async def test_old_style_compound_is_filled_in(session_factory, ws: Ws, run_cdd) -> None:
    """Review Focus 3. The old import's shape: the compound by name and vault id, one
    batch, the CDD batch name only in vendor_catalog_number plus the automatic alias
    with that text, vault batch id in custom_fields (no numeric ID yet), then
    migration 105 as deploy ran it."""
    (old,) = await _run_worker(
        session_factory,
        ws,
        [
            row(
                NAME,
                SMILES,
                external_ids=[{"identifier": "7", "identifier_type": "cdd_molecule_id"}],
            )
        ],
        None,
    )
    async with session_factory() as s:
        await s.execute(
            sa.text(
                "UPDATE batches SET vendor_catalog_number = :vcn, "
                "custom_fields = CAST(:cf AS json) WHERE id = :id"
            ),
            {"vcn": f"{NAME}-001", "cf": json.dumps({"cdd_batch_id": 13250}), "id": old.batch_id},
        )
        await s.run_sync(_run_m105)
        await s.commit()
    assert (await _batches(session_factory, ws))[old.batch_id].real == {
        f"{NAME}-001": ("custom", "CDD batch ID")
    }

    first, second = await run_cdd([MOL])

    assert [r.error for r in (first, second)] == [None, None]
    assert uuid.UUID(first.batch_id) == old.batch_id  # matched by the CDD batch name
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2  # the missing 002 is created, nothing doubled
    assert batches[old.batch_id].real == IDS_001  # LGCY and the vault id added
    assert batches[uuid.UUID(second.batch_id)].real == IDS_002
    assert len(await _molecules(session_factory, ws)) == 1
    assert ("Paracetamol", "custom", "Alternate Names") in await _compound_ids(
        session_factory, old.molecule_id
    )

    filled = await _state(session_factory, ws)
    await run_cdd([MOL])
    assert await _state(session_factory, ws) == filled


async def test_plate_well_finds_file_created_batch_matched_by_cdd(
    session_factory, ws: Ws, run_cdd
) -> None:
    """Review Focus 4: the file-created batch gains the vault id as an ID, not the
    custom field; the CDD-created one has both."""
    (file_row,) = await _run_worker(
        session_factory, ws, [row(NAME, SMILES, batch=[(f"{NAME}-001", "CDD batch ID")])], None
    )
    first, second = await run_cdd([MOL])
    assert uuid.UUID(first.batch_id) == file_row.batch_id
    assert (await _custom_fields(session_factory, ws))[file_row.batch_id] is None

    wells = [
        {"position": "A01", "cdd_batch_id": 13250},
        {"position": "A02", "cdd_batch_id": 13251},
        {"position": "A03", "cdd_batch_id": 99999},
        {"position": "A04"},
    ]
    output = PlateChunkOutput()
    well_map = await PlateRegistrationActivities(session_factory, _Dispatcher())._resolve_wells(  # type: ignore[arg-type]
        session_factory, ws.id, "4443", wells, output
    )

    assert well_map == {
        "A01": {"batch_id": str(file_row.batch_id)},
        "A02": {"batch_id": second.batch_id},
        "A03": {"batch_id": None, "cdd_batch_id_unresolved": 99999},
        "A04": {"batch_id": None},
    }
    assert (output.wells_mapped, output.wells_unresolved) == (3, 1)


UNDISCLOSED = [
    molecule(
        n, f"SACC-00000{n}", None, alt=f"{LABEL}; ALT-{n}", batches=[batch(n, f"SACC-{n}-001")]
    )
    for n in (21, 22)
]


async def test_undisclosed_molecules_sharing_a_label_stay_two_compounds(
    session_factory, ws: Ws, run_cdd
) -> None:
    """Review Focus 2, CDD path: the label is on both, so it is stored on neither."""
    results = await run_cdd(UNDISCLOSED)

    assert [r.error for r in results] == [None, None]
    mols = await _molecules(session_factory, ws)
    assert sorted(status for _, _, status in mols) == ["undisclosed", "undisclosed"]
    assert results[0].molecule_id != results[1].molecule_id
    for r, own in zip(results, ("ALT-21", "ALT-22"), strict=True):
        (warning,) = r.warnings
        assert LABEL in warning
        ids = {i for i, _, _ in await _compound_ids(session_factory, uuid.UUID(r.molecule_id))}
        assert own in ids and LABEL not in ids


async def test_partial_runs_store_a_shared_name_on_the_first_compound_only(
    session_factory, ws: Ws, run_cdd
) -> None:
    """Review Focus 2 when a run reads one molecule at a time (Sync, Specific
    molecules): no label is seen, the stored-only rule keeps the two apart."""
    (first,) = await run_cdd(UNDISCLOSED[:1])
    (second,) = await run_cdd(UNDISCLOSED[1:])

    assert (first.error, second.error) == (None, None)
    assert first.molecule_id != second.molecule_id
    assert first.warnings == []
    assert len(second.warnings) == 1
    assert second.warnings[0].startswith(f"'{LABEL}' is already an ID of ")
    assert LABEL in {
        i for i, _, _ in await _compound_ids(session_factory, uuid.UUID(first.molecule_id))
    }


async def test_report_counts_what_was_added_and_skipped(ws: Ws, run_cdd) -> None:
    """§8: one new compound with two new batches; then a second compound (a partial
    run, so its name is no label) whose Alternate Name is already the first's: that
    one value is skipped and named in the report."""
    await run_cdd([MOL])
    report = run_cdd.report
    assert (report["compounds_added"], report["compounds_matched"]) == (1, 0)
    assert (report["batches_created"], report["batches_matched"]) == (2, 0)
    # three IDs on each batch; the compound's name, vault id, Alternate Name and CAS
    assert report["ids_added"] == 6 + 4
    assert (report["values_skipped"], report["problems"], report["problem_lines"]) == (0, 0, [])

    other = molecule(8, "SACC-1", "CCO", alt="Paracetamol", batches=[batch(1, "SACC-1-001")])
    await run_cdd([other])
    report = run_cdd.report
    assert (report["compounds_added"], report["compounds_matched"]) == (1, 0)
    assert (report["batches_created"], report["batches_matched"]) == (1, 0)
    assert report["values_skipped"] == 1
    assert report["problems"] == 0
    (line,) = report["problem_lines"]
    assert line.startswith("SACC-1: 'Paracetamol' is already an ID of ")


async def _reg(session_factory, molecule_id: uuid.UUID) -> str:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        return (
            await s.execute(
                sa.text("SELECT registration_number FROM molecules WHERE id = :m"),
                {"m": molecule_id},
            )
        ).scalar_one()


async def test_fill_in_counts_compound_and_batch_ids_added(ws: Ws, run_cdd) -> None:
    """A re-run that adds one Alternate Name to the compound and one LGCY Batch Name to
    its batch reports 2 IDs added."""
    await run_cdd([molecule(9, "SACC-9", "CCN", batches=[batch(90, "SACC-9-001")])])

    await run_cdd(
        [molecule(9, "SACC-9", "CCN", alt="ALT-9", batches=[batch(90, "SACC-9-001", "LGCY-9")])]
    )

    assert run_cdd.report["ids_added"] == 2


async def test_molecule_warnings_and_problems_count_once(session_factory, ws: Ws, run_cdd) -> None:
    """A molecule's skipped value or conflict is one line, not one per batch."""
    await run_cdd(
        [molecule(8, "SACC-1", "CCO", alt="Paracetamol", batches=[batch(1, "SACC-1-001")])]
    )
    two = [batch(400, "SACC-40-001"), batch(401, "SACC-40-002")]

    first, second = await run_cdd(
        [molecule(40, "SACC-40", "CCCC", alt="Paracetamol", batches=two)]
    )

    assert len(first.warnings) == 1 and second.warnings == []
    assert run_cdd.report["values_skipped"] == 1
    assert len(run_cdd.report["problem_lines"]) == 1

    # SACC-40's name with another structure and another vault id: a conflict, both rows
    await run_cdd(
        [molecule(41, "SACC-40", "CCCCC", batches=[batch(410, "X-001"), batch(411, "X-002")])]
    )
    assert run_cdd.report["problems"] == 1
    assert len(run_cdd.report["problem_lines"]) == 1


@pytest.mark.parametrize(
    "smiles", [("CCCl", "CCBr"), (None, None)], ids=["disclosed", "undisclosed"]
)
async def test_a_name_of_another_molecule_in_the_run_is_not_stored(
    session_factory, ws: Ws, run_cdd, smiles
) -> None:
    """B is read before A and lists A's name and vault id among its Alternate Names:
    neither is stored on B, so A registers as itself."""
    b = molecule(
        31, "SACC-B", smiles[0], alt="SACC-A; 30; ALT-B", batches=[batch(310, "SACC-B-1")]
    )
    a = molecule(30, "SACC-A", smiles[1], batches=[batch(300, "SACC-A-1")])

    rb, ra = await run_cdd([b, a])

    assert (rb.error, ra.error) == (None, None)
    assert rb.molecule_id != ra.molecule_id
    assert len(await _molecules(session_factory, ws)) == 2
    name_warning, vault_id_warning = rb.warnings
    assert "'SACC-A'" in name_warning and "'30'" in vault_id_warning
    b_ids = {i for i, _, _ in await _compound_ids(session_factory, uuid.UUID(rb.molecule_id))}
    assert "ALT-B" in b_ids and not {"SACC-A", "30"} & b_ids
    a_ids = {i for i, _, _ in await _compound_ids(session_factory, uuid.UUID(ra.molecule_id))}
    assert {"SACC-A", "30"} <= a_ids


VAULT_ID_7 = [{"identifier": "7", "identifier_type": "cdd_molecule_id"}]


async def test_vault_id_decides_over_a_structure_match(session_factory, ws: Ws, run_cdd) -> None:
    """Decision 6: X holds MOL's vault id and name, Y has MOL's structure. MOL's
    batches go on X, with a warning; nothing conflicts or merges."""
    x, y = await _run_worker(
        session_factory,
        ws,
        [row(NAME, "CCOC", external_ids=VAULT_ID_7), row("OTHER-1", SMILES)],
        None,
    )

    first, second = await run_cdd([MOL])

    assert (first.error, second.error) == (None, None)
    assert {first.molecule_id, second.molecule_id} == {str(x.molecule_id)}
    y_reg = await _reg(session_factory, y.molecule_id)
    assert y_reg in first.warnings[0]
    batches = await _batches(session_factory, ws)
    assert {batches[uuid.UUID(r.batch_id)].molecule_id for r in (first, second)} == {x.molecule_id}
    assert len(await _molecules(session_factory, ws)) == 2


async def test_vault_id_decides_when_structures_differ(session_factory, ws: Ws, run_cdd) -> None:
    """X holds MOL's vault id and name with another structure, no compound has MOL's:
    MOL goes on X, which keeps its structure. A vault molecule without a structure goes
    on X too, though X has one."""
    (x,) = await _run_worker(
        session_factory, ws, [row(NAME, "CCOC", external_ids=VAULT_ID_7)], None
    )
    x_reg = await _reg(session_factory, x.molecule_id)

    first, _ = await run_cdd([MOL])
    assert first.error is None and first.molecule_id == str(x.molecule_id)
    assert x_reg in first.warnings[0]

    undisclosed = molecule(7, NAME, None, batches=[batch(13252, f"{NAME}-003")])
    (third,) = await run_cdd([undisclosed])
    assert third.error is None and third.molecule_id == str(x.molecule_id)
    assert len(await _molecules(session_factory, ws)) == 1


@pytest.mark.parametrize("smiles", [SMILES, None], ids=["structure", "no structure"])
async def test_the_vault_id_text_under_another_type_is_not_the_row_s_compound(
    session_factory, ws: Ws, run_cdd, smiles
) -> None:
    """Z holds "7" as a PubChem CID, not as a vault molecule id: MOL's vault id "7" does
    not make Z MOL's compound; the old rule decides (here: a conflict)."""
    (z,) = await _run_worker(
        session_factory,
        ws,
        [
            row(
                "Z-1",
                "CCOCC",
                external_ids=[{"identifier": "7", "identifier_type": "pubchem_cid"}],
            )
        ],
        None,
    )

    results = await run_cdd([molecule(7, NAME, smiles, batches=[batch(13250, f"{NAME}-001")])])

    assert all(r.molecule_id != str(z.molecule_id) for r in results)
    assert NAME not in {i for i, _, _ in await _compound_ids(session_factory, z.molecule_id)}
    assert len(await _batches(session_factory, ws)) == 1  # Z's own


async def test_structure_notes_are_report_lines_not_skipped_values(
    session_factory, ws: Ws, run_cdd
) -> None:
    await _run_worker(
        session_factory,
        ws,
        [row(NAME, "CCOC", external_ids=VAULT_ID_7), row("OTHER-1", SMILES)],
        None,
    )

    await run_cdd([molecule(7, NAME, SMILES, batches=[batch(13250, f"{NAME}-001")])])

    report = run_cdd.report
    assert report["values_skipped"] == 0
    (line,) = report["problem_lines"]
    assert line.startswith(f"{NAME}: Structure also matches ")
