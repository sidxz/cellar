"""CDD fetch activities — trigger async export, poll status, save results to disk.

CDD Vault uses an async export model for molecules:
1. Trigger export → get export_id
2. Poll /export_progress/{id} until finished, then download /exports/{id}
3. Save result JSON to disk (too large for Temporal payloads)

API key is NEVER in Temporal history. Activities receive a ``secret_ref``
and resolve the actual key from SecretProvider at execution time.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from cellar.application.cdd_import.molecule_identifiers import match_identifiers
from cellar.application.cdd_import.molecule_mapper import (
    compute_labels,
    compute_names,
    map_cdd_molecules,
)
from cellar.application.cdd_import.plate_mapper import map_cdd_plate
from cellar.application.chemical_registration.bulk_column_mapping import ColumnMapping
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.domain.workspace_config.data_source import EntityMapping
from cellar.infrastructure.cdd.client import CddVaultClient
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_sync_repository import (  # noqa: E501
    CddMoleculeSyncRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.storage.fsspec_client import StorageSettings
from cellar.infrastructure.temporal.activities.dtos import (
    CddPollExportInput,
    CddPollExportOutput,
    CddStartExportInput,
    CddStartExportOutput,
    CddStartPlateExportInput,
    CddSyncWatermarkInput,
    CddSyncWatermarkOutput,
    ChunkItem,
    LoadExportChunkInput,
    LoadExportChunkOutput,
    LoadPlateChunkInput,
    LoadPlateChunkOutput,
)
from cellar.infrastructure.temporal.task_queues import CHUNK_SIZE

logger = structlog.get_logger(__name__)

# The import workflows give the poll activities a 60 s heartbeat timeout.
_HEARTBEAT_EVERY = 10.0

_LABELS = "labels.json"
_MANIFEST = "manifest.json"
_NAMES = "names.json"


async def _while_heartbeating[T](work: Awaitable[T], details: str) -> T:
    """Await ``work``, heartbeating now and every ``_HEARTBEAT_EVERY`` seconds until it ends."""
    task = asyncio.ensure_future(work)
    try:
        while True:
            activity.heartbeat(details)
            done, _ = await asyncio.wait({task}, timeout=_HEARTBEAT_EVERY)
            if done:
                return task.result()
    finally:
        task.cancel()


def cdd_export_dir(export_id: int) -> Path:
    """Where one CDD export is kept on disk: the raw download, its manifest, its chunks."""
    return StorageSettings().subdir("cdd-exports") / str(export_id)


def export_on_disk(export_dir: Path) -> bool:
    """The export was split into chunks (the manifest is written with them)."""
    return (export_dir / _MANIFEST).exists()


def _split_export(
    raw_path: Path,
    export_dir: Path,
    mapping: ColumnMapping | None = None,
    id_mapping: EntityMapping | None = None,
) -> tuple[int, int]:
    """Parse a downloaded export into a manifest plus chunk files. Blocking: run it in a thread.

    With a molecule export's registration ``mapping`` (and its molecule ``id_mapping``),
    also writes what ``load_export_chunk`` does not store: ``labels.json``, the compound
    IDs on 2+ molecules of this export (``compute_labels``), and ``names.json``, every
    molecule's name and vault id (``compute_names``). A Full run sees the whole vault;
    Sync and Specific molecules only what they read.

    Returns ``(count, number_of_objects)``.
    """
    # Parse from disk (file-based, avoids double-memory of response.json())
    with open(raw_path) as f:
        data = json.load(f)

    objects = data.get("objects", [])
    count = data.get("count", len(objects))

    # Write manifest
    (export_dir / _MANIFEST).write_text(json.dumps({"count": len(objects)}))
    if mapping is not None:
        (export_dir / _LABELS).write_text(json.dumps(compute_labels(objects, mapping)))
        if id_mapping is not None:
            names = compute_names(objects, mapping, id_mapping)
            (export_dir / _NAMES).write_text(json.dumps(names))

    # Split into chunk files
    for i in range(0, len(objects), CHUNK_SIZE):
        chunk_path = export_dir / f"chunk_{i:06d}.json"
        chunk_path.write_text(json.dumps(objects[i : i + CHUNK_SIZE]))

    return count, len(objects)


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

        # Filtered import: look the names up, then export those molecules by vault id.
        molecule_ids = input.molecule_ids
        if input.names is not None:
            molecules = await client.find_molecules_by_names(input.vault_id, api_key, input.names)
            molecule_ids = match_identifiers(input.names, molecules).molecule_ids
            if not molecule_ids:
                # An export with no ids would not be narrowed to anything.
                raise ApplicationError(
                    "None of the requested molecules were found in the vault",
                    non_retryable=True,
                )

        export_id = await client.start_molecule_export(
            input.vault_id,
            api_key,
            molecule_ids=molecule_ids,
            modified_after=input.modified_after,
            max_molecules=input.max_molecules,
        )

        # For modified_after/full exports, we don't know the exact count
        # until the export finishes. Use vault total as estimate.
        effective_count = total_count
        if molecule_ids is not None:
            effective_count = len(molecule_ids)
        elif input.max_molecules is not None:
            effective_count = min(input.max_molecules, total_count)

        logger.info(
            "cdd_fetch.export_started",
            vault_id=input.vault_id,
            export_id=export_id,
            total_count=total_count,
            effective_count=effective_count,
            mode="filtered"
            if input.names is not None
            else "modified_after"
            if input.modified_after
            else "full",
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

        # "downloaded" = finished and fetched before (a retry after a crash).
        # Anything else (failed, canceled) is final — retrying cannot fix it.
        if status not in ("finished", "downloaded"):
            raise ApplicationError(
                f"CDD export {input.export_id} ended with status {status!r}",
                non_retryable=True,
            )

        # Export finished — set up storage directory
        export_dir = cdd_export_dir(input.export_id)
        export_dir.mkdir(parents=True, exist_ok=True)

        raw_path = export_dir / "raw_export.json"
        tmp_path = export_dir / "raw_export.json.tmp"

        # Clean up any partial download from a previous crashed attempt
        if tmp_path.exists():
            tmp_path.unlink()
            logger.info("cdd_fetch.partial_download_removed", tmp_path=str(tmp_path))

        # If raw file already exists (retry after chunk-splitting failed),
        # skip the download — reuse what we already have.
        if not raw_path.exists():
            logger.info("cdd_fetch.export_streaming", export_id=input.export_id)
            await _while_heartbeating(
                client.stream_export_to_file(
                    input.vault_id,
                    api_key,
                    input.export_id,
                    str(tmp_path),
                ),
                f"export {input.export_id}: downloading",
            )
            # Atomic rename — only complete downloads get the final name
            tmp_path.rename(raw_path)
            raw_size = raw_path.stat().st_size
            logger.info(
                "cdd_fetch.export_downloaded",
                export_id=input.export_id,
                raw_bytes=raw_size,
            )
        else:
            raw_size = raw_path.stat().st_size
            logger.info(
                "cdd_fetch.export_already_on_disk",
                export_id=input.export_id,
                raw_bytes=raw_size,
            )

        # In a thread so the loop keeps heartbeating. ponytail: json.load holds the GIL, so
        # the bare parse still stalls heartbeats (~4 s/GB); stream-parse if exports near 10 GB.
        mapping = (
            ColumnMapping.from_dict({"columns": input.registration_mapping})
            if input.registration_mapping
            else None
        )
        id_mapping = next(
            (
                em
                for em in map(EntityMapping.from_dict, input.entity_mappings or [])
                if em.entity_type == "molecule"
            ),
            None,
        )
        count, object_count = await _while_heartbeating(
            asyncio.to_thread(_split_export, raw_path, export_dir, mapping, id_mapping),
            f"export {input.export_id}: parsing",
        )
        logger.info("cdd_fetch.export_parsed", export_id=input.export_id, object_count=count)

        total_bytes = sum(f.stat().st_size for f in export_dir.glob("chunk_*.json"))
        logger.info(
            "cdd_fetch.export_saved",
            export_dir=str(export_dir),
            total_bytes=total_bytes,
            chunk_count=(object_count + CHUNK_SIZE - 1) // CHUNK_SIZE,
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

        manifest = json.loads((export_dir / _MANIFEST).read_text())
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
        """Load a chunk of molecules from a pre-split chunk file and map it to ChunkItems:
        one per CDD batch, or one for a molecule without batches."""

        chunk_objects, has_more = self._load_raw_chunk(
            input.storage_path,
            input.offset,
            input.limit,
            input.max_molecules,
        )

        if not chunk_objects:
            return LoadExportChunkOutput(items=[], has_more=False, molecule_count=0)

        if not input.registration_mapping:
            raise ApplicationError(
                "This import was started without a field mapping; start it again",
                non_retryable=True,
            )
        mappings = {
            em.entity_type: em for em in map(EntityMapping.from_dict, input.entity_mappings or [])
        }
        if "molecule" not in mappings:
            raise ValueError("No molecule EntityMapping found in entity_mappings")

        def _read(name: str) -> dict:
            path = Path(input.storage_path) / name
            return json.loads(path.read_text()) if path.exists() else {}

        mapped, _ = map_cdd_molecules(
            chunk_objects,
            ColumnMapping.from_dict({"columns": input.registration_mapping}),
            id_mapping=mappings["molecule"],
            batch_id_mapping=mappings.get("batch"),
            labels=_read(_LABELS),
            names=_read(_NAMES),
        )

        items: list[dict] = []
        for mol_idx, mol in enumerate(mapped):
            base: dict[str, Any] = {
                "row_index": input.offset + mol_idx,
                "name": mol.name,
                "smiles": mol.smiles,
                "molecule_type": mol.molecule_type,
                "external_ids": mol.external_ids,
                "cdd_molecule_id": mol.cdd_molecule_id,
                "cdd_modified_at": mol.cdd_modified_at,
            }
            if not mol.batches:
                items.append(asdict(ChunkItem(**base, warnings=mol.warnings)))
            for i, b in enumerate(mol.batches):
                item = ChunkItem(
                    **base,
                    batch_ids=b.batch_ids,
                    amount_value=b.amount_value,
                    amount_unit=b.amount_unit,
                    salt_code=b.salt_code,
                    salt_stoichiometry=b.salt_stoichiometry,
                    purity=b.purity,
                    batch_source=b.batch_source,
                    appearance=b.appearance,
                    cdd_batch_id=b.cdd_batch_id,
                    # the molecule's on its first row only, so a report counts them once
                    warnings=[*(mol.warnings if i == 0 else ()), *b.warnings],
                )
                items.append(asdict(item))

        activity.heartbeat(f"loaded chunk offset={input.offset} items={len(items)}")
        return LoadExportChunkOutput(items=items, has_more=has_more, molecule_count=len(mapped))

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
            "cdd_fetch.sync_watermark",
            vault_id=input.vault_id,
            last_modified=modified_after_iso,
            synced_count=known_count,
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
            "cdd_fetch.plate_export_started",
            vault_id=input.vault_id,
            export_id=export_id,
            total_count=total_count,
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
