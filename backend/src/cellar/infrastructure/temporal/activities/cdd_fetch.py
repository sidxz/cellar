"""CDD fetch activities — trigger async export, poll status, save results to disk.

CDD Vault uses an async export model for molecules:
1. Trigger export → get export_id
2. Poll /exports/{id} until finished (302 redirect to results)
3. Save result JSON to disk (too large for Temporal payloads)

API key is NEVER in Temporal history. Activities receive a ``secret_ref``
and resolve the actual key from SecretProvider at execution time.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from cellar.application.cdd_import.molecule_mapper import map_cdd_molecules
from cellar.application.cdd_import.plate_mapper import map_cdd_plate
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.domain.workspace_config.data_source import EntityMapping
from cellar.infrastructure.cdd.client import CddVaultClient
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_sync_repository import (  # noqa: E501
    CddMoleculeSyncRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.temporal.activities.dtos import (
    CddPollExportInput,
    CddPollExportOutput,
    CddStartExportInput,
    CddStartExportOutput,
    CddStartPlateExportInput,
    CddSyncWatermarkInput,
    CddSyncWatermarkOutput,
    LoadExportChunkInput,
    LoadExportChunkOutput,
    LoadPlateChunkInput,
    LoadPlateChunkOutput,
)
from cellar.infrastructure.temporal.task_queues import CHUNK_SIZE

logger = structlog.get_logger(__name__)


class CddFetchActivities:
    """Temporal activities for fetching molecules from CDD Vault."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        secret_provider: SecretProvider,
        cdd_client: CddVaultClient,
    ) -> None:
        self._session_factory = session_factory
        self._secret_provider = secret_provider
        self._cdd_client = cdd_client

    async def _resolve_api_key(self, secret_ref: str) -> str:
        key = await self._secret_provider.get_secret(secret_ref)
        if key is None:
            raise ValueError(f"CDD API key not found for secret ref: {secret_ref}")
        return key

    @activity.defn
    async def start_molecule_export(self, input: CddStartExportInput) -> CddStartExportOutput:
        """Trigger an async molecule export on CDD via POST /molecules/query.

        The client handles all parameter combinations (molecule_ids,
        modified_after, max_molecules) in the JSON body — no URL limits.
        """
        api_key = await self._resolve_api_key(input.secret_ref)
        client = self._cdd_client

        total_count = await client.get_molecule_count(input.vault_id, api_key)

        export_id = await client.start_molecule_export(
            input.vault_id,
            api_key,
            molecule_ids=input.molecule_ids,
            modified_after=input.modified_after,
            max_molecules=input.max_molecules,
        )

        # For modified_after/full exports, we don't know the exact count
        # until the export finishes. Use vault total as estimate.
        effective_count = total_count
        if input.molecule_ids is not None:
            effective_count = len(input.molecule_ids)
        elif input.max_molecules is not None:
            effective_count = min(input.max_molecules, total_count)

        logger.info(
            "CDD export started: vault=%s export_id=%d total=%d effective=%d mode=%s",
            input.vault_id,
            export_id,
            total_count,
            effective_count,
            "modified_after" if input.modified_after else "full",
        )
        return CddStartExportOutput(export_id=export_id, total_count=effective_count)

    @activity.defn
    async def poll_molecule_export(self, input: CddPollExportInput) -> CddPollExportOutput:
        """Poll a CDD export. When finished, streams result to disk and splits into chunks.

        The export result can be hundreds of MB — streamed directly to disk,
        never held fully in memory. Too large for Temporal payloads (4MB gRPC limit).
        """
        api_key = await self._resolve_api_key(input.secret_ref)
        client = self._cdd_client

        # Lightweight status check (no data download)
        status = await client.check_export_progress(
            input.vault_id,
            api_key,
            input.export_id,
        )
        if status in ("new", "started"):
            activity.heartbeat(f"export {input.export_id}: {status}")
            return CddPollExportOutput(finished=False)

        if status == "canceled":
            raise RuntimeError(f"CDD export {input.export_id} was canceled")

        # Export finished — set up storage directory
        storage_root = os.getenv("STORAGE_ROOT", "./data/storage")
        export_dir = Path(storage_root) / "cdd-exports" / str(input.export_id)
        export_dir.mkdir(parents=True, exist_ok=True)

        raw_path = export_dir / "raw_export.json"
        tmp_path = export_dir / "raw_export.json.tmp"

        # Clean up any partial download from a previous crashed attempt
        if tmp_path.exists():
            tmp_path.unlink()
            logger.info("Removed partial download %s", tmp_path)

        # If raw file already exists (retry after chunk-splitting failed),
        # skip the download — reuse what we already have.
        if not raw_path.exists():
            logger.info("Streaming CDD export %d to disk...", input.export_id)
            activity.heartbeat(f"export {input.export_id}: downloading")
            await client.stream_export_to_file(
                input.vault_id,
                api_key,
                input.export_id,
                str(tmp_path),
            )
            # Atomic rename — only complete downloads get the final name
            tmp_path.rename(raw_path)
            raw_size = raw_path.stat().st_size
            logger.info("CDD export %d downloaded: %d bytes", input.export_id, raw_size)
        else:
            raw_size = raw_path.stat().st_size
            logger.info(
                "CDD export %d already on disk (%d bytes), reusing", input.export_id, raw_size
            )

        # Parse from disk (file-based, avoids double-memory of response.json())
        activity.heartbeat(f"export {input.export_id}: parsing")
        with open(raw_path) as f:
            data = json.load(f)

        objects = data.get("objects", [])
        count = data.get("count", len(objects))
        logger.info("CDD export %d: %d objects", input.export_id, count)

        # Write manifest
        (export_dir / "manifest.json").write_text(json.dumps({"count": len(objects)}))

        # Split into chunk files
        for i in range(0, len(objects), CHUNK_SIZE):
            chunk_path = export_dir / f"chunk_{i:06d}.json"
            chunk_path.write_text(json.dumps(objects[i : i + CHUNK_SIZE]))

        total_bytes = sum(f.stat().st_size for f in export_dir.glob("chunk_*.json"))
        logger.info(
            "Saved CDD export to %s (%d bytes across %d chunks)",
            export_dir,
            total_bytes,
            (len(objects) + CHUNK_SIZE - 1) // CHUNK_SIZE,
        )

        return CddPollExportOutput(finished=True, count=count, storage_path=str(export_dir))

    @staticmethod
    def _load_raw_chunk(
        storage_path: str,
        offset: int,
        limit: int,
        max_items: int | None = None,
    ) -> tuple[list[dict], bool]:
        """Load raw JSON objects from a pre-split chunk file.

        Chunk files on disk are split at CHUNK_SIZE (250) intervals.
        The caller may request a smaller slice (e.g. plates use limit=5).
        This method finds the right file and sub-slices within it.

        Returns (objects, has_more). Generic — works for any CDD entity type.
        """
        export_dir = Path(storage_path)
        if not export_dir.exists():
            raise FileNotFoundError(f"Export directory not found: {storage_path}")

        manifest = json.loads((export_dir / "manifest.json").read_text())
        total_objects = manifest["count"]

        effective_total = min(total_objects, max_items) if max_items else total_objects

        if offset >= effective_total:
            return [], False

        # Find the chunk file that contains this offset.
        # Files are named chunk_000000.json, chunk_000250.json, etc.
        file_offset = (offset // CHUNK_SIZE) * CHUNK_SIZE
        chunk_path = export_dir / f"chunk_{file_offset:06d}.json"
        if not chunk_path.exists():
            return [], False

        chunk_objects = json.loads(chunk_path.read_text())

        # Sub-slice within the file
        inner_offset = offset - file_offset
        chunk_objects = chunk_objects[inner_offset : inner_offset + limit]

        # Cap at effective_total
        remaining = effective_total - offset
        if remaining < len(chunk_objects):
            chunk_objects = chunk_objects[:remaining]

        has_more = (offset + len(chunk_objects)) < effective_total
        return chunk_objects, has_more

    @activity.defn
    async def load_export_chunk(self, input: LoadExportChunkInput) -> LoadExportChunkOutput:
        """Load a chunk of molecules from a pre-split chunk file and map to ChunkItems."""

        chunk_objects, has_more = self._load_raw_chunk(
            input.storage_path,
            input.offset,
            input.limit,
            input.max_molecules,
        )

        if not chunk_objects:
            return LoadExportChunkOutput(items=[], skipped=0, has_more=False, molecule_count=0)

        # Deserialize entity mappings from workflow input
        mol_mapping: EntityMapping | None = None
        batch_mapping: EntityMapping | None = None
        if input.entity_mappings:
            for em_dict in input.entity_mappings:
                em = EntityMapping.from_dict(em_dict)
                if em.entity_type == "molecule":
                    mol_mapping = em
                elif em.entity_type == "batch":
                    batch_mapping = em

        if mol_mapping is None:
            raise ValueError("No molecule EntityMapping found in entity_mappings")

        mapped, _ = map_cdd_molecules(chunk_objects, mol_mapping, batch_mapping)

        items: list[dict] = []
        skipped = 0
        molecule_count = 0
        for mol_idx, mol in enumerate(mapped):
            if mol.skipped:
                skipped += 1
                continue
            row_index = input.offset + mol_idx
            molecule_count += 1
            if mol.batches:
                for batch in mol.batches:
                    items.append(
                        {
                            "row_index": row_index,
                            "name": mol.name,
                            "smiles": mol.smiles,
                            "molecule_type": mol.molecule_type,
                            "external_ids": mol.external_ids,
                            "amount_value": batch.amount_value,
                            "amount_unit": batch.amount_unit,
                            "salt_code": batch.salt_code,
                            "salt_stoichiometry": batch.salt_stoichiometry,
                            "purity": batch.purity,
                            "batch_source": batch.batch_source,
                            "appearance": batch.appearance,
                            "vendor_catalog_number": batch.batch_name,
                            "cdd_molecule_id": mol.cdd_molecule_id,
                            "cdd_batch_id": batch.cdd_batch_id,
                            "cdd_modified_at": mol.cdd_modified_at,
                        }
                    )
            else:
                items.append(
                    {
                        "row_index": row_index,
                        "name": mol.name,
                        "smiles": mol.smiles,
                        "molecule_type": mol.molecule_type,
                        "external_ids": mol.external_ids,
                        "cdd_molecule_id": mol.cdd_molecule_id,
                        "cdd_modified_at": mol.cdd_modified_at,
                    }
                )

        activity.heartbeat(
            f"loaded chunk offset={input.offset} items={len(items)} skipped={skipped}"
        )
        return LoadExportChunkOutput(
            items=items, skipped=skipped, has_more=has_more, molecule_count=molecule_count
        )

    @activity.defn
    async def get_sync_watermark(self, input: CddSyncWatermarkInput) -> CddSyncWatermarkOutput:
        """Look up the latest cdd_modified_at for this vault — the sync high-water-mark.

        Returns the ISO 8601 timestamp to pass as modified_after, or None
        if no prior sync exists (meaning: first sync = full export).
        """
        session_factory = self._session_factory
        uow = AsyncUnitOfWork(session_factory)
        sync_repo = CddMoleculeSyncRepository(uow)

        async with uow:
            last_modified = await sync_repo.get_last_modified_at(
                uuid.UUID(input.workspace_id), input.vault_id
            )
            known_count = len(
                await sync_repo.get_known_cdd_ids(uuid.UUID(input.workspace_id), input.vault_id)
            )

        modified_after_iso = last_modified.isoformat() if last_modified else None

        logger.info(
            "Sync watermark: vault=%s last_modified=%s synced=%d",
            input.vault_id,
            modified_after_iso,
            known_count,
        )

        return CddSyncWatermarkOutput(
            modified_after=modified_after_iso,
            synced_count=known_count,
        )

    # ------------------------------------------------------------------
    # CDD plate export
    # ------------------------------------------------------------------

    @activity.defn
    async def start_plate_export(self, input: CddStartPlateExportInput) -> CddStartExportOutput:
        """Trigger an async plate export on CDD."""
        api_key = await self._resolve_api_key(input.secret_ref)
        client = self._cdd_client

        total_count = await client.get_plate_count(input.vault_id, api_key)

        export_id = await client.start_export(
            input.vault_id,
            api_key,
            "plates",
        )

        logger.info(
            "CDD plate export started: vault=%s export_id=%d total=%d",
            input.vault_id,
            export_id,
            total_count,
        )
        return CddStartExportOutput(export_id=export_id, total_count=total_count)

    @activity.defn
    async def poll_plate_export(self, input: CddPollExportInput) -> CddPollExportOutput:
        """Poll a CDD plate export. Identical to molecule poll — reuses stream_export_to_file."""
        return await self.poll_molecule_export(input)

    @activity.defn
    async def load_plate_chunk(self, input: LoadPlateChunkInput) -> LoadPlateChunkOutput:
        """Load a chunk of plates from disk and map to PlateChunkItem dicts."""
        chunk_objects, has_more = self._load_raw_chunk(
            input.storage_path,
            input.offset,
            input.limit,
        )

        if not chunk_objects:
            return LoadPlateChunkOutput(items=[], has_more=False)

        # Deserialize entity mappings from workflow input
        plate_mapping: EntityMapping | None = None
        well_mapping: EntityMapping | None = None
        if input.entity_mappings:
            for em_dict in input.entity_mappings:
                em = EntityMapping.from_dict(em_dict)
                if em.entity_type == "plate":
                    plate_mapping = em
                elif em.entity_type == "well":
                    well_mapping = em

        if plate_mapping is None:
            raise ValueError("No plate EntityMapping found in entity_mappings")

        items: list[dict] = []
        for raw in chunk_objects:
            mapped = map_cdd_plate(raw, plate_mapping, well_mapping)
            items.append(
                {
                    "cdd_plate_id": mapped.cdd_plate_id,
                    "name": mapped.name,
                    "format": mapped.format,
                    "wells": [
                        {"position": w.position, "cdd_batch_id": w.cdd_batch_id}
                        for w in mapped.wells
                    ],
                }
            )

        activity.heartbeat(f"loaded plate chunk offset={input.offset} plates={len(items)}")
        return LoadPlateChunkOutput(items=items, has_more=has_more)
