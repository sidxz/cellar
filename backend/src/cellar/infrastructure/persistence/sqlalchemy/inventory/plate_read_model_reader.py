"""SQLAlchemy implementation of PlateReadModelService."""

from __future__ import annotations

import uuid

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.inventory.plate_read_model import MoleculePlateEntry


class SQLAlchemyPlateReadModelService:
    """Infrastructure-layer read model for cross-aggregate plate queries.

    Takes a ``async_sessionmaker`` and opens a fresh session per call so
    the service is safe to register as a singleton without leaking a
    long-lived connection.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def find_plates_for_molecule(
        self,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        excluded_org_ids: set[uuid.UUID] | None = None,
        include_plate_ids: set[uuid.UUID] | None = None,
    ) -> list[MoleculePlateEntry]:
        """Find all registered plates containing batches of this molecule.

        ``excluded_org_ids`` mirrors the NULL-preserving exclusion clause used
        by ``RegisteredPlateRepository.search`` — a plate with no owner org is
        never excluded, only plates explicitly owned by a private foreign org.
        ``include_plate_ids`` (spec §5 loan clause) re-admits plates on active
        loan to the caller's org even when their owner org is excluded — same
        shape as that method's ``include_plate_ids`` arm. Both clauses are
        only added when their set is non-empty: SQLAlchemy's expanding
        bindparam renders an empty ``IN`` as a typeless ``CAST(NULL AS
        INTEGER)`` placeholder subquery, which Postgres refuses to compare
        against a ``uuid`` column (``operator does not exist: uuid =
        integer``) even though the subquery returns no rows.
        """
        base_sql = """
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
        """
        params: dict[str, object] = {"workspace_id": workspace_id, "molecule_id": molecule_id}

        if excluded_org_ids:
            clause = "rp.owner_org_id IS NULL OR rp.owner_org_id NOT IN :excluded_org_ids"
            bind_params = [bindparam("excluded_org_ids", expanding=True)]
            params["excluded_org_ids"] = list(excluded_org_ids)
            if include_plate_ids:
                clause += " OR rp.id IN :include_plate_ids"
                bind_params.append(bindparam("include_plate_ids", expanding=True))
                params["include_plate_ids"] = list(include_plate_ids)
            sql = text(
                base_sql + f" AND ({clause})" + " ORDER BY rp.barcode, well_entry.key"
            ).bindparams(*bind_params)
        else:
            sql = text(base_sql + " ORDER BY rp.barcode, well_entry.key")

        async with self._session_factory() as session:
            result = await session.execute(sql, params)
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
