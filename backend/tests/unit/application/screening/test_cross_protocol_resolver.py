"""Tests for CrossProtocolResolver — @Protocol.Readout formula references."""

from __future__ import annotations

import uuid
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.cross_protocol_resolver import (
    CrossProtocolResolver,
)
from cellar.domain.screening_assay.enums import (
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.value_objects import QualifiedValue

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
USER = uuid.uuid4()
_PH = uuid.UUID(int=0)  # placeholder


def _make_protocol(name: str, readout_defs: list[ReadoutDefinition]) -> Protocol:
    """Build a minimal DRAFT Protocol, then publish to ACTIVE."""
    protocol = Protocol.create(
        workspace_id=WS,
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=readout_defs,
    )
    protocol.publish()  # DRAFT -> ACTIVE
    return protocol


def _make_readout_def(name: str) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=_PH,
        name=name,
        data_type=ReadoutDataType.NUMERIC,
    )


def _make_readout_data(
    molecule_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    value: float,
) -> ReadoutData:
    return ReadoutData(
        workspace_id=WS,
        run_id=uuid.uuid4(),
        molecule_id=molecule_id,
        batch_id=uuid.uuid4(),
        readout_definition_id=readout_definition_id,
        value=QualifiedValue(value=value),
    )


class _FakeUoW:
    async def commit(self) -> list:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


def _make_resolver(protocol_repo=None, readout_data_repo=None) -> CrossProtocolResolver:
    return CrossProtocolResolver(
        uow=_FakeUoW(),
        protocol_repo=protocol_repo or AsyncMock(),
        readout_data_repo=readout_data_repo or AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolvesSimpleReference:
    """Resolve @TargetAssay.IC50 for a molecule with matching readout data."""

    @pytest.mark.asyncio
    async def test_resolves_simple_reference(self) -> None:
        # -- Arrange --
        rd_ic50 = _make_readout_def("IC50")
        protocol = _make_protocol("TargetAssay", [rd_ic50])
        mol_id = uuid.uuid4()

        # Bind readout def id after protocol assigned it
        rd = protocol.readout_definitions[0]

        readout_data = _make_readout_data(mol_id, rd.id, 5.0)

        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_molecule_and_definition.return_value = [readout_data]

        resolver = _make_resolver(protocol_repo, readout_data_repo)

        # -- Act --
        result = await resolver.resolve(WS, mol_id, "@TargetAssay.IC50")

        # -- Assert --
        assert isinstance(result, Success)
        bindings = result.unwrap()
        assert bindings == {"TargetAssay__IC50": 5.0}

        protocol_repo.find_by_name.assert_awaited_once_with(WS, "TargetAssay")
        readout_data_repo.find_by_molecule_and_definition.assert_awaited_once_with(
            WS, mol_id, rd.id
        )


class TestMissingProtocolFails:
    """When no protocol with that name exists, return Failure(NotFoundError)."""

    @pytest.mark.asyncio
    async def test_missing_protocol_fails(self) -> None:
        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = None  # not found

        resolver = _make_resolver(protocol_repo=protocol_repo)

        result = await resolver.resolve(WS, uuid.uuid4(), "@MissingProto.IC50")

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)
        assert "MissingProto" in err.message


class TestInactiveProtocolFails:
    """A DRAFT (non-active) protocol should be treated as not found."""

    @pytest.mark.asyncio
    async def test_inactive_protocol_fails(self) -> None:
        rd = _make_readout_def("IC50")
        # Create a DRAFT protocol (not published)
        draft_protocol = Protocol.create(
            workspace_id=WS,
            name="DraftProto",
            protocol_type=ProtocolType.BIOCHEMICAL,
            created_by=USER,
            readout_definitions=[rd],
        )
        assert draft_protocol.status == ProtocolStatus.DRAFT

        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = draft_protocol

        resolver = _make_resolver(protocol_repo=protocol_repo)

        result = await resolver.resolve(WS, uuid.uuid4(), "@DraftProto.IC50")

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)


class TestNoDataForMoleculeFails:
    """Protocol + readout definition found, but no readout data for the molecule."""

    @pytest.mark.asyncio
    async def test_no_data_for_molecule_fails(self) -> None:
        rd_ic50 = _make_readout_def("IC50")
        protocol = _make_protocol("TargetAssay", [rd_ic50])

        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_molecule_and_definition.return_value = []  # no data

        resolver = _make_resolver(protocol_repo, readout_data_repo)

        result = await resolver.resolve(WS, uuid.uuid4(), "@TargetAssay.IC50")

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "No data" in err.message


class TestNoCrossRefsReturnsEmpty:
    """Formula with no @ references returns Success({}) without hitting repos."""

    @pytest.mark.asyncio
    async def test_no_cross_refs_returns_empty(self) -> None:
        protocol_repo = AsyncMock()
        readout_data_repo = AsyncMock()
        resolver = _make_resolver(protocol_repo, readout_data_repo)

        result = await resolver.resolve(WS, uuid.uuid4(), "a + b")

        assert isinstance(result, Success)
        assert result.unwrap() == {}

        protocol_repo.find_by_name.assert_not_awaited()
        readout_data_repo.find_by_molecule_and_definition.assert_not_awaited()


class TestRewriteFormula:
    """rewrite_formula replaces @Protocol.Readout with Protocol__Readout."""

    def test_rewrite_simple_reference(self) -> None:
        resolver = _make_resolver()
        rewritten = resolver.rewrite_formula("@TargetAssay.IC50 * 2")
        assert rewritten == "TargetAssay__IC50 * 2"

    def test_rewrite_braced_reference(self) -> None:
        resolver = _make_resolver()
        rewritten = resolver.rewrite_formula("@{Target Assay}.{IC50 nM}")
        assert rewritten == "Target Assay__IC50 nM"

    def test_rewrite_multiple_references(self) -> None:
        resolver = _make_resolver()
        rewritten = resolver.rewrite_formula(
            "@ProtoA.ReadoutX + @ProtoB.ReadoutY"
        )
        assert rewritten == "ProtoA__ReadoutX + ProtoB__ReadoutY"

    def test_rewrite_no_refs_unchanged(self) -> None:
        resolver = _make_resolver()
        formula = "a + b * c"
        assert resolver.rewrite_formula(formula) == formula


class TestResolveBracedReference:
    """Resolve @{Protocol Name}.{Readout Name} (braces for names with spaces)."""

    @pytest.mark.asyncio
    async def test_resolves_braced_reference(self) -> None:
        rd_ic50 = _make_readout_def("IC50 nM")
        protocol = _make_protocol("Target Assay", [rd_ic50])
        rd = protocol.readout_definitions[0]
        mol_id = uuid.uuid4()

        readout_data = _make_readout_data(mol_id, rd.id, 12.5)

        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_molecule_and_definition.return_value = [readout_data]

        resolver = _make_resolver(protocol_repo, readout_data_repo)

        result = await resolver.resolve(
            WS, mol_id, "@{Target Assay}.{IC50 nM} + 1"
        )

        assert isinstance(result, Success)
        bindings = result.unwrap()
        assert bindings == {"Target Assay__IC50 nM": 12.5}

        protocol_repo.find_by_name.assert_awaited_once_with(WS, "Target Assay")


class TestDedupReferences:
    """Same @Protocol.Readout appearing twice is resolved only once."""

    @pytest.mark.asyncio
    async def test_dedup_references(self) -> None:
        rd_ic50 = _make_readout_def("IC50")
        protocol = _make_protocol("TargetAssay", [rd_ic50])
        rd = protocol.readout_definitions[0]
        mol_id = uuid.uuid4()

        readout_data = _make_readout_data(mol_id, rd.id, 7.0)

        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_molecule_and_definition.return_value = [readout_data]

        resolver = _make_resolver(protocol_repo, readout_data_repo)

        result = await resolver.resolve(
            WS, mol_id, "@TargetAssay.IC50 + @TargetAssay.IC50"
        )

        assert isinstance(result, Success)
        # find_by_name only called once despite two occurrences
        assert protocol_repo.find_by_name.await_count == 1
        assert result.unwrap() == {"TargetAssay__IC50": 7.0}


class TestMissingReadoutDefinitionFails:
    """Protocol exists but readout name is not in its definitions."""

    @pytest.mark.asyncio
    async def test_missing_readout_definition_fails(self) -> None:
        rd_raw = _make_readout_def("RawSignal")
        protocol = _make_protocol("TargetAssay", [rd_raw])

        protocol_repo = AsyncMock()
        protocol_repo.find_by_name.return_value = protocol

        resolver = _make_resolver(protocol_repo=protocol_repo)

        # Ask for "IC50" which does not exist in this protocol
        result = await resolver.resolve(WS, uuid.uuid4(), "@TargetAssay.IC50")

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)
        assert "IC50" in err.message
