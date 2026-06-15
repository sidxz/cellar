"""Pure-data result types for R-group decomposition.

Serializable to JSON. No behavior — compute lives in
``infrastructure.rdkit.rgroup_decomposer`` and the use case in
``application.sar_analysis.start_decomposition_run``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class RGroupAssignment:
    """One molecule's R-group substituents, as SMILES keyed by label (R1, R2…)."""

    molecule_id: UUID
    rgroups: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RGroupDecompositionResult:
    """Decomposition of a set of molecules against a single core.

    ``rgroup_labels`` are the discovered positions (e.g. ["R1", "R2"]) in
    ascending order. ``unmatched_ids`` are molecules that did not contain the
    core (or could not be parsed) — surfaced, never silently dropped.
    """

    core_smiles: str
    rgroup_labels: list[str] = field(default_factory=list)
    assignments: list[RGroupAssignment] = field(default_factory=list)
    unmatched_ids: list[UUID] = field(default_factory=list)
