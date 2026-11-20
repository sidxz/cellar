"""Tests for MergeEvent entity."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import MergeReason
from cellar.domain.chemical_registration.merge_event import MergeEvent
from cellar.domain.shared.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def snapshot() -> dict:
    return {"smiles": "CCO", "name": "Ethanol", "reg_number": "CV-00001"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMergeEventCreate:
    """MergeEvent.create() factory tests."""

    def test_self_merge_raises(
        self,
        ws_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot: dict,
    ) -> None:
        same_id = uuid.uuid4()
        with pytest.raises(ValidationError, match="cannot merge into itself"):
            MergeEvent.create(
                workspace_id=ws_id,
                source_molecule_id=same_id,
                target_molecule_id=same_id,
                reason=MergeReason.DUPLICATE_CLEANUP,
                merged_by=user_id,
                snapshot=snapshot,
            )
