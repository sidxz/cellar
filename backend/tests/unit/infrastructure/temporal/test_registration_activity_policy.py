"""Unit tests for the batch-creation policy gate in RegistrationActivities.

These tests verify that process_chunk correctly consults should_create_batch
and gates _create_batch accordingly. All external dependencies (RegisterMolecule,
WorkspaceSettingsRepository, _create_batch) are mocked.
"""

from __future__ import annotations

import dataclasses
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from returns.result import Success

import chem_vault.infrastructure.temporal.activities.registration as registration_module
from chem_vault.domain.chemical_registration.enums import RegistrationAction
from chem_vault.infrastructure.temporal.activities.dtos import (
    ChunkInput,
    ChunkItem,
)
from chem_vault.infrastructure.temporal.activities.registration import RegistrationActivities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = str(uuid.uuid4())
ORG_ID = str(uuid.uuid4())
SUBMITTED_BY = str(uuid.uuid4())
MOL_ID = uuid.uuid4()
BATCH_ID = uuid.uuid4()


def _make_molecule() -> MagicMock:
    mol = MagicMock()
    mol.id = MOL_ID
    mol.descriptors = None
    return mol


def _make_outcome(*, is_new: bool, action: RegistrationAction) -> MagicMock:
    outcome = MagicMock()
    outcome.is_new = is_new
    outcome.action = action
    outcome.molecule = _make_molecule()
    outcome.detected_salt = None
    outcome.needs_merge_confirmation = False
    outcome.matched_molecule_id = None
    outcome.disclosure_id = None
    outcome.conflict_reason = None
    return outcome


def _make_chunk_input(*, create_batch_on_duplicate: bool | None = None) -> ChunkInput:
    item = ChunkItem(
        row_index=0,
        name="Test Compound",
        smiles="c1ccccc1",
        external_ids=[],
    )
    return ChunkInput(
        workspace_id=WORKSPACE_ID,
        originating_org_id=ORG_ID,
        submitted_by=SUBMITTED_BY,
        items=[item],
        chunk_index=0,
        create_batch_on_duplicate=create_batch_on_duplicate,
    )


def _make_settings(*, create_batch_on_duplicate: bool) -> MagicMock:
    settings = MagicMock()
    settings.create_batch_on_duplicate = create_batch_on_duplicate
    return settings


def _make_ws_repo(*, create_batch_on_duplicate: bool) -> MagicMock:
    repo = MagicMock()
    repo.find_by_workspace_id = AsyncMock(
        return_value=_make_settings(create_batch_on_duplicate=create_batch_on_duplicate)
    )
    return repo


def _make_settings_repo_factory(*, create_batch_on_duplicate: bool) -> MagicMock:
    """Returns a callable that produces a mock repo when called with a UoW."""
    repo = _make_ws_repo(create_batch_on_duplicate=create_batch_on_duplicate)
    factory = MagicMock(return_value=repo)
    return factory


async def _run_process_chunk(
    activity_instance: RegistrationActivities,
    chunk_input: ChunkInput,
    *,
    outcome: MagicMock,
) -> object:
    """Invoke process_chunk with RegisterMolecule mocked to return the given outcome."""
    with patch.object(
        registration_module,
        "RegisterMolecule",
        return_value=AsyncMock(return_value=Success(outcome)),
    ):
        with patch.object(
            registration_module,
            "DisclosureService",
            return_value=MagicMock(),
        ):
            with patch.object(
                registration_module,
                "MergeService",
                return_value=MagicMock(),
            ):
                with patch("chem_vault.infrastructure.temporal.activities.registration.AsyncUnitOfWork") as mock_uow_cls:
                    # Make all UoW instances work as async context managers
                    mock_uow = AsyncMock()
                    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
                    mock_uow.__aexit__ = AsyncMock(return_value=False)
                    mock_uow_cls.return_value = mock_uow

                    # Re-wire the settings repo factory to use our mock directly
                    # since AsyncUnitOfWork is now mocked
                    activity_instance._settings_repo_factory = MagicMock(
                        return_value=_make_ws_repo(
                            create_batch_on_duplicate=activity_instance._settings_repo_factory._batch_default
                        )
                    )
                    return await activity_instance.process_chunk(chunk_input)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_molecule_batch_skipped_when_policy_false():
    """A duplicate (is_new=False) with workspace default=False should NOT call _create_batch."""
    fake_create_batch = AsyncMock(return_value=(BATCH_ID, "CVB-0001", False))
    outcome = _make_outcome(is_new=False, action=RegistrationAction.DEDUPLICATED)
    settings_repo = _make_ws_repo(create_batch_on_duplicate=False)
    settings_repo_factory = MagicMock(return_value=settings_repo)

    activity_instance = RegistrationActivities(
        session_factory=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=AsyncMock(),
        side_effect_registry=MagicMock(),
        settings_repo_factory=settings_repo_factory,
    )

    with patch.object(
        registration_module, "_create_batch", fake_create_batch
    ):
        chunk_input = _make_chunk_input(create_batch_on_duplicate=None)
        output = await _run_process_chunk_simple(activity_instance, chunk_input, outcome=outcome)

    fake_create_batch.assert_not_called()
    assert len(output.results) == 1
    result = output.results[0]
    assert result.batch_skipped is True
    assert result.batch_id is None


@pytest.mark.asyncio
async def test_duplicate_molecule_batch_created_when_policy_true():
    """A duplicate (is_new=False) with workspace default=True SHOULD call _create_batch."""
    fake_create_batch = AsyncMock(return_value=(BATCH_ID, "CVB-0001", False))
    outcome = _make_outcome(is_new=False, action=RegistrationAction.DEDUPLICATED)
    settings_repo = _make_ws_repo(create_batch_on_duplicate=True)
    settings_repo_factory = MagicMock(return_value=settings_repo)

    activity_instance = RegistrationActivities(
        session_factory=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=AsyncMock(),
        side_effect_registry=MagicMock(),
        settings_repo_factory=settings_repo_factory,
    )

    with patch.object(
        registration_module, "_create_batch", fake_create_batch
    ):
        chunk_input = _make_chunk_input(create_batch_on_duplicate=None)
        output = await _run_process_chunk_simple(activity_instance, chunk_input, outcome=outcome)

    fake_create_batch.assert_called_once()
    assert len(output.results) == 1
    result = output.results[0]
    assert result.batch_skipped is False
    assert result.batch_id == str(BATCH_ID)


@pytest.mark.asyncio
async def test_new_molecule_always_creates_batch():
    """A new molecule (is_new=True) ALWAYS calls _create_batch regardless of policy."""
    fake_create_batch = AsyncMock(return_value=(BATCH_ID, "CVB-0001", False))
    outcome = _make_outcome(is_new=True, action=RegistrationAction.REGISTERED)
    settings_repo = _make_ws_repo(create_batch_on_duplicate=False)
    settings_repo_factory = MagicMock(return_value=settings_repo)

    activity_instance = RegistrationActivities(
        session_factory=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=AsyncMock(),
        side_effect_registry=MagicMock(),
        settings_repo_factory=settings_repo_factory,
    )

    with patch.object(
        registration_module, "_create_batch", fake_create_batch
    ):
        chunk_input = _make_chunk_input(create_batch_on_duplicate=None)
        output = await _run_process_chunk_simple(activity_instance, chunk_input, outcome=outcome)

    fake_create_batch.assert_called_once()
    assert len(output.results) == 1
    result = output.results[0]
    assert result.batch_skipped is False
    assert result.batch_id == str(BATCH_ID)


@pytest.mark.asyncio
async def test_chunk_level_override_true_overrides_workspace_false():
    """chunk.create_batch_on_duplicate=True overrides workspace default of False."""
    fake_create_batch = AsyncMock(return_value=(BATCH_ID, "CVB-0001", False))
    outcome = _make_outcome(is_new=False, action=RegistrationAction.DEDUPLICATED)
    # workspace default is False, but chunk override is True
    settings_repo = _make_ws_repo(create_batch_on_duplicate=False)
    settings_repo_factory = MagicMock(return_value=settings_repo)

    activity_instance = RegistrationActivities(
        session_factory=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=AsyncMock(),
        side_effect_registry=MagicMock(),
        settings_repo_factory=settings_repo_factory,
    )

    with patch.object(
        registration_module, "_create_batch", fake_create_batch
    ):
        chunk_input = _make_chunk_input(create_batch_on_duplicate=True)
        output = await _run_process_chunk_simple(activity_instance, chunk_input, outcome=outcome)

    fake_create_batch.assert_called_once()
    result = output.results[0]
    assert result.batch_skipped is False


@pytest.mark.asyncio
async def test_chunk_level_override_false_overrides_workspace_true():
    """chunk.create_batch_on_duplicate=False overrides workspace default of True."""
    fake_create_batch = AsyncMock(return_value=(BATCH_ID, "CVB-0001", False))
    outcome = _make_outcome(is_new=False, action=RegistrationAction.DEDUPLICATED)
    # workspace default is True, but chunk override is False
    settings_repo = _make_ws_repo(create_batch_on_duplicate=True)
    settings_repo_factory = MagicMock(return_value=settings_repo)

    activity_instance = RegistrationActivities(
        session_factory=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=AsyncMock(),
        side_effect_registry=MagicMock(),
        settings_repo_factory=settings_repo_factory,
    )

    with patch.object(
        registration_module, "_create_batch", fake_create_batch
    ):
        chunk_input = _make_chunk_input(create_batch_on_duplicate=False)
        output = await _run_process_chunk_simple(activity_instance, chunk_input, outcome=outcome)

    fake_create_batch.assert_not_called()
    result = output.results[0]
    assert result.batch_skipped is True


# ---------------------------------------------------------------------------
# Shared low-level runner — patches at the right layer
# ---------------------------------------------------------------------------

async def _run_process_chunk_simple(
    activity_instance: RegistrationActivities,
    chunk_input: ChunkInput,
    *,
    outcome: MagicMock,
) -> object:
    """Invoke process_chunk with all external I/O patched out.

    Patches:
    - AsyncUnitOfWork — returns an async-context-manager stub
    - RegisterMolecule — returns Success(outcome)
    - DisclosureService, MergeService, SaltMatcher — no-ops
    - SQLAlchemy repo constructors — return MagicMocks
    """
    mock_uow = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)

    mock_register_uc = AsyncMock(return_value=Success(outcome))
    mock_register_cls = MagicMock(return_value=mock_register_uc)

    with (
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.AsyncUnitOfWork",
            return_value=mock_uow,
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.RegisterMolecule",
            mock_register_cls,
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.DisclosureService",
            MagicMock(),
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.MergeService",
            MagicMock(),
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.SQLAlchemyMoleculeRepository",
            MagicMock(),
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.SQLAlchemyMergeEventRepository",
            MagicMock(),
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.SQLAlchemyDisclosureRequestRepository",
            MagicMock(),
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.SQLAlchemyBatchRepository",
            MagicMock(),
        ),
        patch(
            "chem_vault.infrastructure.temporal.activities.registration.SQLAlchemySaltEntryRepository",
            MagicMock(),
        ),
        patch(
            "temporalio.activity.heartbeat",
            MagicMock(),
        ),
    ):
        return await activity_instance.process_chunk(chunk_input)
