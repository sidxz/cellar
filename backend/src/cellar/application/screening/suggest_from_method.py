"""Suggest protocol fields from its method text, for a person to review: never applied on its own.

The first slice suggests two assay conditions, pH and Temperature, as definitions: each run
records its own value, so the value the method states is evidence, never a fixed value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, ServiceUnavailableError, ValidationError


@dataclass(frozen=True)
class MethodAnswer:
    """One value the reader found in the method, with the line it came from."""

    question: str
    value: str
    quote: str


@runtime_checkable
class MethodReader(Protocol):
    """Port: reads a method text and answers questions about it. The adapter raises
    ``ServiceUnavailableError`` when the reader cannot be reached."""

    async def read(self, method: str) -> list[MethodAnswer]: ...


@dataclass(frozen=True)
class Evidence:
    value: str
    quote: str


@dataclass(frozen=True)
class ConditionSuggestion:
    name: str
    data_type: str
    unit: str | None
    evidence: tuple[Evidence, ...]


# The reader's question -> the condition it suggests (name and unit as the default forms use).
CONDITIONS: dict[str, tuple[str, str | None]] = {
    "cond_ph": ("pH", None),
    "cond_temperature": ("Temperature", "°C"),
}


@dataclass(frozen=True, kw_only=True)
class SuggestFromMethodQuery(Query):
    method: str


class SuggestFromMethod:
    """``reader`` is None when the deployment has no reader configured: suggestions are off."""

    def __init__(self, reader: MethodReader | None) -> None:
        self._reader = reader

    @property
    def enabled(self) -> bool:
        return self._reader is not None

    async def __call__(
        self, input: SuggestFromMethodQuery, auth: AuthContext | None = None
    ) -> Result[list[ConditionSuggestion], DomainError]:
        require_editor(auth)
        if self._reader is None:
            return Failure(ServiceUnavailableError("Suggestions from the method are turned off"))
        if not input.method.strip():
            return Failure(ValidationError("Write the method first"))
        try:
            answers = await self._reader.read(input.method)
        except DomainError as exc:
            return Failure(exc)
        found: dict[str, list[Evidence]] = {}
        for a in answers:
            if a.question in CONDITIONS:
                ev = Evidence(a.value, a.quote)
                if ev not in found.setdefault(a.question, []):
                    found[a.question].append(ev)
        return Success(
            [
                ConditionSuggestion(name, "numeric", unit, tuple(found[q]))
                for q, (name, unit) in CONDITIONS.items()
                if q in found
            ]
        )
