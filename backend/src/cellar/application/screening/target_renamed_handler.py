"""A registry target was renamed: re-derive the names of the protocols linked to it."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from cellar.application.screening.rederive_protocol_names import (
    RederiveProtocolNames,
    RederiveProtocolNamesCommand,
)
from cellar.domain.screening_assay.events import TargetRenamed


class TargetRenamedHandler:
    def __init__(
        self,
        rederive: Callable[[], RederiveProtocolNames],
        ids_for_target: Callable[[uuid.UUID, uuid.UUID], Awaitable[list[uuid.UUID]]],
    ) -> None:
        self._rederive = rederive
        self._ids_for_target = ids_for_target

    async def __call__(self, event: TargetRenamed) -> None:
        protocol_ids = await self._ids_for_target(event.workspace_id, event.aggregate_id)
        if protocol_ids:
            await self._rederive()(
                RederiveProtocolNamesCommand(
                    workspace_id=event.workspace_id,
                    protocol_ids=protocol_ids,
                    reason=f"Registry renamed {event.old_name} to {event.new_name}",
                ),
                auth=None,
            )
