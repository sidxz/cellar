"""Tests for SaltMatcher -- match detected/specified salt against workspace catalog."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from chem_vault.application.inventory.salt_matcher import SaltMatcher, compute_formula_weight
from chem_vault.domain.workspace_config.salt_entry import SaltEntry


def _make_salt_entry(
    code: str = "HCl",
    name: str = "hydrochloride",
    smiles: str = "[H]Cl",
    molecular_weight: float = 36.46,
    workspace_id: uuid.UUID | None = None,
) -> SaltEntry:
    return SaltEntry(
        id=uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        code=code,
        name=name,
        smiles=smiles,
        molecular_weight=molecular_weight,
    )


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


class TestSaltMatcher:
    async def test_match_by_code_found(self, workspace_id: uuid.UUID) -> None:
        entry = _make_salt_entry(code="HCl", workspace_id=workspace_id)
        repo = AsyncMock()
        repo.find_by_code = AsyncMock(return_value=entry)

        matcher = SaltMatcher(salt_entry_repo=repo)
        result = await matcher.match_by_code(workspace_id, "HCl")

        assert result is not None
        assert result.code == "HCl"
        repo.find_by_code.assert_called_once_with(workspace_id, "HCl")

    async def test_match_by_code_not_found(self, workspace_id: uuid.UUID) -> None:
        repo = AsyncMock()
        repo.find_by_code = AsyncMock(return_value=None)

        matcher = SaltMatcher(salt_entry_repo=repo)
        result = await matcher.match_by_code(workspace_id, "UNKNOWN")

        assert result is None

    async def test_match_by_smiles_found(self, workspace_id: uuid.UUID) -> None:
        entry = _make_salt_entry(smiles="[Na+]", workspace_id=workspace_id)
        repo = AsyncMock()
        repo.find_by_smiles = AsyncMock(return_value=entry)

        matcher = SaltMatcher(salt_entry_repo=repo)
        result = await matcher.match_by_smiles(workspace_id, "[Na+]")

        assert result is not None
        repo.find_by_smiles.assert_called_once_with(workspace_id, "[Na+]")

    async def test_match_by_smiles_not_found(self, workspace_id: uuid.UUID) -> None:
        repo = AsyncMock()
        repo.find_by_smiles = AsyncMock(return_value=None)

        matcher = SaltMatcher(salt_entry_repo=repo)
        result = await matcher.match_by_smiles(workspace_id, "[Xe]")

        assert result is None


class TestComputeFormulaWeight:
    def test_basic_calculation(self) -> None:
        # parent MW 180.16 + HCl 36.46 * 1
        assert compute_formula_weight(180.16, 36.46, 1) == pytest.approx(216.62)

    def test_stoichiometry_2(self) -> None:
        # parent MW 180.16 + HCl 36.46 * 2
        assert compute_formula_weight(180.16, 36.46, 2) == pytest.approx(253.08)

    def test_zero_salt_returns_parent(self) -> None:
        assert compute_formula_weight(180.16, 0.0, 1) == pytest.approx(180.16)
