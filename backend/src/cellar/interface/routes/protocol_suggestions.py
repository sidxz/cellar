"""Suggestions from a protocol's method text, for the person writing it to review."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cellar.application.screening.suggest_from_method import (
    ConditionSuggestion,
    SuggestFromMethodQuery,
)
from cellar.interface.dependencies import AuthDep, SuggestFromMethodDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/protocol-suggestions", tags=["protocol-suggestions"])


class SuggestionsStatusResponse(BaseModel):
    enabled: bool


@router.get("/status", response_model=SuggestionsStatusResponse)
async def suggestions_status(
    _auth: AuthDep, use_case: SuggestFromMethodDep
) -> SuggestionsStatusResponse:
    """Whether this deployment can suggest from a method (a classifier is configured)."""
    return SuggestionsStatusResponse(enabled=use_case.enabled)


class SuggestFromMethodRequest(BaseModel):
    method: str = Field(min_length=1, max_length=50_000)
    model_config = {"extra": "forbid"}


class EvidenceResponse(BaseModel):
    value: str
    quote: str


class ConditionSuggestionResponse(BaseModel):
    name: str
    data_type: str
    unit: str | None
    evidence: list[EvidenceResponse]

    @classmethod
    def from_domain(cls, s: ConditionSuggestion) -> ConditionSuggestionResponse:
        return cls(
            name=s.name,
            data_type=s.data_type,
            unit=s.unit,
            evidence=[EvidenceResponse(value=e.value, quote=e.quote) for e in s.evidence],
        )


class MethodSuggestionsResponse(BaseModel):
    conditions: list[ConditionSuggestionResponse]


@router.post("", response_model=MethodSuggestionsResponse)
async def suggest_from_method(
    body: SuggestFromMethodRequest, auth: AuthDep, use_case: SuggestFromMethodDep
) -> MethodSuggestionsResponse:
    """Assay conditions the method names, each with the text it was read from. Nothing is saved."""
    found = result_to_response(
        await use_case(SuggestFromMethodQuery(method=body.method), auth=auth)
    )
    return MethodSuggestionsResponse(
        conditions=[ConditionSuggestionResponse.from_domain(s) for s in found]
    )
