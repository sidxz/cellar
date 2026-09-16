"""Maximum common substructure — the shape a set of molecules has in common.

The answer a chemist asks for after a cluster map or a scaffold network: not
"what framework do these share" (a Bemis-Murcko scaffold, which by
construction drops every substituent and acyclic atom) but "what do these
molecules actually have in common", substituents included.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McsResult:
    """One maximum-common-substructure answer.

    ``smarts`` is RDKit's own query string — exact, and what a substructure
    search wants. ``core_smiles`` is the same substructure written as a plain
    SMILES, extracted from a molecule that matches it, so it can go straight
    into depiction or R-group decomposition (both of which take SMILES only).
    It is ``None`` when no such SMILES could be produced.
    """

    smarts: str
    core_smiles: str | None
    num_atoms: int
    num_bonds: int
    #: ``FindMCS`` returns its best-so-far when it hits the time limit. A
    #: partial answer must never be read as *the* maximum common substructure,
    #: so this travels with the result everywhere it goes.
    timed_out: bool
    #: How many molecules the answer was computed over — after de-duplication
    #: and after skipping members with no usable structure. Lets a caller say
    #: "shared by 23 of 23" rather than implying it covers the whole set.
    molecule_count: int

    @property
    def is_empty(self) -> bool:
        """True when the molecules share nothing (``FindMCS`` found no common
        substructure, or there was nothing to compare)."""
        return self.num_atoms == 0
