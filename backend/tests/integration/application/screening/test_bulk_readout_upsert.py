"""Integration test: opt-in upsert mode for BulkCreateReadoutData.

Verifies that ``upsert=True`` overwrites the existing well-less endpoint value
for ``(run_id, molecule_id, batch_id, readout_definition_id)`` instead of
inserting a duplicate, while the default (``upsert=False``) path stays a pure
insert.
"""

from __future__ import annotations

import uuid

from returns.result import Success

from cellar.application.screening.bulk_create_readout_data import (
    BulkCreateReadoutData,
    BulkCreateReadoutDataCommand,
    ReadoutDataItem,
)
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
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
