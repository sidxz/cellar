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
from chem_vault.application.chemical_registration.protocols import DetectedSaltDTO
from chem_vault.application.chemical_registration.register_molecule import RegistrationOutcome
from chem_vault.domain.chemical_registration.enums import BulkRegistrationStatus
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import BatchNumber


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


def _make_salt_matcher() -> AsyncMock:
    matcher = AsyncMock()
    matcher.match_by_code = AsyncMock(return_value=None)
    matcher.match_by_smiles = AsyncMock(return_value=None)
    return matcher


def _make_service(
    uow: MagicMock | None = None,
    salt_matcher: AsyncMock | None = None,
    batch_repo: AsyncMock | None = None,
) -> BulkRegistrationService:
    return BulkRegistrationService(
        uow=uow or _make_uow(),
        bulk_reg_repo=AsyncMock(),
        mol_repo=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=MagicMock(),
        salt_matcher=salt_matcher or _make_salt_matcher(),
        batch_repo=batch_repo or AsyncMock(),
    )


def _items(*names: str) -> list[BulkRegistrationItem]:
    return [
        BulkRegistrationItem(row_index=i, name=n, smiles="C" * (i + 1))
        for i, n in enumerate(names)
    ]


def _mock_batch(batch_id: uuid.UUID | None = None) -> MagicMock:
    """Create a mock Batch with proper batch_number."""
    batch = MagicMock()
    batch.id = batch_id or uuid.uuid4()
    batch.batch_number = BatchNumber(value="CV-00001-001")
    return batch


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
        mock_batch = _mock_batch()

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(return_value=Success(mock_outcome))
            MockBatchClass.return_value = AsyncMock(return_value=Success(mock_batch))
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

        mock_batch = _mock_batch()

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(side_effect=_side_effect)
            MockBatchClass.return_value = AsyncMock(return_value=Success(mock_batch))
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

        mock_batch = _mock_batch()

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(side_effect=_side_effect)
            MockBatchClass.return_value = AsyncMock(return_value=Success(mock_batch))
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


class TestBulkRegistrationBatchCreation:
    """Tests for batch creation during bulk registration."""

    async def test_successful_registration_creates_batch(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """Verify that a successful molecule registration also creates a batch."""
        uow = _make_uow()
        salt_matcher = _make_salt_matcher()
        service = _make_service(uow, salt_matcher=salt_matcher)

        items = [
            BulkRegistrationItem(
                row_index=0,
                name="Aspirin",
                smiles="CC(=O)Oc1ccccc1C(O)=O",
                amount_value=100.0,
                amount_unit="mg",
                purity=99.5,
                batch_source="synthesized",
                appearance="white powder",
            )
        ]

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=items,
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        mock_mol = MagicMock()
        mock_mol.id = uuid.uuid4()
        mock_mol.descriptors = None
        mock_outcome = RegistrationOutcome(molecule=mock_mol, is_new=True)

        batch_id = uuid.uuid4()
        mock_batch = _mock_batch(batch_id)

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(return_value=Success(mock_outcome))
            mock_create_batch = AsyncMock(return_value=Success(mock_batch))
            MockBatchClass.return_value = mock_create_batch
            result = await service(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert len(outcome.item_results) == 1

        item_result = outcome.item_results[0]
        assert item_result.success is True
        assert item_result.batch_id == batch_id
        assert item_result.batch_number == "CV-00001-001"

        # Verify CreateBatch was called with the correct command
        mock_create_batch.assert_called_once()
        batch_cmd = mock_create_batch.call_args[0][0]
        assert batch_cmd.workspace_id == workspace_id
        assert batch_cmd.molecule_id == mock_mol.id
        assert batch_cmd.amount_value == 100.0
        assert batch_cmd.amount_unit == "mg"
        assert batch_cmd.purity == 99.5
        assert batch_cmd.source == "synthesized"
        assert batch_cmd.appearance == "white powder"

    async def test_salt_code_triggers_match_by_code(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """Verify explicit salt_code in import row triggers match_by_code."""
        uow = _make_uow()
        salt_matcher = _make_salt_matcher()

        # Set up salt entry mock
        salt_entry = MagicMock()
        salt_entry.id = uuid.uuid4()
        salt_entry.name = "Hydrochloride"
        salt_entry.smiles = "[Cl-]"
        salt_entry.molecular_weight = 36.46
        salt_matcher.match_by_code = AsyncMock(return_value=salt_entry)

        service = _make_service(uow, salt_matcher=salt_matcher)

        items = [
            BulkRegistrationItem(
                row_index=0,
                name="Aspirin HCl",
                smiles="CC(=O)Oc1ccccc1C(O)=O",
                salt_code="HCl",
                salt_stoichiometry=1,
                amount_value=50.0,
            )
        ]

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=items,
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        mock_mol = MagicMock()
        mock_mol.id = uuid.uuid4()
        mock_mol.descriptors = MagicMock()
        mock_mol.descriptors.molecular_weight = 180.16
        mock_outcome = RegistrationOutcome(molecule=mock_mol, is_new=True)

        mock_batch = _mock_batch()

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(return_value=Success(mock_outcome))
            mock_create_batch = AsyncMock(return_value=Success(mock_batch))
            MockBatchClass.return_value = mock_create_batch
            result = await service(cmd)

        assert isinstance(result, Success)
        item_result = result.unwrap().item_results[0]
        assert item_result.salt_matched is True

        # Verify salt matcher was called with the code
        salt_matcher.match_by_code.assert_called_once_with(workspace_id, "HCl")

        # Verify batch was created with salt info
        batch_cmd = mock_create_batch.call_args[0][0]
        assert batch_cmd.salt_entry_id == salt_entry.id
        assert batch_cmd.salt_name == "Hydrochloride"
        assert batch_cmd.salt_smiles == "[Cl-]"
        # formula_weight = parent_mw + salt_mw * stoichiometry = 180.16 + 36.46
        assert batch_cmd.formula_weight == pytest.approx(216.62)

    async def test_detected_salt_triggers_match_by_smiles(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """Verify auto-detected salt from structure processing triggers match_by_smiles."""
        uow = _make_uow()
        salt_matcher = _make_salt_matcher()

        salt_entry = MagicMock()
        salt_entry.id = uuid.uuid4()
        salt_entry.name = "Sodium"
        salt_entry.smiles = "[Na+]"
        salt_entry.molecular_weight = 22.99
        salt_matcher.match_by_smiles = AsyncMock(return_value=salt_entry)

        service = _make_service(uow, salt_matcher=salt_matcher)

        items = [
            BulkRegistrationItem(
                row_index=0,
                name="Naproxen Na",
                smiles="COc1ccc2cc(CC(=O)[O-])ccc2c1.[Na+]",
                amount_value=25.0,
            )
        ]

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=items,
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        mock_mol = MagicMock()
        mock_mol.id = uuid.uuid4()
        mock_mol.descriptors = MagicMock()
        mock_mol.descriptors.molecular_weight = 230.26
        detected_salt = DetectedSaltDTO(
            salt_smiles="[Na+]", salt_fragment_mw=22.99, stoichiometry=1
        )
        mock_outcome = RegistrationOutcome(
            molecule=mock_mol, is_new=True, detected_salt=detected_salt
        )

        mock_batch = _mock_batch()

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(return_value=Success(mock_outcome))
            mock_create_batch = AsyncMock(return_value=Success(mock_batch))
            MockBatchClass.return_value = mock_create_batch
            result = await service(cmd)

        assert isinstance(result, Success)
        item_result = result.unwrap().item_results[0]
        assert item_result.salt_matched is True

        # match_by_smiles should be called (not match_by_code, since no salt_code)
        salt_matcher.match_by_code.assert_not_called()
        salt_matcher.match_by_smiles.assert_called_once_with(workspace_id, "[Na+]")

        batch_cmd = mock_create_batch.call_args[0][0]
        assert batch_cmd.salt_entry_id == salt_entry.id
        assert batch_cmd.salt_stoichiometry == 1

    async def test_batch_creation_failure_reports_per_row_error(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """Batch creation failure is surfaced on the row result.

        The molecule is registered (the bulk-reg aggregate counts it), but
        the per-row result flips ``success=False`` with ``batch_error``
        populated so operators can see what went wrong.
        """
        uow = _make_uow()
        service = _make_service(uow)

        cmd = StartBulkRegistrationCommand(
            workspace_id=workspace_id,
            source_file="compounds.csv",
            file_format="csv",
            items=_items("Aspirin"),
            submitted_by=user_id,
            originating_org_id=org_id,
        )

        mock_mol = MagicMock()
        mock_mol.id = uuid.uuid4()
        mock_mol.descriptors = None
        mock_outcome = RegistrationOutcome(molecule=mock_mol, is_new=True)

        with (
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.RegisterMolecule"
            ) as MockRegClass,
            patch(
                "chem_vault.application.chemical_registration.bulk_registration_service.CreateBatch"
            ) as MockBatchClass,
        ):
            MockRegClass.return_value = AsyncMock(return_value=Success(mock_outcome))
            MockBatchClass.return_value = AsyncMock(
                return_value=Failure(ValidationError("Batch creation failed"))
            )
            result = await service(cmd)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.bulk_registration.registered_count == 1
        item_result = outcome.item_results[0]
        assert item_result.success is False
        assert item_result.molecule_id == mock_mol.id
        assert item_result.batch_id is None
        assert item_result.batch_number is None
        assert item_result.salt_matched is False
        assert item_result.batch_error is not None
        assert "Batch creation failed" in item_result.batch_error
