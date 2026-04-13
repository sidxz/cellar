"""Unit tests for ImportRunReadouts use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.screening.import_run_readouts import (
    ImportRunReadouts,
    ImportRunReadoutsCommand,
    ImportRunReadoutsResult,
)
from chem_vault.domain.screening_assay.enums import (
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
    WellType,
)
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from chem_vault.domain.screening_assay.run import Plate, Run, Well
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    """Minimal fake UoW."""

    def __init__(self):
        self.committed = False
        self.is_active = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        self.is_active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.is_active = False


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


@dataclass
class FakeBatch:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    molecule_id: uuid.UUID = field(default_factory=uuid.uuid4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws_and_auth() -> tuple[uuid.UUID, FakeAuth]:
    ws_id = uuid.uuid4()
    return ws_id, FakeAuth(workspace_id=ws_id)


def _make_run_with_wells(
    workspace_id: uuid.UUID,
    wells: list[Well] | None = None,
) -> Run:
    protocol_id = uuid.uuid4()
    run = Run(
        workspace_id=workspace_id,
        protocol_id=protocol_id,
        run_date=date(2026, 1, 15),
        operator=uuid.uuid4(),
        plates=[],
        wells=wells or [],
    )
    return run


def _make_protocol(
    workspace_id: uuid.UUID,
    readout_names: list[str] | None = None,
) -> Protocol:
    names = readout_names or ["% Inhibition"]
    rd_list = [
        ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name=name,
            data_type=ReadoutDataType.NUMERIC,
        )
        for name in names
    ]
    return Protocol(
        workspace_id=workspace_id,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        status=ProtocolStatus.ACTIVE,
        readout_definitions=rd_list,
    )


def _make_well(
    plate_id: uuid.UUID,
    row: str,
    column: int,
    batch_id: uuid.UUID | None = None,
) -> Well:
    return Well(
        plate_id=plate_id,
        row=row,
        column=column,
        batch_id=batch_id,
    )


def _build_use_case(
    run: Run | None = None,
    protocol: Protocol | None = None,
    batch: FakeBatch | None = None,
    save_bulk_called: list | None = None,
) -> tuple[ImportRunReadouts, FakeUoW, AsyncMock]:
    uow = FakeUoW()

    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)

    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

    readout_data_repo = AsyncMock()
    _saved: list = save_bulk_called if save_bulk_called is not None else []

    async def _save_bulk(entities):
        _saved.extend(entities)

    readout_data_repo.save_bulk = _save_bulk

    batch_repo = AsyncMock()
    batch_repo.find_by_id_in_workspace = AsyncMock(return_value=batch)

    uc = ImportRunReadouts(
        uow=uow,
        run_repo=run_repo,
        protocol_repo=protocol_repo,
        readout_data_repo=readout_data_repo,
        batch_repo=batch_repo,
    )
    return uc, uow, run_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImportRunReadouts:

    @pytest.mark.asyncio
    async def test_successful_single_value_import(self):
        """CSV with Well + Value columns, readout_definition_id supplied."""
        ws_id, auth = _make_ws_and_auth()

        plate_id = uuid.uuid4()
        batch = FakeBatch()
        wells = [
            _make_well(plate_id, "A", 1, batch_id=batch.id),
            _make_well(plate_id, "A", 2, batch_id=batch.id),
        ]
        run = _make_run_with_wells(ws_id, wells)
        protocol = _make_protocol(ws_id, ["% Inhibition"])
        rd_id = protocol.readout_definitions[0].id

        saved: list = []
        uc, uow, _ = _build_use_case(
            run=run,
            protocol=protocol,
            batch=batch,
            save_bulk_called=saved,
        )

        csv_bytes = b"Well,Value\nA1,2.3\nA2,5.1\n"
        cmd = ImportRunReadoutsCommand(
            workspace_id=ws_id,
            run_id=run.id,
            csv_content=csv_bytes,
            readout_definition_id=rd_id,
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success), result
        res: ImportRunReadoutsResult = result.unwrap()
        assert res.total_rows == 2
        assert res.matched == 2
        assert res.unmatched == 0
        assert res.readouts_created == 2
        assert len(saved) == 2
        assert uow.committed

        # Verify ReadoutData entities are correctly populated
        for entity in saved:
            assert entity.workspace_id == ws_id
            assert entity.run_id == run.id
            assert entity.readout_definition_id == rd_id
            assert entity.batch_id == batch.id
            assert entity.molecule_id == batch.molecule_id
            assert entity.value is not None

    @pytest.mark.asyncio
    async def test_unmatched_wells_are_counted(self):
        """CSV rows that don't match any run well are counted as unmatched."""
        ws_id, auth = _make_ws_and_auth()

        plate_id = uuid.uuid4()
        batch = FakeBatch()
        wells = [_make_well(plate_id, "A", 1, batch_id=batch.id)]
        run = _make_run_with_wells(ws_id, wells)
        protocol = _make_protocol(ws_id, ["% Inhibition"])
        rd_id = protocol.readout_definitions[0].id

        saved: list = []
        uc, _, _ = _build_use_case(
            run=run, protocol=protocol, batch=batch, save_bulk_called=saved
        )

        # A1 matches, B1 and C3 do not
        csv_bytes = b"Well,Value\nA1,2.3\nB1,5.1\nC3,9.9\n"
        cmd = ImportRunReadoutsCommand(
            workspace_id=ws_id,
            run_id=run.id,
            csv_content=csv_bytes,
            readout_definition_id=rd_id,
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.total_rows == 3
        assert res.matched == 1
        assert res.unmatched == 2
        assert res.readouts_created == 1

    @pytest.mark.asyncio
    async def test_run_with_no_wells_returns_validation_error(self):
        """A run with empty wells list should fail with ValidationError."""
        ws_id, auth = _make_ws_and_auth()

        # Run has no wells at all
        run = _make_run_with_wells(ws_id, wells=[])
        protocol = _make_protocol(ws_id)

        uc, _, _ = _build_use_case(run=run, protocol=protocol)

        cmd = ImportRunReadoutsCommand(
            workspace_id=ws_id,
            run_id=run.id,
            csv_content=b"Well,Value\nA1,2.3\n",
            readout_definition_id=uuid.uuid4(),
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        error = result.failure()
        assert isinstance(error, ValidationError)
        assert "no wells" in str(error).lower()

    @pytest.mark.asyncio
    async def test_run_not_found_returns_not_found_error(self):
        """When run_repo returns None, a NotFoundError is returned."""
        ws_id, auth = _make_ws_and_auth()

        uc, _, _ = _build_use_case(run=None, protocol=None)

        cmd = ImportRunReadoutsCommand(
            workspace_id=ws_id,
            run_id=uuid.uuid4(),
            csv_content=b"Well,Value\nA1,2.3\n",
            readout_definition_id=uuid.uuid4(),
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        error = result.failure()
        assert isinstance(error, NotFoundError)
        assert "Run" in str(error)

    @pytest.mark.asyncio
    async def test_multiple_readout_columns(self):
        """CSV with multiple value columns matched by name to protocol readouts."""
        ws_id, auth = _make_ws_and_auth()

        plate_id = uuid.uuid4()
        batch = FakeBatch()
        wells = [
            _make_well(plate_id, "A", 1, batch_id=batch.id),
            _make_well(plate_id, "A", 2, batch_id=batch.id),
        ]
        run = _make_run_with_wells(ws_id, wells)
        protocol = _make_protocol(ws_id, ["% Inhibition", "Absorbance"])
        inh_id = protocol.readout_definitions[0].id
        abs_id = protocol.readout_definitions[1].id

        saved: list = []
        uc, _, _ = _build_use_case(
            run=run, protocol=protocol, batch=batch, save_bulk_called=saved
        )

        csv_bytes = b"Well,% Inhibition,Absorbance\nA1,2.3,0.95\nA2,5.1,0.88\n"
        cmd = ImportRunReadoutsCommand(
            workspace_id=ws_id,
            run_id=run.id,
            csv_content=csv_bytes,
            # No readout_definition_id — columns resolved by name
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        res = result.unwrap()
        assert res.total_rows == 2
        assert res.matched == 2
        assert res.readouts_created == 4  # 2 wells × 2 columns

        # Each entity should have correct rd_id
        rd_ids = {e.readout_definition_id for e in saved}
        assert inh_id in rd_ids
        assert abs_id in rd_ids

    @pytest.mark.asyncio
    async def test_viewer_role_returns_authorization_failure(self):
        """Users with viewer role (below editor) cannot import readout data."""
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id, workspace_role="viewer")

        plate_id = uuid.uuid4()
        batch = FakeBatch()
        wells = [_make_well(plate_id, "A", 1, batch_id=batch.id)]
        run = _make_run_with_wells(ws_id, wells)
        protocol = _make_protocol(ws_id)
        rd_id = protocol.readout_definitions[0].id

        uc, _, _ = _build_use_case(run=run, protocol=protocol, batch=batch)

        cmd = ImportRunReadoutsCommand(
            workspace_id=ws_id,
            run_id=run.id,
            csv_content=b"Well,Value\nA1,2.3\n",
            readout_definition_id=rd_id,
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        from chem_vault.domain.shared.errors import AuthorizationError
        assert isinstance(result.failure(), AuthorizationError)
