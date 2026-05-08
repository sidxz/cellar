"""SQLAlchemy implementation of PlateReadModelService."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.inventory.plate_read_model import MoleculePlateEntry


class SQLAlchemyPlateReadModelService:
    """Infrastructure-layer read model for cross-aggregate plate queries.

    Takes a ``async_sessionmaker`` and opens a fresh session per call so
    the service is safe to register as a singleton without leaking a
    long-lived connection.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def find_plates_for_molecule(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[MoleculePlateEntry]:
        """Find all registered plates containing batches of this molecule."""
        sql = text("""
            SELECT
                rp.id AS plate_id,
                rp.barcode,
                rp.plate_label,
                well_entry.key AS well_position,
                (well_entry.value ->> 'concentration_value')::float AS concentration_value,
                well_entry.value ->> 'concentration_unit' AS concentration_unit,
                rp.plate_type,
                rp.status,
                sl.name AS storage_location_name
            FROM registered_plates rp
            CROSS JOIN LATERAL jsonb_each(rp.well_map) AS well_entry(key, value)
            JOIN batches b ON b.id = (well_entry.value ->> 'batch_id')::uuid
            LEFT JOIN storage_locations sl ON sl.id = rp.storage_location_id
            WHERE rp.workspace_id = :workspace_id
              AND b.workspace_id = :workspace_id
              AND b.molecule_id = :molecule_id
            ORDER BY rp.barcode, well_entry.key
        """)

        async with self._session_factory() as session:
            result = await session.execute(
                sql, {"workspace_id": workspace_id, "molecule_id": molecule_id}
            )
            rows = result.fetchall()
        return [
            MoleculePlateEntry(
                plate_id=row.plate_id,
                barcode=row.barcode,
                plate_label=row.plate_label,
                well_position=row.well_position,
                concentration_value=row.concentration_value,
                concentration_unit=row.concentration_unit,
                plate_type=row.plate_type,
                status=row.status,
                storage_location_name=row.storage_location_name,
            )
            for row in rows
        ]
