"""SaltMatcher -- match detected/specified salt against workspace SaltEntry catalog."""

from __future__ import annotations

import uuid

from cellar.domain.workspace_config.repository import SaltEntryRepository
from cellar.domain.workspace_config.salt_entry import SaltEntry


def compute_formula_weight(parent_mw: float, salt_mw: float, stoichiometry: int) -> float:
    """Compute formula weight: parent MW + (salt MW * stoichiometry)."""
    return parent_mw + (salt_mw * stoichiometry)


class SaltMatcher:
    """Match detected or user-specified salt against workspace SaltEntry catalog."""

    def __init__(self, salt_entry_repo: SaltEntryRepository) -> None:
        self._repo = salt_entry_repo

    async def match_by_code(self, workspace_id: uuid.UUID, salt_code: str) -> SaltEntry | None:
        """Look up a salt entry by its short code (e.g., 'HCl', 'Na')."""
        return await self._repo.find_by_code(workspace_id, salt_code)

    async def match_by_smiles(self, workspace_id: uuid.UUID, salt_smiles: str) -> SaltEntry | None:
        """Look up a salt entry by canonical SMILES."""
        return await self._repo.find_by_smiles(workspace_id, salt_smiles)
