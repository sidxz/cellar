"""Shared Pydantic response models for dose-response intercepts.

Previously every route that surfaces intercept-bearing curves
(``molecule_activity``, ``protocol_hub``, ``readout_data``) defined its
own identical-shape ``InterceptSpecResponse`` / ``InterceptValueResponse``
pair and re-implemented the same 14-line domain → Pydantic mapping. That
duplication had already drifted (``readout_data`` called ``.value`` on
the enum spec fields while the other two relied on Pydantic's implicit
coercion).

This module exposes the canonical pair plus a ``from_domain`` factory.
All three routes now import from here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class InterceptSpecResponse(BaseModel):
    kind: str  # "ic" | "ec"
    level: float
    basis: str  # "relative_percent" | "absolute"
    label: str | None = None


class InterceptValueResponse(BaseModel):
    spec: InterceptSpecResponse
    value: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    at_bound: bool = False

    @classmethod
    def from_domain(cls, iv: Any) -> InterceptValueResponse:
        """Map a domain ``InterceptValue`` to its wire form.

        Defensive enum extraction (``getattr(..., "value", ...)``) handles
        both stored-as-enum (e.g. ``IntereptKind.IC``) and already-stringified
        fields uniformly — readers don't have to know whether the producer
        already coerced.
        """
        spec = iv.spec
        return cls(
            spec=InterceptSpecResponse(
                kind=_enum_str(spec.kind),
                level=spec.level,
                basis=_enum_str(spec.basis),
                label=spec.label,
            ),
            value=iv.value,
            confidence_interval_low=iv.confidence_interval_low,
            confidence_interval_high=iv.confidence_interval_high,
            at_bound=iv.at_bound,
        )


def _enum_str(value: Any) -> str:
    """Return ``.value`` for Enums, ``str(value)`` otherwise."""
    return value.value if hasattr(value, "value") else str(value)
