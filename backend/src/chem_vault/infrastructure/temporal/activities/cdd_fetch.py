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
import logging
import os
import uuid
from pathlib import Path

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity

from chem_vault.application.cdd_import.molecule_mapper import map_cdd_molecules
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.infrastructure.cdd.client import CddVaultClient
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_sync_repository import (
    CddMoleculeSyncRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.temporal.activities.dtos import (
    CddPollExportInput,
    CddPollExportOutput,
    CddStartExportInput,
    CddStartExportOutput,
    CddSyncWatermarkInput,
    CddSyncWatermarkOutput,
    LoadExportChunkInput,
    LoadExportChunkOutput,
)
from chem_vault.infrastructure.temporal.task_queues import CHUNK_SIZE

logger = logging.getLogger(__name__)


class CddFetchActivities:
    """Temporal activities for fetching molecules from CDD Vault."""

    def __init__(self, container: Container) -> None:
        self._container = container

    async def _resolve_api_key(self, secret_ref: str) -> str:
        provider = self._container[SecretProvider]
        key = await provider.get_secret(secret_ref)
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
        client = self._container[CddVaultClient]

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
            input.vault_id, export_id, total_count, effective_count,
            "modified_after" if input.modified_after else "full",
        )
        return CddStartExportOutput(export_id=export_id, total_count=effective_count)

    @activity.defn
    async def poll_molecule_export(self, input: CddPollExportInput) -> CddPollExportOutput:
        """Poll a CDD export. When finished, saves objects to disk and returns the path.

        The export result can be hundreds of MB — far too large for Temporal
        payloads (4MB gRPC limit). We save to STORAGE_ROOT and return the path.
        """
        api_key = await self._resolve_api_key(input.secret_ref)
        client = self._container[CddVaultClient]

        data = await client.get_export_status(input.vault_id, api_key, input.export_id)

        status = data.get("status")
        if status in ("new", "started"):
            activity.heartbeat(f"export {input.export_id}: {status}")
            return CddPollExportOutput(finished=False)

        objects = data.get("objects", [])
        count = data.get("count", len(objects))

        logger.info("CDD export %d finished: %d molecules", input.export_id, count)

        # Save to disk as per-chunk files so load_export_chunk doesn't re-parse
        # the entire export on every invocation.
        storage_root = os.getenv("STORAGE_ROOT", "./data/storage")
        export_dir = Path(storage_root) / "cdd-exports" / str(input.export_id)
        export_dir.mkdir(parents=True, exist_ok=True)

        # Write a manifest with total count
        (export_dir / "manifest.json").write_text(json.dumps({"count": len(objects)}))

        # Split into chunk files
        for i in range(0, len(objects), CHUNK_SIZE):
            chunk_path = export_dir / f"chunk_{i:06d}.json"
            chunk_path.write_text(json.dumps(objects[i : i + CHUNK_SIZE]))

        total_bytes = sum(f.stat().st_size for f in export_dir.glob("chunk_*.json"))
        logger.info("Saved CDD export to %s (%d bytes across %d chunks)",
                     export_dir, total_bytes, (len(objects) + CHUNK_SIZE - 1) // CHUNK_SIZE)

        return CddPollExportOutput(finished=True, count=count, storage_path=str(export_dir))

    @activity.defn
    async def load_export_chunk(self, input: LoadExportChunkInput) -> LoadExportChunkOutput:
        """Load a chunk of molecules from a pre-split chunk file and map to ChunkItems."""

        export_dir = Path(input.storage_path)
        if not export_dir.exists():
            raise FileNotFoundError(f"Export directory not found: {input.storage_path}")

        manifest = json.loads((export_dir / "manifest.json").read_text())
        total_objects = manifest["count"]

        # Cap at max_molecules if set
        effective_total = min(total_objects, input.max_molecules) if input.max_molecules else total_objects

        # Read the pre-split chunk file for this offset
        chunk_path = export_dir / f"chunk_{input.offset:06d}.json"
        if not chunk_path.exists():
            # No chunk at this offset — we're past the end
            return LoadExportChunkOutput(items=[], skipped=0, has_more=False, molecule_count=0)

        chunk_objects = json.loads(chunk_path.read_text())

        # If max_molecules limits us mid-chunk, trim
        remaining = effective_total - input.offset
        if remaining < len(chunk_objects):
            chunk_objects = chunk_objects[:remaining]

        has_more = (input.offset + input.limit) < effective_total

        mapped, _ = map_cdd_molecules(chunk_objects)

        items: list[dict] = []
        skipped = 0
        molecule_count = 0
        for mol_idx, mol in enumerate(mapped):
            if mol.skipped:
                skipped += 1
                continue
            # row_index is a sequential index (not CDD ID) so mol_outcomes
            # deduplication in process_chunk works even if CDD IDs are missing.
            row_index = input.offset + mol_idx
            molecule_count += 1
            if mol.batches:
                for batch in mol.batches:
                    items.append({
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
                        "cdd_modified_at": mol.cdd_modified_at,
                    })
            else:
                items.append({
                    "row_index": row_index,
                    "name": mol.name,
                    "smiles": mol.smiles,
                    "molecule_type": mol.molecule_type,
                    "external_ids": mol.external_ids,
                    "cdd_molecule_id": mol.cdd_molecule_id,
                    "cdd_modified_at": mol.cdd_modified_at,
                })

        activity.heartbeat(f"loaded chunk offset={input.offset} items={len(items)} skipped={skipped}")
        return LoadExportChunkOutput(items=items, skipped=skipped, has_more=has_more, molecule_count=molecule_count)

    @activity.defn
    async def get_sync_watermark(self, input: CddSyncWatermarkInput) -> CddSyncWatermarkOutput:
        """Look up the latest cdd_modified_at for this vault — the sync high-water-mark.

        Returns the ISO 8601 timestamp to pass as modified_after, or None
        if no prior sync exists (meaning: first sync = full export).
        """
        session_factory = self._container[async_sessionmaker]
        uow = AsyncUnitOfWork(session_factory)
        sync_repo = CddMoleculeSyncRepository(uow)

        async with uow:
            last_modified = await sync_repo.get_last_modified_at(
                uuid.UUID(input.workspace_id), input.vault_id
            )
            known_count = len(
                await sync_repo.get_known_cdd_ids(
                    uuid.UUID(input.workspace_id), input.vault_id
                )
            )

        modified_after_iso = last_modified.isoformat() if last_modified else None

        logger.info(
            "Sync watermark: vault=%s last_modified=%s synced=%d",
            input.vault_id, modified_after_iso, known_count,
        )

        return CddSyncWatermarkOutput(
            modified_after=modified_after_iso,
            synced_count=known_count,
        )
