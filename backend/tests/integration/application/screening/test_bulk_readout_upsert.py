"""Integration test: opt-in upsert mode for BulkCreateReadoutData.

Verifies that ``upsert=True`` overwrites the existing well-less endpoint value
for ``(run_id, molecule_id, batch_id, readout_definition_id)`` instead of
inserting a duplicate, while the default (``upsert=False``) path stays a pure
insert.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from returns.result import Success

from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
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
    _insert_readout_def,
    _insert_run,
)


class _NoOpDispatcher:
    async def dispatch_all(self, events: list) -> None:
        return None


async def _seed_run_and_def(
    uow: AsyncUnitOfWork, *, workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)
    await _insert_run(uow, run_id, protocol_id, workspace_id)
    return run_id, readout_def_id


def _build_use_case(uow: AsyncUnitOfWork) -> BulkCreateReadoutData:
    run_repo = SQLAlchemyRunRepository(uow)
    return BulkCreateReadoutData(
        uow=uow,
        repo=SQLAlchemyReadoutDataRepository(uow),
        guard=DataLockGuard(run_repo),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
        run_repo=run_repo,
        protocol_repo=SQLAlchemyProtocolRepository(uow),
    )


def _build_use_case_with_molecules(uow: AsyncUnitOfWork) -> BulkCreateReadoutData:
    run_repo = SQLAlchemyRunRepository(uow)
    return BulkCreateReadoutData(
        uow=uow,
        repo=SQLAlchemyReadoutDataRepository(uow),
        guard=DataLockGuard(run_repo),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
        molecule_repo=SQLAlchemyMoleculeRepository(uow),
        run_repo=run_repo,
        protocol_repo=SQLAlchemyProtocolRepository(uow),
    )


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID, reg: str
) -> None:
    """Insert a registered molecule, ensuring an originating org exists."""
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


def _item(
    *,
    run_id: uuid.UUID,
    molecule_id: uuid.UUID,
    batch_id: uuid.UUID,
    readout_def_id: uuid.UUID,
    value: float,
) -> ReadoutDataItem:
    return ReadoutDataItem(
        run_id=run_id,
        well_id=None,
        molecule_id=molecule_id,
        batch_id=batch_id,
        readout_definition_id=readout_def_id,
        value_numeric=value,
    )


class TestBulkCreateReadoutDataUpsert:
    async def test_upsert_overwrites_existing_wellless_row(
        self, session_factory, workspace_id
    ) -> None:
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        # Seed prerequisites in their own committed transaction.
        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, rd_id = await _seed_run_and_def(seed_uow, workspace_id=workspace_id)
            await seed_uow.commit()

        # First import (upsert=True) — inserts.
        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        first = await uc(
            BulkCreateReadoutDataCommand(
                workspace_id=workspace_id,
                items=[
                    _item(
                        run_id=run_id,
                        molecule_id=molecule_id,
                        batch_id=batch_id,
                        readout_def_id=rd_id,
                        value=10.0,
                    )
                ],
            ),
            auth=auth,
            upsert=True,
        )
        assert isinstance(first, Success)
        assert first.unwrap().success_count == 1

        # Second import of the SAME key with a different value (upsert=True) — overwrites.
        uc = _build_use_case(AsyncUnitOfWork(session_factory))
        second = await uc(
            BulkCreateReadoutDataCommand(
                workspace_id=workspace_id,
                items=[
                    _item(
                        run_id=run_id,
                        molecule_id=molecule_id,
                        batch_id=batch_id,
                        readout_def_id=rd_id,
                        value=42.0,
                    )
                ],
            ),
            auth=auth,
            upsert=True,
        )
        assert isinstance(second, Success)
        assert second.unwrap().success_count == 1

        # Exactly ONE well-less, non-computed row exists, with the latest value.
        check_uow = AsyncUnitOfWork(session_factory)
        async with check_uow:
            repo = SQLAlchemyReadoutDataRepository(check_uow)
            rows = await repo.find_by_run(workspace_id, run_id)
            wellless = [r for r in rows if r.well_id is None and not r.is_computed]
            assert len(wellless) == 1
            assert wellless[0].value is not None
            assert wellless[0].value.value == 42.0

    async def test_default_path_inserts_duplicate(
        self, session_factory, workspace_id
    ) -> None:
        """Without upsert, re-importing the same key inserts a second row."""
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, rd_id = await _seed_run_and_def(seed_uow, workspace_id=workspace_id)
            await seed_uow.commit()

        for value in (10.0, 42.0):
            uc = _build_use_case(AsyncUnitOfWork(session_factory))
            result = await uc(
                BulkCreateReadoutDataCommand(
                    workspace_id=workspace_id,
                    items=[
                        _item(
                            run_id=run_id,
                            molecule_id=molecule_id,
                            batch_id=batch_id,
                            readout_def_id=rd_id,
                            value=value,
                        )
                    ],
                ),
                auth=auth,
                # upsert defaults to False
            )
            assert isinstance(result, Success)

        check_uow = AsyncUnitOfWork(session_factory)
        async with check_uow:
            repo = SQLAlchemyReadoutDataRepository(check_uow)
            rows = await repo.find_by_run(workspace_id, run_id)
            wellless = [r for r in rows if r.well_id is None and not r.is_computed]
            assert len(wellless) == 2


class TestBulkCreateReadoutDataRequireBatch:
    async def test_require_batch_false_stores_compound_only_row(
        self, session_factory, workspace_id
    ) -> None:
        """require_batch=False + molecule (reg #) and no batch → stores batch_id NULL row."""
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, rd_id = await _seed_run_and_def(seed_uow, workspace_id=workspace_id)
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        uc = _build_use_case_with_molecules(AsyncUnitOfWork(session_factory))
        result = await uc(
            BulkCreateReadoutDataCommand(
                workspace_id=workspace_id,
                items=[
                    ReadoutDataItem(
                        run_id=run_id,
                        registration_number=reg,
                        readout_definition_id=rd_id,
                        value_numeric=7.5,
                    )
                ],
            ),
            auth=auth,
            require_batch=False,
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.success_count == 1
        assert res.error_count == 0

        check_uow = AsyncUnitOfWork(session_factory)
        async with check_uow:
            repo = SQLAlchemyReadoutDataRepository(check_uow)
            rows = await repo.find_by_run(workspace_id, run_id)
            wellless = [r for r in rows if r.well_id is None and not r.is_computed]
            assert len(wellless) == 1
            assert wellless[0].batch_id is None
            assert wellless[0].molecule_id == molecule_id
            assert wellless[0].value is not None
            assert wellless[0].value.value == 7.5

    async def test_require_batch_false_neither_molecule_nor_batch_errors(
        self, session_factory, workspace_id
    ) -> None:
        """require_batch=False + item with neither molecule nor batch → reported, not stored."""
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, rd_id = await _seed_run_and_def(seed_uow, workspace_id=workspace_id)
            await seed_uow.commit()

        uc = _build_use_case_with_molecules(AsyncUnitOfWork(session_factory))
        result = await uc(
            BulkCreateReadoutDataCommand(
                workspace_id=workspace_id,
                items=[
                    ReadoutDataItem(
                        run_id=run_id,
                        readout_definition_id=rd_id,
                        value_numeric=1.0,
                    )
                ],
            ),
            auth=auth,
            require_batch=False,
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.success_count == 0
        assert res.error_count == 1
        assert "molecule or batch" in res.errors[0]["error"]

        check_uow = AsyncUnitOfWork(session_factory)
        async with check_uow:
            repo = SQLAlchemyReadoutDataRepository(check_uow)
            rows = await repo.find_by_run(workspace_id, run_id)
            wellless = [r for r in rows if r.well_id is None and not r.is_computed]
            assert len(wellless) == 0

    async def test_default_still_requires_batch(self, session_factory, workspace_id) -> None:
        """Default (require_batch omitted) + item with no batch → still an error."""
        molecule_id = uuid.uuid4()
        reg = f"REG-{uuid.uuid4().hex[:8]}"
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        seed_uow = AsyncUnitOfWork(session_factory)
        async with seed_uow:
            run_id, rd_id = await _seed_run_and_def(seed_uow, workspace_id=workspace_id)
            await _insert_molecule(seed_uow, molecule_id, workspace_id, reg)
            await seed_uow.commit()

        uc = _build_use_case_with_molecules(AsyncUnitOfWork(session_factory))
        result = await uc(
            BulkCreateReadoutDataCommand(
                workspace_id=workspace_id,
                items=[
                    ReadoutDataItem(
                        run_id=run_id,
                        registration_number=reg,
                        readout_definition_id=rd_id,
                        value_numeric=1.0,
                    )
                ],
            ),
            auth=auth,
            # require_batch omitted → defaults to True
        )
        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.success_count == 0
        assert res.error_count == 1
        assert "batch_id or batch_number is required" in res.errors[0]["error"]

        check_uow = AsyncUnitOfWork(session_factory)
        async with check_uow:
            repo = SQLAlchemyReadoutDataRepository(check_uow)
            rows = await repo.find_by_run(workspace_id, run_id)
            wellless = [r for r in rows if r.well_id is None and not r.is_computed]
            assert len(wellless) == 0
