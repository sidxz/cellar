"""Tests for BulkRegistrationService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationItem,
    BulkRegistrationService,
    StartBulkRegistrationCommand,
)
from chem_vault.application.chemical_registration.register_molecule import RegistrationOutcome
from chem_vault.domain.chemical_registration.enums import BulkRegistrationStatus
from chem_vault.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_uow() -> MagicMock:
    uow = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock(return_value=[])
    return uow


def _make_service(uow: MagicMock | None = None) -> BulkRegistrationService:
    return BulkRegistrationService(
        uow=uow or _make_uow(),
        bulk_reg_repo=AsyncMock(),
        mol_repo=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=MagicMock(),
    )


def _items(*names: str) -> list[BulkRegistrationItem]:
    return [
        BulkRegistrationItem(row_index=i, name=n, smiles="C" * (i + 1))
        for i, n in enumerate(names)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBulkRegistrationService:
    async def test_unsupported_format_returns_failure(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        service = _make_service()
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="test.xyz",
            file_format="xyz",
            items=_items("A"),
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        result = await service(cmd)
        assert isinstance(result, Failure)
        assert "Unsupported file format" in str(result.failure())

    async def test_empty_items_returns_failure(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        service = _make_service()
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="empty.csv",
            file_format="csv",
            items=[],
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        result = await service(cmd)
        assert isinstance(result, Failure)
        assert "no records" in str(result.failure()).lower()

    async def test_processes_all_items(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        uow = _make_uow()
        service = _make_service(uow)

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=_items("Aspirin", "Caffeine"),
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        mock_mol = MagicMock()
        mock_mol.id = uuid.uuid4()
        mock_outcome = RegistrationOutcome(molecule=mock_mol, is_new=True)

        with patch(
            "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
        ) as MockRegClass:
            MockRegClass.return_value = AsyncMock(return_value=Success(mock_outcome))
            result = await service(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.bulk_registration.total_count == 2
        assert outcome.bulk_registration.registered_count == 2
        assert len(outcome.item_results) == 2

    async def test_handles_registration_errors(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        uow = _make_uow()
        service = _make_service(uow)

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=_items("Good", "Bad"),
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        call_count = 0

        async def _side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                m = MagicMock()
                m.id = uuid.uuid4()
                return Success(RegistrationOutcome(molecule=m, is_new=True))
            return Failure(ValidationError("Invalid SMILES"))

        with patch(
            "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
        ) as MockRegClass:
            MockRegClass.return_value = AsyncMock(side_effect=_side_effect)
            result = await service(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.bulk_registration.registered_count == 1
        assert outcome.bulk_registration.error_count == 1
        assert outcome.bulk_registration.status == BulkRegistrationStatus.COMPLETED_WITH_ERRORS

    async def test_detects_duplicates(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        uow = _make_uow()
        service = _make_service(uow)

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=_items("Aspirin", "Aspirin2"),
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        call_count = 0

        async def _side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.id = uuid.uuid4()
            return Success(RegistrationOutcome(molecule=m, is_new=call_count == 1))

        with patch(
            "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
        ) as MockRegClass:
            MockRegClass.return_value = AsyncMock(side_effect=_side_effect)
            result = await service(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.bulk_registration.registered_count == 1
        assert outcome.bulk_registration.duplicate_count == 1

    async def test_requires_editor_permission(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        service = _make_service()
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=_items("A"),
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        from chem_vault.domain.shared.errors import AuthorizationError

        viewer_auth = MagicMock()
        viewer_auth.workspace_id = workspace_id
        viewer_auth.user_id = user_id
        viewer_auth.workspace_role = "viewer"
        viewer_auth.has_role = lambda min_role: False

        with pytest.raises(AuthorizationError):
            await service(cmd, auth=viewer_auth)
