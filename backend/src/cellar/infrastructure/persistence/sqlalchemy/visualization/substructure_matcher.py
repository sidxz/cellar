"""SQLAlchemy implementation of SubstructureMatcher — Search's strict substructure clause."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from rdkit import Chem
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.visualization.match_substructure import (
    QueryKind,
    SubstructureMatchResult,
)
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._structure_query import (
    _substructure_clause,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import MoleculeModel


def _check_readable(query: str, kind: QueryKind | None) -> None:
    """The cartridge reads an unparseable query as NULL and silently matches nothing."""
    smiles_ok = kind != "smarts" and Chem.MolFromSmiles(query) is not None
    smarts_ok = kind != "smiles" and Chem.MolFromSmarts(query) is not None
    if smiles_ok or smarts_ok:
        return
    what = {"smiles": "a SMILES structure", "smarts": "a SMARTS pattern"}.get(
        kind or "", "a structure (SMILES or SMARTS)"
    )
    msg = f"Cannot read “{query}” as {what}. Check ring closures, brackets and charges."
    if kind == "smiles":
        msg += " Query atoms and atom lists need SMARTS."
    raise ValueError(msg)


class SQLAlchemySubstructureMatcher:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def match(
        self,
        workspace_id: uuid.UUID,
        molecule_ids: Sequence[uuid.UUID],
        query: str,
        query_kind: QueryKind | None,
    ) -> SubstructureMatchResult:
        _check_readable(query, query_kind)
        clause = _substructure_clause(
            {"smiles_or_smarts": query, "query_kind": query_kind, "generalized": False}
        )
        scope = (
            MoleculeModel.workspace_id == workspace_id,
            any_id(MoleculeModel.id, molecule_ids),
        )
        blank = or_(MoleculeModel.smiles.is_(None), MoleculeModel.smiles == "")
        async with self._session_factory() as session:
            searched, without_structure = (
                await session.execute(
                    select(func.count(), func.count().filter(blank)).where(*scope)
                )
            ).one()
            matched = (
                await session.scalars(
                    select(MoleculeModel.id)
                    .where(*scope, ~blank, clause)
                    .order_by(MoleculeModel.id)
                )
            ).all()
        return SubstructureMatchResult(
            matched_ids=list(matched), searched=searched, without_structure=without_structure
        )
