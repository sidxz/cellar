"""Search execution endpoint."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, TypeAdapter, model_validator
from rdkit import Chem

from chem_vault.application.research_organization.execute_search import ExecuteSearchQuery
from chem_vault.domain.sar_analysis.search_modes import SearchMode
from chem_vault.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry
from chem_vault.interface.dependencies import AuthDep, ExecuteSearchDep
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.pagination import clamp_limit, parse_cursor
from chem_vault.interface.routes.molecules import MoleculeResponse

router = APIRouter(prefix="/api/v1/search", tags=["search"])

_registry = FingerprintRegistry.default()


# ---------------------------------------------------------------------------
# Structure-clause discriminated-union models
# ---------------------------------------------------------------------------


class _MetricTanimoto(BaseModel):
    kind: Literal["tanimoto"] = "tanimoto"


class _MetricTversky(BaseModel):
    kind: Literal["tversky"]
    alpha: float = Field(ge=0.0)
    beta: float = Field(ge=0.0)


_MetricSpec = Annotated[
    _MetricTanimoto | _MetricTversky, Field(discriminator="kind")
]


class _ExactMatch(BaseModel):
    kind: Literal["exact"]
    smiles: str | None = None
    inchi_key: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "_ExactMatch":
        # Allow either smiles OR inchi_key. The composer accepts inchi_key path.
        if self.smiles is None and self.inchi_key is None:
            raise ValueError("exact match requires smiles or inchi_key")
        if self.smiles is not None and Chem.MolFromSmiles(self.smiles) is None:
            raise ValueError("smiles failed RDKit parse")
        return self


class _SubstructureMatch(BaseModel):
    kind: Literal["substructure"]
    smiles_or_smarts: str | None = None
    smarts: str | None = None  # legacy alias accepted
    generalized: bool = False

    @model_validator(mode="after")
    def _check(self) -> "_SubstructureMatch":
        text_value = self.smiles_or_smarts or self.smarts
        if not text_value:
            raise ValueError("substructure requires smiles_or_smarts (or legacy smarts)")
        if (Chem.MolFromSmiles(text_value) is None
                and Chem.MolFromSmarts(text_value) is None):
            raise ValueError("smiles_or_smarts failed RDKit parse")
        return self


class _SimilarityMatch(BaseModel):
    kind: Literal["similarity"]
    smiles: str
    mode: SearchMode | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    algorithm: str | None = None
    metric: _MetricSpec | None = None

    @model_validator(mode="after")
    def _check(self) -> "_SimilarityMatch":
        if Chem.MolFromSmiles(self.smiles) is None:
            raise ValueError("smiles failed RDKit parse")
        # Power-user override: if `algorithm` is set without `mode`,
        # `metric` and `threshold` must also be set explicitly.
        if (self.mode is None and self.algorithm is not None
                and (self.metric is None or self.threshold is None)):
            raise ValueError(
                "explicit algorithm requires metric + threshold (or use mode)"
            )
        # Legacy shape (just smiles + optional threshold) is accepted; the
        # composer falls back to morgan + tanimoto + supplied/default threshold.
        if self.algorithm is not None and self.algorithm not in _registry.names():
            raise ValueError(
                f"unknown algorithm: {self.algorithm!r}; valid: {sorted(_registry.names())}"
            )
        return self


_StructureClause = Annotated[
    _ExactMatch | _SubstructureMatch | _SimilarityMatch,
    Field(discriminator="kind"),
]
_structure_adapter: TypeAdapter[_ExactMatch | _SubstructureMatch | _SimilarityMatch] = TypeAdapter(_StructureClause)


def _walk_validate_structures(criteria: list[dict[str, Any]]) -> None:
    """Recursively validate every {type: structure} criterion in the criteria tree."""
    for c in criteria:
        ctype = c.get("type")
        if ctype == "structure":
            payload = {k: v for k, v in c.items() if k != "type"}
            # Accept legacy `search_type` key as `kind`.
            if "kind" not in payload and "search_type" in payload:
                payload["kind"] = payload.pop("search_type")
            _structure_adapter.validate_python(payload)
        elif ctype == "group":
            _walk_validate_structures(c.get("criteria", []))


class ExecuteSearchBody(BaseModel):
    query: dict[str, Any] | None = None
    saved_search_id: uuid.UUID | None = None
    protocol_columns: list[str] | None = None

    @model_validator(mode="after")
    def _validate_structure_clauses(self) -> "ExecuteSearchBody":
        if self.query is None:
            return self
        _walk_validate_structures(self.query.get("criteria", []))
        return self


class ExecuteSearchResponse(BaseModel):
    """Response for compound search execution with optional activity enrichment."""

    items: list[MoleculeResponse]
    next_cursor: str | None = None
    activity_data: dict[str, dict[str, Any]] | None = None
    total_count: int | None = None


@router.post("/execute", response_model=ExecuteSearchResponse)
async def execute_search(
    body: ExecuteSearchBody,
    auth: AuthDep,
    use_case: ExecuteSearchDep,
    cursor: str | None = None,
    limit: int | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> ExecuteSearchResponse:
    """Execute a compound search -- inline query or saved search reference."""
    q = ExecuteSearchQuery(
        workspace_id=auth.workspace_id,
        saved_search_id=body.saved_search_id,
        query=body.query,
        protocol_columns=body.protocol_columns,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
        sort_by=sort_by,
        sort_dir=sort_dir if sort_dir in ("asc", "desc") else None,
    )
    page = result_to_response(await use_case(q, auth=auth))
    return ExecuteSearchResponse(
        items=[MoleculeResponse.from_domain(m) for m in page.items],
        next_cursor=page.next_cursor,
        activity_data=page.activity_data,
        total_count=page.total_count,
    )
