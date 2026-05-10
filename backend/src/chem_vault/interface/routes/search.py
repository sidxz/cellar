"""Search execution endpoint."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, TypeAdapter, model_validator

from chem_vault.application.research_organization.count_search import CountSearchQuery
from chem_vault.application.research_organization.execute_search import ExecuteSearchQuery
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.sar_analysis.search_modes import SearchMode
from chem_vault.interface.dependencies import AuthDep, CountSearchDep, ExecuteSearchDep
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.pagination import clamp_limit, parse_cursor
from chem_vault.interface.routes.molecules import MoleculeResponse

router = APIRouter(prefix="/api/v1/search", tags=["search"])

# RDKit / fingerprint-registry semantic checks are intentionally NOT performed
# here. Pydantic validators below cover only structural shape (discriminator,
# required fields, basic conflicts). Substantive validation — SMILES/SMARTS
# parseability, fingerprint algorithm existence — is the application layer's
# job and surfaces as a ValidationError → 422 from the use case.


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
        return self


class _SubstructureMatch(BaseModel):
    kind: Literal["substructure"]
    smiles_or_smarts: str | None = None
    smarts: str | None = None  # legacy alias accepted
    generalized: bool = False
    # Disambiguates how the cartridge interprets the value. Optional —
    # legacy criteria (no query_kind) follow the "either parses" rule and
    # the composer aromatizes them defensively. New FE always sets it.
    query_kind: Literal["smiles", "smarts"] | None = None

    @model_validator(mode="after")
    def _check(self) -> "_SubstructureMatch":
        text_value = self.smiles_or_smarts or self.smarts
        if not text_value:
            raise ValueError("substructure requires smiles_or_smarts (or legacy smarts)")
        if self.generalized and self.query_kind == "smarts":
            # The cartridge's mol_to_xqmol path requires a real `mol`,
            # not a `qmol`. Generalized + SMARTS would silently match
            # nothing useful — surface the conflict instead.
            raise ValueError(
                "generalized matching requires a structural query "
                "(SMILES); query atoms / atom lists aren't supported"
            )
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
        # Power-user override: if `algorithm` is set without `mode`,
        # `metric` and `threshold` must also be set explicitly.
        if (self.mode is None and self.algorithm is not None
                and (self.metric is None or self.threshold is None)):
            raise ValueError(
                "explicit algorithm requires metric + threshold (or use mode)"
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


def _attach_score(
    m: Molecule, scores: dict[uuid.UUID, float] | None
) -> MoleculeResponse:
    """Build a MoleculeResponse and attach similarity_score when available."""
    resp = MoleculeResponse.from_domain(m)
    if scores is not None and m.id in scores:
        resp = resp.model_copy(update={"similarity_score": round(scores[m.id], 4)})
    return resp


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
        items=[_attach_score(m, page.similarity_scores) for m in page.items],
        next_cursor=page.next_cursor,
        activity_data=page.activity_data,
        total_count=page.total_count,
    )


# ---------------------------------------------------------------------------
# Count-only endpoint -- powers the live "Search N compounds" preview on the
# search panel. Deliberately separate from /execute so we never materialize
# rows, score similarity, or run activity enrichment for a draft preview.
# ---------------------------------------------------------------------------


class CountSearchBody(BaseModel):
    query: dict[str, Any] | None = None
    saved_search_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_structure_clauses(self) -> "CountSearchBody":
        if self.query is None:
            return self
        _walk_validate_structures(self.query.get("criteria", []))
        return self


class CountSearchResponse(BaseModel):
    total_count: int


@router.post("/count", response_model=CountSearchResponse)
async def count_search(
    body: CountSearchBody,
    auth: AuthDep,
    use_case: CountSearchDep,
) -> CountSearchResponse:
    """Count compounds matching a draft query without materializing rows."""
    q = CountSearchQuery(
        workspace_id=auth.workspace_id,
        saved_search_id=body.saved_search_id,
        query=body.query,
    )
    total = result_to_response(await use_case(q, auth=auth))
    return CountSearchResponse(total_count=total)
