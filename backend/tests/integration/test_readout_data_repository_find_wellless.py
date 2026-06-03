"""Integration test: ReadoutDataRepository.find_wellless_by_keys."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.value_objects import QualifiedValue
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_data_repository import (
    SQLAlchemyReadoutDataRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import (
    _insert_org,
    _insert_protocol,
    _insert_readout_def,
    _insert_run,
)


async def _seed_run_and_def(
    uow: AsyncUnitOfWork, *, workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert prerequisite org/protocol/run/readout-def rows.

    Returns ``(run_id, readout_definition_id)``.
    """
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)
    await _insert_run(uow, run_id, protocol_id, workspace_id)
    return run_id, readout_def_id


@pytest.mark.asyncio
class TestFindWelllessByKeys:
    async def test_returns_matching_wellless_row(self, uow, workspace_id):
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=12.5, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=workspace_id,
                run_id=run_id,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
            )

        assert found is not None
        assert found.id == row.id
        assert found.well_id is None
        assert found.molecule_id == molecule_id
        assert found.batch_id == batch_id

    async def test_returns_none_for_non_matching_key(self, uow, workspace_id):
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=12.5, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=workspace_id,
                run_id=run_id,
                molecule_id=uuid.uuid4(),  # different molecule
                batch_id=batch_id,
                readout_definition_id=rd_id,
            )

        assert found is None

    async def test_matches_null_molecule_and_batch_as_is_null(self, uow, workspace_id):
        """None keys must match IS NULL rows, not a row with a populated value."""
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            null_row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=None,
                batch_id=None,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=1.0, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            populated_row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=uuid.uuid4(),
                batch_id=uuid.uuid4(),
                readout_definition_id=rd_id,
                value=QualifiedValue(value=2.0, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(null_row)
            await repo.save(populated_row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=workspace_id,
                run_id=run_id,
                molecule_id=None,
                batch_id=None,
                readout_definition_id=rd_id,
            )

        assert found is not None
        assert found.id == null_row.id

    async def test_ignores_computed_and_welled_rows(self, uow, workspace_id):
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            computed_row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=9.0, qualifier=Qualifier.EQUAL),
                is_computed=True,
            )
            welled_row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=uuid.uuid4(),
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=8.0, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(computed_row)
            await repo.save(welled_row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=workspace_id,
                run_id=run_id,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
            )

        assert found is None

    async def test_returns_none_for_different_workspace(self, uow, workspace_id):
        """Workspace isolation: a row in another workspace must not be returned."""
        other_workspace_id = uuid.uuid4()
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=12.5, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=other_workspace_id,  # different workspace
                run_id=run_id,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
            )

        assert found is None

    async def test_returns_none_for_different_run(self, uow, workspace_id):
        """A row matching everything but run_id must not be returned."""
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=12.5, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=workspace_id,
                run_id=uuid.uuid4(),  # different run
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
            )

        assert found is None

    async def test_returns_none_for_different_readout_definition(self, uow, workspace_id):
        """A row matching everything but readout_definition_id must not be returned."""
        molecule_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        async with uow:
            run_id, rd_id = await _seed_run_and_def(uow, workspace_id=workspace_id)
            row = ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=None,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=12.5, qualifier=Qualifier.EQUAL),
                is_computed=False,
            )
            repo = SQLAlchemyReadoutDataRepository(uow)
            await repo.save(row)
            await uow.commit()

        repo = SQLAlchemyReadoutDataRepository(uow)
        async with uow:
            found = await repo.find_wellless_by_keys(
                workspace_id=workspace_id,
                run_id=run_id,
                molecule_id=molecule_id,
                batch_id=batch_id,
                readout_definition_id=uuid.uuid4(),  # different readout def
            )

        assert found is None
