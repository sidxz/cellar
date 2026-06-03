"""Integration test: PreviewSummaryImport use case (summary import dry-run).

Exercises the real parser + identifier-aware resolver + SQLAlchemy repos to
forecast insert-vs-update for a wide-format summary file WITHOUT writing. The
CRITICAL invariant is that the use case performs NO writes — every test asserts
the ``readout_data`` row count is unchanged across the call.

Mirrors ``test_import_summary_file.py`` seeds (molecule with custom identifier,
run, protocol with an IC50 numeric def).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from returns.result import Success

from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
)
from cellar.application.screening.import_summary_file import (
    ImportSummaryFile,
    ImportSummaryFileCommand,
)
from cellar.application.screening.preview_summary_import import (
    PreviewSummaryImport,
    PreviewSummaryImportCommand,
)
from cellar.application.screening.summary_import_models import SummaryColumnMapping
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
from cellar.infrastructure.parsers.tabular_file import TabularFileParser
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import (
    _insert_org,
    _insert_protocol,
    _insert_run,
)


class _NoOpDispatcher:
    async def dispatch_all(self, events: list) -> None:
        return None


async def _insert_readout_def_typed(
    uow: AsyncUnitOfWork,
    rd_id: uuid.UUID,
    protocol_id: uuid.UUID,
    *,
    name: str,
    data_type: str,
    display_order: int,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO readout_definitions "
            "(id, protocol_id, name, data_type, display_order, is_calculated) "
            "VALUES (:id, :proto, :name, :dt, :ord, false)"
        ),
        {"id": rd_id, "proto": protocol_id, "name": name, "dt": data_type, "ord": display_order},
    )


async def _insert_molecule_identifier(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    identifier: str,
    *,
    identifier_type: str = "custom",
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecule_identifiers "
            "(id, molecule_id, workspace_id, identifier, identifier_type, source, registered_by) "
            "VALUES (:id, :mol, :ws, :ident, :itype, 'test', :by)"
        ),
        {
            "id": uuid.uuid4(),
            "mol": mol_id,
            "ws": ws_id,
            "ident": identifier,
            "itype": identifier_type,
            "by": uuid.uuid4(),
        },
    )


async def _insert_molecule(
    uow: AsyncUnitOfWork,
    mol_id: uuid.UUID,
    ws_id: uuid.UUID,
    reg: str,
    *,
    identifier: str | None = None,
) -> None:
    org_id = uuid.uuid4()
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :name, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws_id, "name": f"Org-{reg}"},
    )
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'undisclosed', "
            "'approved', 'virtual', 'registered', :reg, :org, 1)"
        ),
        {"id": mol_id, "ws": ws_id, "name": f"M-{reg}", "reg": reg, "org": org_id},
    )
    await _insert_molecule_identifier(
        uow, mol_id, ws_id, identifier if identifier is not None else reg
    )


def _build_preview(read_uow: AsyncUnitOfWork) -> PreviewSummaryImport:
    return PreviewSummaryImport(
        run_repo=SQLAlchemyRunRepository(read_uow),
        protocol_repo=SQLAlchemyProtocolRepository(read_uow),
        readout_repo=SQLAlchemyReadoutDataRepository(read_uow),
        molecule_repo=SQLAlchemyMoleculeRepository(read_uow),
        batch_repo=SQLAlchemyBatchRepository(read_uow),
        parser=TabularFileParser(),
        uow=read_uow,
    )


def _build_import(read_uow: AsyncUnitOfWork, session_factory) -> ImportSummaryFile:
    run_repo = SQLAlchemyRunRepository(read_uow)
    readout_repo = SQLAlchemyReadoutDataRepository(read_uow)
    protocol_repo = SQLAlchemyProtocolRepository(read_uow)

    bulk_uow = AsyncUnitOfWork(session_factory)
    bulk_run_repo = SQLAlchemyRunRepository(bulk_uow)
    bulk = BulkCreateReadoutData(
        uow=bulk_uow,
        repo=SQLAlchemyReadoutDataRepository(bulk_uow),
        guard=DataLockGuard(bulk_run_repo),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
        molecule_repo=SQLAlchemyMoleculeRepository(bulk_uow),
        run_repo=bulk_run_repo,
        protocol_repo=SQLAlchemyProtocolRepository(bulk_uow),
    )
    return ImportSummaryFile(
        uow=read_uow,
        run_repo=run_repo,
        protocol_repo=protocol_repo,
        readout_repo=readout_repo,
        molecule_repo=SQLAlchemyMoleculeRepository(read_uow),
        batch_repo=SQLAlchemyBatchRepository(read_uow),
        parser=TabularFileParser(),
        bulk_uc=bulk,
    )


async def _readout_count(session_factory) -> int:
    check_uow = AsyncUnitOfWork(session_factory)
    async with check_uow:
        result = await check_uow.session.execute(sa.text("SELECT COUNT(*) FROM readout_data"))
        return int(result.scalar_one())


async def _run_preview(session_factory, command, auth):
    read_uow = AsyncUnitOfWork(session_factory)
    uc = _build_preview(read_uow)
    return await uc(command, auth=auth)


async def _run_import(session_factory, command, auth):
    read_uow = AsyncUnitOfWork(session_factory)
    uc = _build_import(read_uow, session_factory)
    return await uc(command, auth=auth)


async def _seed(session_factory, workspace_id, *, identifier=None):
    """Seed org + protocol + IC50 numeric def + run + one molecule.

    Returns (run_id, ic50_id, molecule_id, ref) where ``ref`` is the value the
    file's compound_ref column should carry (identifier if given, else reg).
    """
    molecule_id = uuid.uuid4()
    reg = f"CC-{uuid.uuid4().hex[:8]}"
    ic50_id = uuid.uuid4()
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    seed_uow = AsyncUnitOfWork(session_factory)
    async with seed_uow:
        await _insert_org(seed_uow, org_id, workspace_id)
        await _insert_protocol(seed_uow, protocol_id, workspace_id)
        await _insert_readout_def_typed(
            seed_uow, ic50_id, protocol_id, name="IC50", data_type="numeric", display_order=0
        )
        await _insert_run(seed_uow, run_id, protocol_id, workspace_id)
        await _insert_molecule(
            seed_uow, molecule_id, workspace_id, reg, identifier=identifier
        )
        await seed_uow.commit()
    ref = identifier if identifier is not None else reg
    return run_id, ic50_id, molecule_id, ref


class TestPreviewSummaryImport:
    async def test_all_resolve_forecasts_inserts_no_writes(
        self, session_factory, workspace_id
    ) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)
        run_id, ic50_id, _mol, ref = await _seed(session_factory, workspace_id)
        mapping = SummaryColumnMapping(compound_ref="Compound", readout_columns={"IC50": ic50_id})

        before = await _readout_count(session_factory)

        result = await _run_preview(
            session_factory,
            PreviewSummaryImportCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{ref},5.2\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        preview = result.unwrap()
        assert preview.values_to_insert == 1
        assert preview.values_to_update == 0
        assert preview.unmatched_compound_refs == []
        assert preview.unmatched_batch_refs == []
        assert preview.matched_compound_count == 1
        assert preview.errors == []

        # CRITICAL: no writes.
        after = await _readout_count(session_factory)
        assert after == before

    async def test_existing_rows_forecast_updates(
        self, session_factory, workspace_id
    ) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)
        run_id, ic50_id, _mol, ref = await _seed(session_factory, workspace_id)
        mapping = SummaryColumnMapping(compound_ref="Compound", readout_columns={"IC50": ic50_id})
        content = f"Compound,IC50\n{ref},5.2\n".encode()

        # Actually import the data first so a well-less row exists.
        imp = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=content,
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(imp, Success)
        assert imp.unwrap().values_inserted == 1

        before = await _readout_count(session_factory)

        # Second preview of the same data → all updates, no inserts.
        result = await _run_preview(
            session_factory,
            PreviewSummaryImportCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=content,
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        preview = result.unwrap()
        assert preview.values_to_update == 1
        assert preview.values_to_insert == 0

        after = await _readout_count(session_factory)
        assert after == before

    async def test_unmatched_compound_ref(self, session_factory, workspace_id) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)
        run_id, ic50_id, _mol, _ref = await _seed(session_factory, workspace_id)
        mapping = SummaryColumnMapping(compound_ref="Compound", readout_columns={"IC50": ic50_id})

        before = await _readout_count(session_factory)
        missing = "NOPE-DOES-NOT-EXIST"

        result = await _run_preview(
            session_factory,
            PreviewSummaryImportCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{missing},5.2\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        preview = result.unwrap()
        assert preview.unmatched_compound_refs == [missing]
        assert preview.values_to_insert == 0
        assert preview.values_to_update == 0

        after = await _readout_count(session_factory)
        assert after == before

    async def test_bad_numeric_in_errors(self, session_factory, workspace_id) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)
        run_id, ic50_id, _mol, ref = await _seed(session_factory, workspace_id)
        mapping = SummaryColumnMapping(compound_ref="Compound", readout_columns={"IC50": ic50_id})

        before = await _readout_count(session_factory)

        result = await _run_preview(
            session_factory,
            PreviewSummaryImportCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{ref},not-a-number\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        preview = result.unwrap()
        assert len(preview.errors) == 1
        assert "not numeric" in preview.errors[0]["error"]
        assert preview.values_to_insert == 0

        after = await _readout_count(session_factory)
        assert after == before

    async def test_no_writes_across_full_run(self, session_factory, workspace_id) -> None:
        """Belt-and-braces: a preview over a mix of matched + unmatched +
        bad-numeric rows must not change the readout_data row count."""
        auth = FakeAuth(role="editor", workspace_id=workspace_id)
        run_id, ic50_id, _mol, ref = await _seed(session_factory, workspace_id)
        mapping = SummaryColumnMapping(compound_ref="Compound", readout_columns={"IC50": ic50_id})

        before = await _readout_count(session_factory)

        result = await _run_preview(
            session_factory,
            PreviewSummaryImportCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=(
                    f"Compound,IC50\n{ref},5.2\nMISSING-REF,9.9\n{ref},oops\n,1.0\n"
                ).encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        preview = result.unwrap()
        assert preview.values_to_insert == 1
        assert preview.rows_skipped == 1
        assert "MISSING-REF" in preview.unmatched_compound_refs

        after = await _readout_count(session_factory)
        assert after == before
