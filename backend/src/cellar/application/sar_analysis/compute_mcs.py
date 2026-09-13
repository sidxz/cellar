"""ComputeMcs — the maximum common substructure of a supplied molecule set.

Synchronous, unlike its three SAR siblings (scaffold tree, UMAP cluster,
R-group decomposition), which all schedule a job. Those exist because their
computes run for minutes; ``FindMCS`` measured in milliseconds on every
realistic set tried (a 2,000-molecule series sharing a 30-atom scaffold took
0.11 s; the worst constructed case — ten highly symmetric 12-residue peptides
with a 49-atom answer — took 1.8 s), and its own ``timeout`` bounds the rest.
A job table, a Temporal workflow and a poll/cancel pair would be lifecycle
scaffolding for a wait that does not happen.

ponytail: sync with a hard timeout. The ceiling is that timeout holding the
request open, and the GIL with it — the same trade the other SAR routes' sync
paths already make. If a real set ever pushes past it, this becomes the fourth
async job on the ``AsyncJob`` base: add an ``McsJob`` aggregate + repository +
migration and move the compute into a Temporal activity, keeping this use case
as the compute body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.sar_analysis.repositories import MoleculeSmilesFetcher
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.mcs_types import McsResult

#: Hard ceiling on the RDKit search. Past this, ``FindMCS`` returns its
#: best-so-far and the result is flagged ``timed_out``.
MCS_TIMEOUT_SECONDS = 10

#: Two molecules are the minimum with a common substructure worth the name.
MIN_SET_SIZE = 2

#: Above this the request is refused rather than run long. Far above anything
#: measured (2,000 molecules took 0.11 s), so it guards the pathological set,
#: not the ordinary one.
MAX_SET_SIZE = 10_000


class McsCalculator(Protocol):
    def compute(self, smiles: list[str], *, timeout_seconds: int) -> McsResult: ...


@dataclass(frozen=True)
class ComputeMcsInput:
    molecule_ids: list[UUID]
    workspace_id: UUID


class ComputeMcs:
    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeSmilesFetcher,
        calculator: McsCalculator,
        uow: UnitOfWork,
        timeout_seconds: int = MCS_TIMEOUT_SECONDS,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._calculator = calculator
        self._uow = uow
        self._timeout_seconds = timeout_seconds

    async def execute(
        self, payload: ComputeMcsInput, auth: AuthContext | None = None
    ) -> McsResult:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, payload.workspace_id)

        async with self._uow:
            rows = await self._fetcher.fetch_for_scaffold_tree(
                molecule_ids=payload.molecule_ids, workspace_id=payload.workspace_id
            )

        # The fetch is workspace-scoped and drops structureless rows, so a
        # molecule the caller named but does not own simply is not here —
        # `molecule_count` is what the answer actually covers, which is why it
        # travels with the result.
        smiles = list(dict.fromkeys(smi for _id, smi, _bm in rows if smi))
        return self._calculator.compute(smiles, timeout_seconds=self._timeout_seconds)
