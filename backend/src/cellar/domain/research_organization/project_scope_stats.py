"""ProjectScopeStats — aggregate counts describing the size of a project's scope."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ProjectScopeStats:
    molecule_count: int
    protocol_count: int
    run_count: int
