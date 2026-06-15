"""The enricher port + the batch ``enrich_to_scalars`` bridge.

``MoleculeActivityEnricher`` is the application-layer Protocol that
``MoleculeActivityService`` satisfies structurally (wired via DI), so the
projection use cases stay unit-testable with a fake. ``enrich_to_scalars`` runs
one enrich call for a batch of ids and applies ``pick_scalar`` to produce SPARSE
``ActivityScalar`` rows — the shared bridge used by both ``StartActivityProjection``
(inline) and ``RunActivityProjection`` (per streamed batch).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.activity_channel import (
    ActivityChannelSpec,
    activity_value_snapshot,
    pick_scalar,
)
from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule


class MoleculeActivityEnricher(Protocol):
    async def enrich_molecules(
        self,
        workspace_id: UUID,
        molecule_ids: list[UUID],
        protocol_columns: list[str],
        *,
        selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling: QualifierHandling = QualifierHandling.EXCLUDE_QUALIFIED,
        run_scopes: dict[str, RunScope] | None = None,
    ) -> dict[UUID, dict[str, ActivityValue]]: ...


async def enrich_to_scalars(
    enricher: MoleculeActivityEnricher,
    *,
    workspace_id: UUID,
    molecule_ids: list[UUID],
    channel: ActivityChannelSpec,
) -> list[ActivityScalar]:
    if not molecule_ids:
        return []
    enriched = await enricher.enrich_molecules(
        workspace_id,
        molecule_ids,
        [channel.column],
        selection_rule=channel.selection_rule,
        qualifier_handling=channel.qualifier_handling,
        run_scopes=channel.resolved_run_scopes(),
    )
    out: list[ActivityScalar] = []
    for molecule_id, cols in enriched.items():
        av = cols.get(channel.column)
        if av is None:
            continue
        scalar = pick_scalar(av, channel.intercept_key)
        if scalar is None:
            continue  # sparse — no value for this molecule on this channel
        out.append(
            ActivityScalar(
                molecule_id=molecule_id,
                scalar=scalar,
                unit=av.unit,
                qualifier=av.qualifier,
                source=av.source,
                snapshot=activity_value_snapshot(av),
            )
        )
    return out
