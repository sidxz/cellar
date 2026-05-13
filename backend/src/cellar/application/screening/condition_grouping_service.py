"""ConditionGroupingService — read-model query service for aggregating readout data
by condition values.

Typical use case: "For protocol X, group all IC50 values by the 'Cell Line' condition."
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregatedReadout:
    """A single aggregated readout value for a condition group."""

    readout_definition_id: uuid.UUID
    name: str
    value: float
    unit: str | None
    aggregation: str
    count: int


@dataclass(frozen=True)
class ConditionGroup:
    """All readout data for a single condition value."""

    condition_value: str
    run_count: int
    aggregated_readouts: list[AggregatedReadout]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ConditionGroupingService:
    """Read-model service for aggregating readout data by condition value.

    This is a query-side service that does not modify any aggregate state.
    It crosses the boundary between protocol definitions and raw readout data
    to produce a grouped pivot view.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        readout_data_repo: ReadoutDataRepository,
        protocol_repo: ProtocolRepository,
    ) -> None:
        self._uow = uow
        self._readout_data_repo = readout_data_repo
        self._protocol_repo = protocol_repo

    async def group_by_condition(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        condition_name: str,
    ) -> Result[list[ConditionGroup], DomainError]:
        """Aggregate readout data grouped by a specific condition value.

        Steps:
        1. Load the protocol — 404 if missing.
        2. Verify condition_name exists in protocol.condition_definitions — 422 if not.
        3. Query DB for grouped rows via find_grouped_by_condition.
        4. Build ConditionGroup list sorted by condition_value.

        Args:
            workspace_id: Scoping workspace.
            protocol_id: Protocol whose readout data will be grouped.
            condition_name: Name of the condition variable to group by.

        Returns:
            Success(list[ConditionGroup]) sorted by condition_value, or Failure.
        """
        async with self._uow:
            # Step 1 — load protocol + workspace check
            protocol = await self._protocol_repo.find_by_id_in_workspace(workspace_id, protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(protocol_id)))

            # Step 2 — validate condition_name
            available_names = [cd.name for cd in protocol.condition_definitions]
            if condition_name not in available_names:
                return Failure(
                    ValidationError(
                        f"Condition '{condition_name}' not found in protocol "
                        f"'{protocol.name}'. Available conditions: {available_names}"
                    )
                )

            # Step 3 — fetch grouped DB rows
            rows = await self._readout_data_repo.find_grouped_by_condition(
                workspace_id, protocol_id, condition_name
            )

            # Step 4 — handle empty result
            if not rows:
                return Success([])

            # Step 5 — group rows by condition_value
            groups_map: dict[str, list] = {}
            for row in rows:
                groups_map.setdefault(row.condition_value, []).append(row)

            condition_groups: list[ConditionGroup] = []
            for condition_value in sorted(groups_map):
                group_rows = groups_map[condition_value]

                aggregated_readouts: list[AggregatedReadout] = []
                run_count = 0

                for row in group_rows:
                    agg_lower = (row.aggregation or "").lower()
                    if agg_lower == "min":
                        value = row.min_val
                    elif agg_lower == "max":
                        value = row.max_val
                    else:
                        value = row.avg_val

                    aggregated_readouts.append(
                        AggregatedReadout(
                            readout_definition_id=row.readout_definition_id,
                            name=row.readout_name,
                            value=float(value),
                            unit=row.unit,
                            aggregation=row.aggregation or "none",
                            count=row.cnt,
                        )
                    )
                    if row.cnt > run_count:
                        run_count = row.cnt

                condition_groups.append(
                    ConditionGroup(
                        condition_value=condition_value,
                        run_count=run_count,
                        aggregated_readouts=aggregated_readouts,
                    )
                )

            return Success(condition_groups)
