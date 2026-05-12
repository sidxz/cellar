"""DepictMolecules — render 2D PNG depictions for a batch of SMILES."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, ValidationError


MAX_SMILES_PER_REQUEST = 200


class DepictionService(Protocol):
    """Application-layer Protocol for batch SMILES → PNG rendering."""

    def generate_pngs_for_smiles(
        self,
        smiles_list: list[str],
        *,
        width: int = 150,
        height: int = 100,
    ) -> dict[str, str]: ...


@dataclass(frozen=True, kw_only=True)
class DepictMoleculesQuery(Query):
    smiles_list: list[str] = field(default_factory=list)
    width: int = 150
    height: int = 100


class DepictMolecules:
    """Render 2D PNG depictions for a batch of SMILES.

    Bounded at MAX_SMILES_PER_REQUEST. Invalid SMILES are skipped silently.
    """

    def __init__(self, depiction: DepictionService) -> None:
        self._depiction = depiction

    async def __call__(
        self, input: DepictMoleculesQuery, auth: AuthContext | None = None
    ) -> Result[dict[str, str], DomainError]:
        require_workspace_role(auth, "viewer")

        if len(input.smiles_list) > MAX_SMILES_PER_REQUEST:
            return Failure(ValidationError(f"Max {MAX_SMILES_PER_REQUEST} SMILES per request"))

        images = self._depiction.generate_pngs_for_smiles(
            input.smiles_list, width=input.width, height=input.height
        )
        return Success(images)
