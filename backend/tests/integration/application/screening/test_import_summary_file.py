"""Integration test: ImportSummaryFile use case (wide-format summary import).

Exercises the real parser + BulkCreateReadoutData (upsert, require_batch=False)
+ SQLAlchemy repos against a registered molecule so ``registration_number``
resolves. Mirrors ``test_bulk_readout_upsert.py`` seed-helper style.

Covers: insert vs. update accounting, text readouts, bad-numeric error
reporting, and qualifier parsing.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from returns.result import Success

from cellar.application.screening.bulk_create_readout_data import BulkCreateReadoutData
from cellar.application.screening.import_summary_file import (
    ImportSummaryFile,
    ImportSummaryFileCommand,
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
    """Add a ``molecule_identifiers`` row.

    Resolution now goes through ``find_by_identifier``, which JOINs
    ``molecule_identifiers`` (it does NOT match the ``molecules.registration_number``
    column), so a molecule is only resolvable by a value that has an identifier row.
    """
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
    """Insert a molecule and an identifier row so it is resolvable.

    ``identifier`` defaults to ``reg`` (the registration number is the value the
    file's compound_ref column carries in most tests). Pass a distinct
    ``identifier`` to prove identifier-based (not reg-number) resolution.
    """
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


def _build_use_case(read_uow: AsyncUnitOfWork, session_factory) -> ImportSummaryFile:
    # The orchestrating use case owns + enters ``read_uow`` itself; the delegated
    # bulk use case opens its own write UoW. They MUST be separate instances so
    # the bulk's commit/close does not tear down the read session used for the
    # before/after snapshots.
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


async def _wellless(session_factory, workspace_id, run_id):
    check_uow = AsyncUnitOfWork(session_factory)
    async with check_uow:
        repo = SQLAlchemyReadoutDataRepository(check_uow)
        rows = await repo.find_by_run(workspace_id, run_id)
        return [r for r in rows if r.well_id is None and not r.is_computed]


async def _run_import(session_factory, command, auth):
    """Run the import. The use case now owns + enters its own read UoW, so the
    caller just builds it and awaits (mirrors how the route calls it)."""
    read_uow = AsyncUnitOfWork(session_factory)
    uc = _build_use_case(read_uow, session_factory)
    return await uc(command, auth=auth)


class TestImportSummaryFile:
    async def test_insert_then_update_accounting(self, session_factory, workspace_id) -> None:
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound", readout_columns={"IC50": ic50_id}
        )

        first = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},5.2\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(first, Success)
        res = first.unwrap()
        assert res.values_inserted == 1
        assert res.values_updated == 0
        assert res.errors == []

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value is not None
        assert rows[0].value.value == 5.2

        # Re-import the same key with a new value → update, no insert.
        second = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},9.9\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(second, Success)
        res2 = second.unwrap()
        assert res2.values_inserted == 0
        assert res2.values_updated == 1

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value.value == 9.9

    async def test_text_readout_stores_value_text(self, session_factory, workspace_id) -> None:
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        notes_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_readout_def_typed(
                seed_uow, notes_id, protocol_id, name="Notes", data_type="text", display_order=1
            )
            await _insert_run(seed_uow, run_id, protocol_id, workspace_id)
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound",
            readout_columns={"Notes": notes_id},
        )

        result = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,Notes\n{reg},clean curve\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        assert result.unwrap().values_inserted == 1

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value_text == "clean curve"
        assert rows[0].value is None

    async def test_bad_numeric_reported_not_stored(self, session_factory, workspace_id) -> None:
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound", readout_columns={"IC50": ic50_id}
        )

        result = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},not-a-number\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.values_inserted == 0
        assert len(res.errors) == 1
        assert "not numeric" in res.errors[0]["error"]

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 0

    async def test_qualifier_parsed(self, session_factory, workspace_id) -> None:
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound", readout_columns={"IC50": ic50_id}
        )

        result = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},>100\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        assert result.unwrap().values_inserted == 1

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value is not None
        assert rows[0].value.value == 100.0
        assert rows[0].value.qualifier.value == ">"

    async def test_duplicate_key_within_file_last_wins(
        self, session_factory, workspace_id
    ) -> None:
        """Two rows with the same reg+readout collapse to ONE well-less row (last
        value wins), accounting reports a single insert, and a later re-import of
        the same compound updates in place instead of raising MultipleResultsFound
        (proving no duplicate row was planted)."""
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound", readout_columns={"IC50": ic50_id}
        )

        first = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},5.0\n{reg},7.0\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(first, Success)
        res = first.unwrap()
        assert res.values_inserted == 1
        assert res.values_updated == 0
        assert res.errors == []

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value is not None
        assert rows[0].value.value == 7.0  # last occurrence wins

        # Re-import must NOT raise (no duplicate well-less row was planted) and
        # must update the single existing row in place.
        second = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},8.0\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(second, Success)
        res2 = second.unwrap()
        assert res2.values_inserted == 0
        assert res2.values_updated == 1

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value.value == 8.0

    async def test_row_with_no_refs_is_skipped(self, session_factory, workspace_id) -> None:
        """A row whose compound and batch cells are both empty increments
        rows_skipped and stores nothing for it."""
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound", readout_columns={"IC50": ic50_id}
        )

        result = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{reg},5.2\n,9.9\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.rows_skipped == 1
        assert res.values_inserted == 1

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        assert rows[0].value.value == 5.2

    async def test_multiple_readout_columns_one_row(
        self, session_factory, workspace_id
    ) -> None:
        """A single row with two readout columns stores two values for the
        compound (one per readout definition)."""
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        ic50_id = uuid.uuid4()
        mic_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            await _insert_readout_def_typed(
                seed_uow, mic_id, protocol_id, name="MIC", data_type="numeric", display_order=1
            )
            await _insert_run(seed_uow, run_id, protocol_id, workspace_id)
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound",
            readout_columns={"IC50": ic50_id, "MIC": mic_id},
        )

        result = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50,MIC\n{reg},5.2,1.5\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.values_inserted == 2
        assert res.errors == []

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 2
        by_def = {r.readout_definition_id: r for r in rows}
        assert by_def[ic50_id].value.value == 5.2
        assert by_def[mic_id].value.value == 1.5

    async def test_resolves_by_custom_identifier_not_reg_number(
        self, session_factory, workspace_id
    ) -> None:
        """THE FIX: a compound_ref that is a custom identifier (NOT the
        registration number) resolves to the right molecule.

        The molecule's registration_number is ``CC-...`` but its custom
        identifier is ``SACC-TEST-1``; the file's compound_ref column carries the
        custom identifier. The old reg-number-only path would silently drop this
        row; the identifier-aware path must store the readout against the right
        molecule."""
        molecule_id = uuid.uuid4()
        reg = f"CC-{uuid.uuid4().hex[:8]}"
        custom_ident = f"SACC-TEST-{uuid.uuid4().hex[:6]}"
        ic50_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

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
            # Identifier differs from the registration number.
            await _insert_molecule(
                seed_uow, molecule_id, workspace_id, reg, identifier=custom_ident
            )
            await seed_uow.commit()

        mapping = SummaryColumnMapping(
            compound_ref="Compound", readout_columns={"IC50": ic50_id}
        )

        # compound_ref carries the CUSTOM identifier, not the reg number.
        result = await _run_import(
            session_factory,
            ImportSummaryFileCommand(
                workspace_id=workspace_id,
                run_id=run_id,
                filename="summary.csv",
                content=f"Compound,IC50\n{custom_ident},4.2\n".encode(),
                mapping=mapping,
            ),
            auth,
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.values_inserted == 1
        assert res.errors == []

        rows = await _wellless(session_factory, workspace_id, run_id)
        assert len(rows) == 1
        # Resolution succeeded via identifier → stored against the right molecule.
        assert rows[0].molecule_id == molecule_id
        assert rows[0].value is not None
        assert rows[0].value.value == 4.2
