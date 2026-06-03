"""Integration test: PreviewSummaryFile parses a wide file + suggests roles.

Seeds a protocol with two readout definitions (IC50 numeric, Notes text) and a
run under it, then previews a CSV whose columns are ``Compound,IC50,Notes``.
Asserts the suggested roles: Compound -> compound_ref, IC50/Notes -> readout
(with a non-null readout_definition_id), and the row count.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from returns.result import Failure, Success

from cellar.application.screening.preview_summary_file import PreviewSummaryFile
from cellar.application.screening.summary_import_models import SummaryRole
from cellar.infrastructure.parsers.tabular_file import TabularFileParser
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import _insert_org, _insert_protocol, _insert_run


async def _insert_named_readout_def(
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
            "VALUES (:id, :proto, :name, :data_type, :display_order, false)"
        ),
        {
            "id": rd_id,
            "proto": protocol_id,
            "name": name,
            "data_type": data_type,
            "display_order": display_order,
        },
    )


async def _seed(
    uow: AsyncUnitOfWork, *, workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    ic50_id = uuid.uuid4()
    notes_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_named_readout_def(
        uow, ic50_id, protocol_id, name="IC50", data_type="numeric", display_order=0
    )
    await _insert_named_readout_def(
        uow, notes_id, protocol_id, name="Notes", data_type="text", display_order=1
    )
    await _insert_run(uow, run_id, protocol_id, workspace_id)
    return run_id, ic50_id, notes_id


def _build_use_case(uow: AsyncUnitOfWork) -> PreviewSummaryFile:
    # The use case now owns + enters ``uow`` itself; the caller no longer wraps
    # it in ``async with`` (the route's only job is ``await uc(...)``).
    return PreviewSummaryFile(
        uow=uow,
        run_repo=SQLAlchemyRunRepository(uow),
        protocol_repo=SQLAlchemyProtocolRepository(uow),
        parser=TabularFileParser(),
    )


_CSV = (
    b"Compound,IC50,Notes\n"
    b"CMP-1,5.2,clean\n"
    b"CMP-2,12.7,noisy\n"
    b"CMP-3,0.8,clean\n"
)


class TestPreviewSummaryFile:
    async def test_suggests_compound_ref_and_readouts(
        self, session_factory, workspace_id
    ) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, ic50_id, notes_id = await _seed(seed_uow, workspace_id=workspace_id)
            await seed_uow.commit()

        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        result = await uc(
            workspace_id=workspace_id,
            run_id=run_id,
            filename="summary.csv",
            content=_CSV,
            auth=auth,
        )

        assert isinstance(result, Success)
        preview = result.unwrap()

        assert preview.headers == ["Compound", "IC50", "Notes"]
        assert preview.total_rows == 3
        assert len(preview.sample_rows) == 3

        by_header = {s.header: s for s in preview.suggestions}

        compound = by_header["Compound"]
        assert compound.role == SummaryRole.COMPOUND_REF
        assert compound.confidence == "high"

        ic50 = by_header["IC50"]
        assert ic50.role == SummaryRole.READOUT
        assert ic50.readout_definition_id == ic50_id

        notes = by_header["Notes"]
        assert notes.role == SummaryRole.READOUT
        assert notes.readout_definition_id == notes_id

    async def test_unmatched_column_suggests_ignore(
        self, session_factory, workspace_id
    ) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, _ic50_id, _notes_id = await _seed(
                seed_uow, workspace_id=workspace_id
            )
            await seed_uow.commit()

        csv = b"Compound,Solvent\nCMP-1,DMSO\nCMP-2,water\n"

        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        result = await uc(
            workspace_id=workspace_id,
            run_id=run_id,
            filename="summary.csv",
            content=csv,
            auth=auth,
        )

        assert isinstance(result, Success)
        by_header = {s.header: s for s in result.unwrap().suggestions}

        solvent = by_header["Solvent"]
        assert solvent.role == SummaryRole.IGNORE
        assert solvent.confidence == "low"
        assert solvent.note == "no confident role match"

    async def test_batch_column_suggests_batch_ref(
        self, session_factory, workspace_id
    ) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, _ic50_id, _notes_id = await _seed(
                seed_uow, workspace_id=workspace_id
            )
            await seed_uow.commit()

        csv = b"Batch,IC50\nB-1,5.2\nB-2,12.7\n"

        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        result = await uc(
            workspace_id=workspace_id,
            run_id=run_id,
            filename="summary.csv",
            content=csv,
            auth=auth,
        )

        assert isinstance(result, Success)
        by_header = {s.header: s for s in result.unwrap().suggestions}

        batch = by_header["Batch"]
        assert batch.role == SummaryRole.BATCH_REF
        assert batch.confidence == "high"

    async def test_readout_name_takes_precedence_over_compound_family(
        self, session_factory, workspace_id
    ) -> None:
        # "Name" is in the compound-header family, but a readout def named
        # "Name" must win: readout matching gates ahead of the compound family.
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        org_id = uuid.uuid4()
        protocol_id = uuid.uuid4()
        run_id = uuid.uuid4()
        name_rd_id = uuid.uuid4()

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            await _insert_org(seed_uow, org_id, workspace_id)
            await _insert_protocol(seed_uow, protocol_id, workspace_id)
            await _insert_named_readout_def(
                seed_uow,
                name_rd_id,
                protocol_id,
                name="Name",
                data_type="text",
                display_order=0,
            )
            await _insert_run(seed_uow, run_id, protocol_id, workspace_id)
            await seed_uow.commit()

        csv = b"Name\nfoo\nbar\n"

        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        result = await uc(
            workspace_id=workspace_id,
            run_id=run_id,
            filename="summary.csv",
            content=csv,
            auth=auth,
        )

        assert isinstance(result, Success)
        by_header = {s.header: s for s in result.unwrap().suggestions}

        name = by_header["Name"]
        assert name.role == SummaryRole.READOUT
        assert name.readout_definition_id == name_rd_id

    async def test_missing_run_returns_not_found(
        self, session_factory, workspace_id
    ) -> None:
        auth = FakeAuth(role="editor", workspace_id=workspace_id)
        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        result = await uc(
            workspace_id=workspace_id,
            run_id=uuid.uuid4(),
            filename="summary.csv",
            content=_CSV,
            auth=auth,
        )
        assert isinstance(result, Failure)
