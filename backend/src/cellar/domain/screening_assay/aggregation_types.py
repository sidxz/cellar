"""Aggregation primitives — re-exported from ``domain.shared``.

These types describe screening-domain concepts (selection rules,
qualifier handling, value qualifiers, variance stats). They live in
``domain.shared.aggregation_types`` because they are also consumed by
``domain.research_organization`` (campaign channels), and the
bounded-context-independence contract forbids cross-context domain
imports.

This module is the screening_assay-side ergonomic alias so callers in
this context can import from their own namespace.
"""

from __future__ import annotations

from cellar.domain.shared.aggregation_types import (
    AggregateStats,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)

__all__ = [
    "AggregateStats",
    "QualifierHandling",
    "SelectionRule",
    "ValueQualifier",
]
