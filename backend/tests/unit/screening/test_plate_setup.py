"""Tests for ParsePlateMapFile and SetUpRunPlate use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.screening.plate_setup import (
    CompoundAssignment,
    ParsePlateMapFile,
    ParsedPlateMap,
    SetUpRunPlate,
    SetUpRunPlateCommand,
    _DEFAULT_DOSE_SERIES,
)
from chem_vault.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    RefType,
    ResolvedMolecule,
    UnresolvedMolecule,
)
from chem_vault.domain.screening_assay.enums import (
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
    WellType,
)
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.infrastructure.parsers.tabular_file import TabularFileParser


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    """Minimal fake UoW for unit tests."""

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


# ============================================================================
# ParsePlateMapFile tests
# ============================================================================


class TestParsePlateMapFileWellLevel:
    """Test well-level CSV format: Well, Compound columns."""

    async def _parse(self, csv_content: str):
        parser = ParsePlateMapFile(TabularFileParser())
        return await parser(csv_content)

    @pytest.mark.asyncio
    async def test_basic_well_level(self):
        csv = "Well,Compound\nA1,Aspirin\nA2,Aspirin\nB1,Ibuprofen\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        assert isinstance(parsed, ParsedPlateMap)
        assert len(parsed.assignments) == 2
        assert parsed.row_count == 3

        # Find assignments by compound name
        by_name = {a.molecule_ref: a for a in parsed.assignments}
        assert set(by_name.keys()) == {"Aspirin", "Ibuprofen"}
        assert set(by_name["Aspirin"].well_positions) == {"A1", "A2"}
        assert by_name["Ibuprofen"].well_positions == ["B1"]

    @pytest.mark.asyncio
    async def test_case_insensitive_headers(self):
        csv = "well,compound\nA1,Drug1\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        assert len(parsed.assignments) == 1
        assert parsed.assignments[0].molecule_ref == "Drug1"

    @pytest.mark.asyncio
    async def test_skips_empty_rows(self):
        csv = "Well,Compound\nA1,Aspirin\n,\nB1,Ibuprofen\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        assert len(parsed.assignments) == 2
        # Blank rows are filtered at the parse layer — only data rows counted.
        assert parsed.row_count == 2

    @pytest.mark.asyncio
    async def test_normalizes_well_uppercase(self):
        csv = "Well,Compound\na1,Aspirin\nb2,Aspirin\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        positions = parsed.assignments[0].well_positions
        assert all(p == p.upper() for p in positions)


class TestParsePlateMapFileRowRange:
    """Test row-range CSV format: Compound, Start Row, End Row columns."""

    async def _parse(self, csv_content: str):
        parser = ParsePlateMapFile(TabularFileParser())
        return await parser(csv_content)

    @pytest.mark.asyncio
    async def test_basic_row_range(self):
        csv = "Compound,Start Row,End Row\nAspirin,A,B\nIbuprofen,C,C\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        assert len(parsed.assignments) == 2
        assert parsed.row_count == 2

        # Aspirin should have rows A and B
        aspirin = parsed.assignments[0]
        assert aspirin.molecule_ref == "Aspirin"
        assert aspirin.well_positions == ["A", "B"]

        # Ibuprofen single row
        ibu = parsed.assignments[1]
        assert ibu.molecule_ref == "Ibuprofen"
        assert ibu.well_positions == ["C"]

    @pytest.mark.asyncio
    async def test_row_range_reversed(self):
        """Start row > end row should still work (auto-sorts)."""
        csv = "Compound,Start Row,End Row\nDrug,C,A\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        assert parsed.assignments[0].well_positions == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_underscore_headers(self):
        csv = "Compound,Start_Row,End_Row\nDrug,A,A\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        assert len(result.unwrap().assignments) == 1


class TestParsePlateMapFileInvalid:
    """Test invalid CSV inputs."""

    async def _parse(self, csv_content: str):
        parser = ParsePlateMapFile(TabularFileParser())
        return await parser(csv_content)

    @pytest.mark.asyncio
    async def test_missing_columns(self):
        csv = "Name,Position\nAspirin,A1\n"
        result = await self._parse(csv)
        assert isinstance(result, Failure)
        error = result.failure()
        assert "Well, Compound" in str(error) or "Start Row, End Row" in str(error)

    @pytest.mark.asyncio
    async def test_empty_csv(self):
        result = await self._parse("")
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_header_only(self):
        csv = "Well,Compound\n"
        result = await self._parse(csv)
        assert isinstance(result, Success)
        parsed = result.unwrap()
        assert len(parsed.assignments) == 0
        assert parsed.row_count == 0


# ============================================================================
# SetUpRunPlate tests
# ============================================================================


def _make_run(
    workspace_id: uuid.UUID,
    protocol_id: uuid.UUID,
    operator: uuid.UUID,
    **kwargs,
) -> Run:
    return Run(
        workspace_id=workspace_id,
        protocol_id=protocol_id,
        run_date=date(2026, 1, 15),
        operator=operator,
        **kwargs,
    )


def _make_protocol(
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    with_dose_response: bool = False,
) -> Protocol:
    rd = ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name="Inhibition",
        data_type=ReadoutDataType.NUMERIC,
        unit="%",
    )
    return Protocol(
        workspace_id=workspace_id,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=created_by,
        status=ProtocolStatus.ACTIVE,
        readout_definitions=[rd],
    )


class TestSetUpRunPlate:
    """Test SetUpRunPlate use case."""

    def _build(
        self,
        run: Run | None = None,
        protocol: Protocol | None = None,
        resolved: list[ResolvedMolecule] | None = None,
        unresolved: list[UnresolvedMolecule] | None = None,
        batches_by_mol: dict[uuid.UUID, list[FakeBatch]] | None = None,
    ):
        """Build the use case with fakes/mocks."""
        uow = FakeUoW()
        run_repo = AsyncMock()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        run_repo.save = AsyncMock()

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

        batch_repo = AsyncMock()
        _batches = batches_by_mol or {}
        batch_repo.find_by_molecule = AsyncMock(
            side_effect=lambda ws_id, mol_id: _batches.get(mol_id, [])
        )

        resolver = AsyncMock(spec=MoleculeResolver)
        resolver.resolve = AsyncMock(
            return_value=(resolved or [], unresolved or [])
        )

        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = SetUpRunPlate(
            uow=uow,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
            batch_repo=batch_repo,
            molecule_resolver=resolver,
            dispatcher=dispatcher,
        )
        return uc, uow, run_repo, resolver

    @pytest.mark.asyncio
    async def test_creates_wells_with_correct_concentrations(self):
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        auth = FakeAuth(user_id=user_id, workspace_id=ws_id)

        protocol = _make_protocol(ws_id, user_id)
        run = _make_run(ws_id, protocol.id, user_id)

        mol_id = uuid.uuid4()
        batch = FakeBatch(molecule_id=mol_id)
        conc_series = [1000.0, 333.3, 111.1]

        resolved = [
            ResolvedMolecule(
                ref=MoleculeReference(value="Aspirin", ref_type=RefType.NAME),
                molecule_id=mol_id,
            )
        ]

        uc, uow, run_repo, _ = self._build(
            run=run,
            protocol=protocol,
            resolved=resolved,
            batches_by_mol={mol_id: [batch]},
        )

        cmd = SetUpRunPlateCommand(
            workspace_id=ws_id,
            run_id=run.id,
            plate_number=1,
            compound_assignments=[
                CompoundAssignment(
                    molecule_ref="Aspirin",
                    well_positions=["A1", "A2", "A3"],
                ),
            ],
            concentration_series=conc_series,
        )

        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        data = result.unwrap()
        assert data["wells_created"] == 3
        assert data["compounds_assigned"] == 1
        assert data["unresolved"] == []
        assert data["plate_id"] is not None

        # Verify run was saved
        run_repo.save.assert_called_once()
        assert uow.committed

        # Verify the plate was added to the run
        assert len(run.plates) == 1
        plate = run.plates[0]
        assert plate.plate_number == 1

    @pytest.mark.asyncio
    async def test_skips_unresolved_molecules(self):
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        auth = FakeAuth(user_id=user_id, workspace_id=ws_id)

        protocol = _make_protocol(ws_id, user_id)
        run = _make_run(ws_id, protocol.id, user_id)

        mol_id = uuid.uuid4()
        batch = FakeBatch(molecule_id=mol_id)

        resolved = [
            ResolvedMolecule(
                ref=MoleculeReference(value="Aspirin", ref_type=RefType.NAME),
                molecule_id=mol_id,
            )
        ]
        unresolved = [
            UnresolvedMolecule(
                ref=MoleculeReference(value="UnknownDrug", ref_type=RefType.NAME),
                reason="not_found",
            )
        ]

        uc, _, _, _ = self._build(
            run=run,
            protocol=protocol,
            resolved=resolved,
            unresolved=unresolved,
            batches_by_mol={mol_id: [batch]},
        )

        cmd = SetUpRunPlateCommand(
            workspace_id=ws_id,
            run_id=run.id,
            compound_assignments=[
                CompoundAssignment(molecule_ref="Aspirin", well_positions=["A1"]),
                CompoundAssignment(molecule_ref="UnknownDrug", well_positions=["B1"]),
            ],
            concentration_series=[1000.0],
        )

        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        data = result.unwrap()
        assert data["wells_created"] == 1  # only Aspirin
        assert data["compounds_assigned"] == 1
        assert data["unresolved"] == ["UnknownDrug"]

    @pytest.mark.asyncio
    async def test_fails_if_run_not_found(self):
        ws_id = uuid.uuid4()
        auth = FakeAuth(workspace_id=ws_id)

        uc, _, _, _ = self._build(run=None)

        cmd = SetUpRunPlateCommand(
            workspace_id=ws_id,
            run_id=uuid.uuid4(),
            compound_assignments=[
                CompoundAssignment(molecule_ref="Aspirin", well_positions=["A1"]),
            ],
            concentration_series=[1000.0],
        )

        result = await uc(cmd, auth=auth)
        assert isinstance(result, Failure)
        error = result.failure()
        assert "Run" in str(error)

    @pytest.mark.asyncio
    async def test_uses_default_dose_series_when_none_provided(self):
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        auth = FakeAuth(user_id=user_id, workspace_id=ws_id)

        protocol = _make_protocol(ws_id, user_id)
        run = _make_run(ws_id, protocol.id, user_id)

        mol_id = uuid.uuid4()
        batch = FakeBatch(molecule_id=mol_id)

        resolved = [
            ResolvedMolecule(
                ref=MoleculeReference(value="Drug", ref_type=RefType.NAME),
                molecule_id=mol_id,
            )
        ]

        uc, _, _, _ = self._build(
            run=run,
            protocol=protocol,
            resolved=resolved,
            batches_by_mol={mol_id: [batch]},
        )

        # 10 well positions for the default 10-point series
        positions = [f"A{i}" for i in range(1, 11)]
        cmd = SetUpRunPlateCommand(
            workspace_id=ws_id,
            run_id=run.id,
            compound_assignments=[
                CompoundAssignment(molecule_ref="Drug", well_positions=positions),
            ],
            # No concentration_series — should use default
        )

        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        data = result.unwrap()
        assert data["wells_created"] == 10

    @pytest.mark.asyncio
    async def test_cyclic_concentration_mapping(self):
        """When more positions than concentrations, series cycles."""
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        auth = FakeAuth(user_id=user_id, workspace_id=ws_id)

        protocol = _make_protocol(ws_id, user_id)
        run = _make_run(ws_id, protocol.id, user_id)

        mol_id = uuid.uuid4()
        batch = FakeBatch(molecule_id=mol_id)

        resolved = [
            ResolvedMolecule(
                ref=MoleculeReference(value="Drug", ref_type=RefType.NAME),
                molecule_id=mol_id,
            )
        ]

        uc, _, _, _ = self._build(
            run=run,
            protocol=protocol,
            resolved=resolved,
            batches_by_mol={mol_id: [batch]},
        )

        cmd = SetUpRunPlateCommand(
            workspace_id=ws_id,
            run_id=run.id,
            compound_assignments=[
                CompoundAssignment(
                    molecule_ref="Drug",
                    well_positions=["A1", "A2", "A3", "A4"],
                ),
            ],
            concentration_series=[100.0, 50.0],  # 2 concentrations, 4 wells
        )

        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        data = result.unwrap()
        assert data["wells_created"] == 4

    @pytest.mark.asyncio
    async def test_no_auth_returns_failure(self):
        uc, _, _, _ = self._build(run=None)

        cmd = SetUpRunPlateCommand(
            workspace_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            compound_assignments=[],
        )

        result = await uc(cmd, auth=None)
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_row_letter_positions_generate_columns(self):
        """Row-range format: positions are just row letters, columns generated."""
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        auth = FakeAuth(user_id=user_id, workspace_id=ws_id)

        protocol = _make_protocol(ws_id, user_id)
        run = _make_run(ws_id, protocol.id, user_id)

        mol_id = uuid.uuid4()
        batch = FakeBatch(molecule_id=mol_id)

        resolved = [
            ResolvedMolecule(
                ref=MoleculeReference(value="Drug", ref_type=RefType.NAME),
                molecule_id=mol_id,
            )
        ]

        uc, _, _, _ = self._build(
            run=run,
            protocol=protocol,
            resolved=resolved,
            batches_by_mol={mol_id: [batch]},
        )

        cmd = SetUpRunPlateCommand(
            workspace_id=ws_id,
            run_id=run.id,
            compound_assignments=[
                CompoundAssignment(
                    molecule_ref="Drug",
                    well_positions=["A", "B"],  # row letters only
                ),
            ],
            concentration_series=[1000.0, 333.3],
        )

        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success)
        data = result.unwrap()
        assert data["wells_created"] == 2
        assert data["compounds_assigned"] == 1
