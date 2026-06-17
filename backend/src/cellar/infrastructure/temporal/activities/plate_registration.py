"""Plate registration activities — process a chunk of CDD plates.

Registers plates via existing RegisterPlate + MapWells use cases.
Resolves CDD batch IDs to internal batch IDs via custom_fields query.
"""

from __future__ import annotations

import uuid

import structlog
from returns.result import Failure
from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from cellar.application.inventory.registered_plates import (
    MapWells,
    MapWellsCommand,
    RegisterPlate,
    RegisterPlateCommand,
)
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import BatchModel
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.activities.dtos import (
    PlateChunkInput,
    PlateChunkItem,
    PlateChunkOutput,
)

logger = structlog.get_logger(__name__)


class PlateRegistrationActivities:
    """Temporal activities for registering CDD plates."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        dispatcher: EventDispatcher,
    ) -> None:
        self._session_factory = session_factory
        self._dispatcher = dispatcher

    @activity.defn
    async def process_plate_chunk(self, input: PlateChunkInput) -> PlateChunkOutput:
        """Process a chunk of CDD plates — register plates, resolve wells, map wells."""
        output = PlateChunkOutput()

        for plate_item in input.items:
            plate = PlateChunkItem(**plate_item) if isinstance(plate_item, dict) else plate_item
            try:
                result = await self._process_single_plate(
                    self._session_factory,
                    input,
                    plate,
                    output,
                )
                if result:
                    output.sync_pairs.append(result)
            except Exception:
                logger.exception(
                    "plate.processing_failed",
                    cdd_plate_id=plate.cdd_plate_id,
                )
                output.plates_error += 1

            activity.heartbeat(
                f"chunk {input.chunk_index}: "
                f"reg={output.plates_registered} dup={output.plates_duplicate} "
                f"err={output.plates_error}"
            )

        return output

    async def _process_single_plate(
        self,
        session_factory: async_sessionmaker,
        input: PlateChunkInput,
        plate: PlateChunkItem,
        output: PlateChunkOutput,
    ) -> dict | None:
        """Register a single plate and return sync pair dict, or None."""
        uow = AsyncUnitOfWork(session_factory)
        repo = SQLAlchemyRegisteredPlateRepository(uow)
        register_uc = RegisterPlate(uow=uow, repo=repo, dispatcher=self._dispatcher)
        batch_repo = SQLAlchemyBatchRepository(uow)
        map_wells_uc = MapWells(
            uow=uow, repo=repo, batch_repo=batch_repo, dispatcher=self._dispatcher
        )

        ws_id = uuid.UUID(input.workspace_id)
        submitted_by = uuid.UUID(input.submitted_by)
        barcode = plate.name or f"CDD-{plate.cdd_plate_id}"

        # Check for existing plate with same barcode (duplicate detection)
        async with uow:
            existing = await repo.find_by_barcode(ws_id, barcode)
        if existing:
            output.plates_duplicate += 1
            return {
                "cdd_plate_id": plate.cdd_plate_id,
                "plate_id": str(existing.id),
            }

        # Register the plate
        reg_result = await register_uc(
            RegisterPlateCommand(
                workspace_id=ws_id,
                barcode=barcode,
                plate_label=barcode,
                format=plate.format,
                plate_type="compound_storage",
                registered_by=submitted_by,
            ),
        )

        if isinstance(reg_result, Failure):
            logger.warning(
                "plate.registration_failed",
                barcode=barcode,
                error=str(reg_result.failure()),
            )
            output.plates_error += 1
            return None

        registered_plate = reg_result.unwrap()
        output.plates_registered += 1

        # Resolve wells — map CDD batch IDs to internal batch IDs
        if plate.wells:
            well_map = await self._resolve_wells(
                session_factory,
                ws_id,
                input.cdd_vault_id,
                plate.wells,
                output,
            )
            if well_map:
                await map_wells_uc(
                    MapWellsCommand(
                        workspace_id=ws_id,
                        plate_id=registered_plate.id,
                        well_map=well_map,
                    ),
                )

        return {
            "cdd_plate_id": plate.cdd_plate_id,
            "plate_id": str(registered_plate.id),
        }

    async def _resolve_wells(
        self,
        session_factory: async_sessionmaker,
        workspace_id: uuid.UUID,
        cdd_vault_id: str,
        wells: list[dict],
        output: PlateChunkOutput,
    ) -> dict:
        """Resolve CDD batch IDs in wells to internal batch IDs.

        Wells without a cdd_batch_id (blanks/controls) are included with batch_id=None.
        Wells with unresolvable CDD batch IDs get batch_id=None + warning.
        """
        # Collect unique CDD batch IDs that need resolution
        cdd_batch_ids: set[int] = set()
        for well in wells:
            cdd_bid = well.get("cdd_batch_id")
            if cdd_bid is not None:
                cdd_batch_ids.add(int(cdd_bid))

        # Batch-resolve CDD batch IDs via custom_fields->>'cdd_batch_id' query
        batch_id_map: dict[int, uuid.UUID] = {}
        if cdd_batch_ids:
            uow = AsyncUnitOfWork(session_factory)
            async with uow:
                for cdd_bid in cdd_batch_ids:
                    stmt = (
                        select(BatchModel.id)
                        .where(
                            BatchModel.workspace_id == workspace_id,
                            cast(BatchModel.custom_fields["cdd_batch_id"].astext, String)
                            == str(cdd_bid),
                        )
                        .limit(1)
                    )
                    result = await uow.session.execute(stmt)
                    internal_id = result.scalar_one_or_none()
                    if internal_id:
                        batch_id_map[cdd_bid] = internal_id

        # Build well_map
        well_map: dict[str, dict] = {}
        for well in wells:
            position = well.get("position", "")
            cdd_bid = well.get("cdd_batch_id")

            well_data: dict = {}
            if cdd_bid is not None:
                internal_id = batch_id_map.get(int(cdd_bid))
                if internal_id:
                    well_data["batch_id"] = str(internal_id)
                    output.wells_mapped += 1
                else:
                    well_data["batch_id"] = None
                    well_data["cdd_batch_id_unresolved"] = cdd_bid
                    output.wells_unresolved += 1
            else:
                # Blank/control well — no batch
                well_data["batch_id"] = None
                output.wells_mapped += 1

            well_map[position] = well_data

        return well_map
