"""Tests for BulkRegistrationService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.bulk_registration_service import (
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
            file_content=b"",
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        result = await service.execute(cmd)
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "Unsupported file format" in str(err)

    async def test_empty_file_returns_failure(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        service = _make_service()
        # Headers only, no data rows
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="empty.csv",
            file_format="csv",
            file_content=b"name,smiles\n",
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        result = await service.execute(cmd)
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "no records" in str(err).lower()

    async def test_csv_with_valid_rows_processes_all(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        uow = _make_uow()
        service = _make_service(uow)

        csv_content = b"name,smiles\nAspirin,CC(=O)Oc1ccccc1C(=O)O\nMethane,C\n"
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            file_content=csv_content,
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        # Mock RegisterMolecule to always succeed with new molecule
        mock_mol = MagicMock()
        mock_mol.id = uuid.uuid4()
        mock_outcome = RegistrationOutcome(molecule=mock_mol, is_new=True)

        with patch(
            "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
        ) as MockRegClass:
            mock_reg = AsyncMock(return_value=Success(mock_outcome))
            MockRegClass.return_value = mock_reg

            result = await service.execute(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.bulk_registration.total_count == 2
        assert outcome.bulk_registration.registered_count == 2
        assert outcome.bulk_registration.error_count == 0
        assert outcome.bulk_registration.status in (
            BulkRegistrationStatus.COMPLETED,
            BulkRegistrationStatus.COMPLETED_WITH_ERRORS,
        )
        assert len(outcome.item_results) == 2
        assert all(item.success for item in outcome.item_results)

    async def test_csv_with_registration_errors(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        uow = _make_uow()
        service = _make_service(uow)

        csv_content = b"name,smiles\nGood,C\nBad,invalid_smiles\n"
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            file_content=csv_content,
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        call_count = 0

        async def _side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_mol = MagicMock()
                mock_mol.id = uuid.uuid4()
                return Success(RegistrationOutcome(molecule=mock_mol, is_new=True))
            return Failure(ValidationError("Invalid SMILES"))

        with patch(
            "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
        ) as MockRegClass:
            mock_reg = AsyncMock(side_effect=_side_effect)
            MockRegClass.return_value = mock_reg

            result = await service.execute(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.bulk_registration.registered_count == 1
        assert outcome.bulk_registration.error_count == 1
        assert outcome.bulk_registration.status == BulkRegistrationStatus.COMPLETED_WITH_ERRORS

    async def test_csv_with_duplicate_detection(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        uow = _make_uow()
        service = _make_service(uow)

        csv_content = b"name,smiles\nAspirin,CC(=O)Oc1ccccc1C(=O)O\nAspirin2,CC(=O)Oc1ccccc1C(=O)O\n"
        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            file_content=csv_content,
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        call_count = 0

        async def _side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            mock_mol = MagicMock()
            mock_mol.id = uuid.uuid4()
            is_new = call_count == 1
            return Success(RegistrationOutcome(molecule=mock_mol, is_new=is_new))

        with patch(
            "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
        ) as MockRegClass:
            mock_reg = AsyncMock(side_effect=_side_effect)
            MockRegClass.return_value = mock_reg

            result = await service.execute(cmd)

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
            file_content=b"name,smiles\nA,C\n",
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        # Auth with viewer role should raise
        from chem_vault.domain.shared.errors import AuthorizationError

        viewer_auth = MagicMock()
        viewer_auth.workspace_id = workspace_id
        viewer_auth.user_id = user_id
        viewer_auth.workspace_role = "viewer"
        viewer_auth.has_role = lambda min_role: False  # viewer < editor

        with pytest.raises(AuthorizationError):
            await service.execute(cmd, auth=viewer_auth)
