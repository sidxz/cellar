"""Batch IDs from a bulk file land on the right batch (spec 2026-11-18 §4), real DB.

Each scenario runs through both pipelines: the in-process ``BulkRegistrationService``
and the Temporal worker's ``RegistrationActivities.process_chunk``.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from temporalio.testing import ActivityEnvironment

from cellar.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationItem,
    BulkRegistrationService,
    StartBulkRegistrationCommand,
)
from cellar.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from cellar.application.inventory.salt_matcher import SaltMatcher
from cellar.application.inventory.sync_batch_identifier_mirrors import SyncBatchIdentifierMirrors
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_repository import (  # noqa: E501
    SQLAlchemyBulkRegistrationRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (  # noqa: E501
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator
from cellar.infrastructure.rdkit.structure_processor import StructureProcessor
from cellar.infrastructure.temporal.activities.dtos import ChunkInput, ChunkItem
from cellar.infrastructure.temporal.activities.registration import RegistrationActivities
from tests.fakes.fake_auth import FakeAuth
from tests.integration.chemical_registration.conftest import _ensure_org

PROCESSOR = StructureProcessor(scaffold_calculator=MurckoScaffoldCalculator())
PROBLEM = "Compound registered, batch not created: "


class _Dispatcher:
    async def dispatch_all(self, events) -> None:  # type: ignore[no-untyped-def]
        pass


@dataclass(frozen=True)
class Ws:
    id: uuid.UUID
    org_id: uuid.UUID
    actor: uuid.UUID


@dataclass(frozen=True)
class RowOutcome:
    molecule_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    batch_number: str | None
    error: str | None  # the row's message, as the job records it
    batch_skipped: bool


@dataclass
class BatchView:
    batch_number: str
    molecule_id: uuid.UUID
    amount_value: float
    purity: float | None
    real: dict[str, tuple[str, str]] = field(default_factory=dict)  # text → (type, source)
    auto: set[str] = field(default_factory=set)  # automatic aliases


Run = Callable[..., Awaitable[list[RowOutcome]]]


def row(
    name: str | None,
    smiles: str | None = None,
    *,
    batch: Sequence[tuple[str, str]] = (),
    ids: Sequence[tuple[str, str]] = (),
    **fields: object,
) -> dict:
    """One parsed file row: ``batch``/``ids`` are (value, Source label) pairs."""
    return {
        "name": name,
        "smiles": smiles,
        "batch_ids": [{"identifier": i, "source": s} for i, s in batch],
        "external_ids": [
            {"identifier": i, "identifier_type": "custom", "source": s} for i, s in ids
        ],
        **fields,
    }


@pytest.fixture
async def ws(session_factory) -> Ws:  # type: ignore[no-untyped-def]
    ws_id = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _ensure_org(uow.session, ws_id, ws_id)
        await uow.commit()
    return Ws(id=ws_id, org_id=ws_id, actor=uuid.uuid4())


async def _run_service(
    session_factory, ws: Ws, rows: list[dict], create_batch_on_duplicate: bool | None
) -> list[RowOutcome]:
    uow = AsyncUnitOfWork(session_factory)
    batch_repo = SQLAlchemyBatchRepository(uow)
    service = BulkRegistrationService(  # wired as in di/_chemical_registration.py
        uow=uow,
        bulk_reg_repo=SQLAlchemyBulkRegistrationRepository(uow),
        mol_repo=SQLAlchemyMoleculeRepository(uow),
        dispatcher=_Dispatcher(),
        structure_processor=PROCESSOR,
        salt_matcher=SaltMatcher(SQLAlchemySaltEntryRepository(uow)),
        batch_repo=batch_repo,
        settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
        sync=SyncBatchIdentifierMirrors(batch_repo),
    )
    result = await service(
        StartBulkRegistrationCommand(
            workspace_id=ws.id,
            source_file="rows.xlsx",
            file_format="xlsx",
            items=[
                BulkRegistrationItem(row_index=i, file_row=i + 2, **r) for i, r in enumerate(rows)
            ],
            submitted_by=ws.actor,
            originating_org_id=ws.org_id,
            create_batch_on_duplicate=create_batch_on_duplicate,
        ),
        auth=FakeAuth(role="editor", workspace_id=ws.id, user_id=ws.actor),
    )
    outcome = result.unwrap()
    async with session_factory() as s:
        recorded = dict(
            (
                await s.execute(
                    sa.text(
                        "SELECT row_index, error FROM bulk_registration_items "
                        "WHERE bulk_registration_id = :id"
                    ),
                    {"id": outcome.bulk_registration.id},
                )
            ).all()
        )
    return [
        RowOutcome(
            r.molecule_id, r.batch_id, r.batch_number, recorded[r.row_index], r.batch_skipped
        )
        for r in outcome.item_results
    ]


async def _run_worker(
    session_factory, ws: Ws, rows: list[dict], create_batch_on_duplicate: bool | None
) -> list[RowOutcome]:
    activities = RegistrationActivities(
        session_factory, _Dispatcher(), PROCESSOR, MergeSideEffectRegistry()
    )
    output = await ActivityEnvironment().run(
        activities.process_chunk,
        ChunkInput(
            workspace_id=str(ws.id),
            originating_org_id=str(ws.org_id),
            submitted_by=str(ws.actor),
            items=[ChunkItem(row_index=i, file_row=i + 2, **r) for i, r in enumerate(rows)],
            create_batch_on_duplicate=create_batch_on_duplicate,
        ),
    )
    return [
        RowOutcome(
            uuid.UUID(r.molecule_id) if r.molecule_id else None,
            uuid.UUID(r.batch_id) if r.batch_id else None,
            r.batch_number,
            r.error,
            r.batch_skipped,
        )
        for r in output.results
    ]


@pytest.fixture(params=["service", "worker"])
def run_rows(request, session_factory, ws: Ws) -> Run:  # type: ignore[no-untyped-def]
    pipeline = _run_service if request.param == "service" else _run_worker

    async def _run(
        rows: list[dict], *, create_batch_on_duplicate: bool | None = None
    ) -> list[RowOutcome]:
        return await pipeline(session_factory, ws, rows, create_batch_on_duplicate)

    return _run


async def _batches(session_factory, ws: Ws) -> dict[uuid.UUID, BatchView]:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        rows = (
            await s.execute(
                sa.text(
                    "SELECT b.id, b.batch_number, b.molecule_id, b.amount_value, b.purity, "
                    "bi.identifier, bi.identifier_type, bi.source, "
                    "bi.derived_from_molecule_identifier_id IS NOT NULL AS auto "
                    "FROM batches b LEFT JOIN batch_identifiers bi ON bi.batch_id = b.id "
                    "WHERE b.workspace_id = :ws"
                ),
                {"ws": ws.id},
            )
        ).all()
    out: dict[uuid.UUID, BatchView] = {}
    for bid, number, mol, amount, purity, ident, itype, source, auto in rows:
        view = out.setdefault(bid, BatchView(number, mol, amount, purity))
        if ident is None:
            continue
        if auto:
            view.auto.add(ident)
        else:
            view.real[ident] = (itype, source)
    return out


async def _molecules(session_factory, ws: Ws) -> list[tuple[uuid.UUID, str, str]]:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        return list(
            (
                await s.execute(
                    sa.text(
                        "SELECT id, name, structure_status FROM molecules WHERE workspace_id = :ws"
                    ),
                    {"ws": ws.id},
                )
            ).all()
        )


async def _compound_ids(session_factory, molecule_id: uuid.UUID) -> set[tuple[str, str, str]]:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        rows = await s.execute(
            sa.text(
                "SELECT identifier, identifier_type, source FROM molecule_identifiers "
                "WHERE molecule_id = :m"
            ),
            {"m": molecule_id},
        )
        return {tuple(r) for r in rows.all()}  # type: ignore[misc]


SACC = "SACC-0428730"
SACC_SMILES = "COC(=O)c1ccc(N)cc1"
ROW_001 = row(
    SACC,
    SACC_SMILES,
    batch=[(f"{SACC}-001", "CDD batch ID"), ("MSD-946760565-001K001", "CDD legacy batch ID")],
    amount_value=5.0,
)
ROW_002 = row(
    SACC,
    SACC_SMILES,
    batch=[(f"{SACC}-002", "CDD batch ID"), ("MSD-946760565-002K001", "CDD legacy batch ID")],
    amount_value=2.0,
)
IDS_001 = {
    f"{SACC}-001": ("custom", "CDD batch ID"),
    "MSD-946760565-001K001": ("custom", "CDD legacy batch ID"),
}
IDS_002 = {
    f"{SACC}-002": ("custom", "CDD batch ID"),
    "MSD-946760565-002K001": ("custom", "CDD legacy batch ID"),
}


async def test_new_compound_with_two_batch_rows_gets_two_batches(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    out = await run_rows([ROW_001, ROW_002])

    assert [o.error for o in out] == [None, None]
    assert len(await _molecules(session_factory, ws)) == 1
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2
    assert batches[out[0].batch_id].real == IDS_001
    assert batches[out[1].batch_id].real == IDS_002
    assert [batches[o.batch_id].amount_value for o in out] == [5.0, 2.0]


async def test_same_rows_imported_twice_add_nothing(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    first = await run_rows([ROW_001, ROW_002])
    before = await _batches(session_factory, ws)

    again = await run_rows([ROW_001, ROW_002])

    assert [o.error for o in again] == [None, None]
    assert [o.batch_id for o in again] == [o.batch_id for o in first]
    assert await _batches(session_factory, ws) == before  # no batch, no ID, no alias added
    assert len(await _molecules(session_factory, ws)) == 1


async def test_rows_out_of_order_keep_their_own_ids(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    """Review Focus 1 (R1): the 002 row first. Its batch is ChemCellar's -001 and gets
    the automatic alias ``SACC-0428730-001``; the 001 row must not match that alias."""
    out = await run_rows([ROW_002, ROW_001])

    assert [o.error for o in out] == [None, None]
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2
    assert batches[out[0].batch_id].real == IDS_002
    assert batches[out[1].batch_id].real == IDS_001
    assert out[0].batch_number.endswith("-001")  # ChemCellar numbers its own batches
    # R2: the 001 row's ID moved off the alias; no batch keeps it as an alias.
    assert all(f"{SACC}-001" not in b.auto for b in batches.values())


async def test_file_id_held_by_automatic_alias_goes_to_the_rows_batch(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    """Review Focus 2 (R2): the alias is removed, the ID is stored, no unique violation."""
    (p,) = await run_rows([row("ALIAS-P", "CCCCO")])
    assert "ALIAS-P-001" in (await _batches(session_factory, ws))[p.batch_id].auto

    (q,) = await run_rows([row("OTHER-Q", "CCCCN", batch=[("ALIAS-P-001", "Legacy lot")])])

    assert q.error is None
    assert q.batch_id is not None and q.batch_id != p.batch_id
    batches = await _batches(session_factory, ws)
    assert "ALIAS-P-001" not in batches[p.batch_id].auto
    assert "ALIAS-P-001" not in batches[p.batch_id].real
    assert batches[q.batch_id].real == {"ALIAS-P-001": ("custom", "Legacy lot")}


async def test_batch_matched_by_a_real_id_is_reused_and_keeps_its_fields(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    (first,) = await run_rows(
        [row("KEEP-1", "CCCCCO", batch=[("K-001", "CDD batch ID")], amount_value=7.5, purity=98.0)]
    )

    (again,) = await run_rows(
        [
            row(
                "KEEP-1",
                "CCCCCO",
                batch=[("K-001", "CDD batch ID"), ("K-LEG-1", "CDD legacy batch ID")],
                amount_value=1.0,
                purity=50.0,
            )
        ]
    )

    assert again.error is None
    assert again.batch_id == first.batch_id
    (batch,) = (await _batches(session_factory, ws)).values()
    assert (batch.amount_value, batch.purity) == (7.5, 98.0)
    assert batch.real == {
        "K-001": ("custom", "CDD batch ID"),
        "K-LEG-1": ("custom", "CDD legacy batch ID"),
    }


async def test_existing_compound_whose_batches_do_not_match_gets_a_new_batch(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    (first,) = await run_rows([row("KEEP-2", "CCCCCCl", batch=[("K2-001", "CDD batch ID")])])

    (second,) = await run_rows([row("KEEP-2", "CCCCCCl", batch=[("K2-002", "CDD batch ID")])])

    assert second.error is None
    assert second.batch_id not in (None, first.batch_id)
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2
    assert batches[second.batch_id].real == {"K2-002": ("custom", "CDD batch ID")}


async def test_id_on_another_compounds_batch_registers_compound_without_batch(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    (owner,) = await run_rows([row("OWNER-A", "CCCCCCO", batch=[("SHARED-1", "CDD batch ID")])])

    (other,) = await run_rows(
        [
            row(
                "OTHER-B",
                "CCCCCCN",
                ids=[("B-SYN-1", "Synonyms")],
                batch=[("SHARED-1", "CDD batch ID")],
            )
        ]
    )

    assert other.molecule_id is not None and other.batch_id is None
    assert other.error is not None and other.error.startswith(PROBLEM)
    assert f"SHARED-1 already belongs to {owner.batch_number} (another compound)" in other.error
    # The compound step stays, with its names and compound IDs; no batch for it.
    assert ("B-SYN-1", "custom", "Synonyms") in await _compound_ids(
        session_factory, other.molecule_id
    )
    batches = await _batches(session_factory, ws)
    assert [b.molecule_id for b in batches.values()] == [owner.molecule_id]


async def test_ids_on_two_different_batches_is_a_problem(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    await run_rows([ROW_001, ROW_002])

    (both,) = await run_rows(
        [row(SACC, SACC_SMILES, batch=[(f"{SACC}-001", "A"), (f"{SACC}-002", "A")])]
    )

    assert both.batch_id is None
    assert both.error is not None and both.error.startswith(PROBLEM)
    assert f"{SACC}-001 and {SACC}-002 belong to two different batches" in both.error
    assert len(await _batches(session_factory, ws)) == 2


async def test_row_without_batch_ids_follows_the_duplicate_policy(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    (new,) = await run_rows([row("POL-1", "CCCCCCCO")])
    (dup,) = await run_rows([row("POL-1", "CCCCCCCO")])  # workspace default: off
    (forced,) = await run_rows([row("POL-1", "CCCCCCCO")], create_batch_on_duplicate=True)

    assert new.batch_id is not None and not new.batch_skipped
    assert dup.batch_id is None and dup.batch_skipped
    assert forced.batch_id not in (None, new.batch_id)
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2
    assert all(b.real == {} for b in batches.values())  # only automatic aliases, as before


async def test_undisclosed_compound_with_two_batch_rows(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    name = "SACC-0132501"
    out = await run_rows(
        [
            row(
                name,
                ids=[("JSF-1187", "Synonyms")],
                batch=[("JSF-1187", "CDD legacy batch ID")],
            ),
            row(
                name,
                ids=[("JSF-1187", "Synonyms")],
                batch=[(f"{name}-002", "CDD batch ID")],
            ),
        ]
    )

    assert [o.error for o in out] == [None, None]
    ((mol_id, _, status),) = await _molecules(session_factory, ws)
    assert status == "undisclosed"
    assert ("JSF-1187", "custom", "Synonyms") in await _compound_ids(session_factory, mol_id)
    batches = await _batches(session_factory, ws)
    assert len(batches) == 2
    assert batches[out[0].batch_id].real == {"JSF-1187": ("custom", "CDD legacy batch ID")}
    assert batches[out[1].batch_id].real == {f"{name}-002": ("custom", "CDD batch ID")}


async def test_worker_records_a_parse_error_row_and_registers_nothing(
    session_factory, ws: Ws
) -> None:
    """Review Focus 4: the parser's error travels on the ChunkItem; the worker
    used to register such a row as a nameless undisclosed compound."""
    activities = RegistrationActivities(
        session_factory, _Dispatcher(), PROCESSOR, MergeSideEffectRegistry()
    )
    output = await ActivityEnvironment().run(
        activities.process_chunk,
        ChunkInput(
            workspace_id=str(ws.id),
            originating_org_id=str(ws.org_id),
            submitted_by=str(ws.actor),
            items=[
                ChunkItem(row_index=2, file_row=4, error="Row 4: no name or structure"),
                ChunkItem(row_index=3, file_row=5, name="AFTER-ERROR", smiles="CCCCCCCCO"),
            ],
        ),
    )

    assert output.error == 1
    assert output.registered == 1
    bad = output.results[0]
    assert (bad.success, bad.error, bad.molecule_id) == (
        False,
        "Row 4: no name or structure",
        None,
    )
    assert [name for _, name, _ in await _molecules(session_factory, ws)] == ["AFTER-ERROR"]


# ---------------------------------------------------------------------------
# Review Focus 3: a batch from the CDD automated import, after migration 105
# ---------------------------------------------------------------------------

_M105 = Path(__file__).parents[3] / "alembic" / "versions" / "105_cdd_batch_name_backfill.py"


def _run_m105(sync_session) -> None:  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m105", _M105)
    assert spec is not None and spec.loader is not None
    m105 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m105)
    with Operations.context(MigrationContext.configure(sync_session.connection())):
        m105.upgrade()


async def test_cdd_imported_batch_after_backfill_is_matched_not_doubled(
    run_rows: Run, session_factory, ws: Ws
) -> None:
    name, smiles = "SACC-0013250", "CC(=O)N[C@H](C)C(=O)O"
    # The CDD automated import's shape: batch name only in vendor_catalog_number,
    # vault batch id in custom_fields, plus the automatic alias with the same text.
    (cdd,) = await _run_worker(
        session_factory,
        ws,
        [row(name, smiles, vendor_catalog_number=f"{name}-001", cdd_batch_id=13250)],
        None,
    )
    assert f"{name}-001" in (await _batches(session_factory, ws))[cdd.batch_id].auto

    async with session_factory() as s:  # migration 105, as deploy runs it
        await s.run_sync(_run_m105)
        await s.commit()

    out = await run_rows(
        [
            row(
                name,
                smiles,
                batch=[(f"{name}-001", "CDD batch ID"), ("C07278", "CDD legacy batch ID")],
            )
        ]
    )

    assert out[0].error is None
    assert out[0].batch_id == cdd.batch_id
    (batch,) = (await _batches(session_factory, ws)).values()
    assert batch.real[f"{name}-001"] == ("custom", "CDD batch ID")
    assert batch.real["C07278"] == ("custom", "CDD legacy batch ID")
