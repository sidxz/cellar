"""File parsing activity — reads uploaded files and produces chunks for registration.

Runs in the Temporal worker process. Reads files from persistent storage,
parses them using existing parsers (SDF, CSV, XLSX), and returns chunks
of BulkRegistrationItem DTOs for the registration activity.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import structlog
from temporalio import activity

from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.infrastructure.parsers.chemical_file_parser import get_parser
from cellar.infrastructure.temporal.activities.dtos import ChunkItem
from cellar.infrastructure.temporal.task_queues import CHUNK_SIZE

logger = structlog.get_logger(__name__)


@dataclass
class ParseFileInput:
    """Input for the parse_file activity."""

    storage_path: str  # absolute path to uploaded file
    file_format: str  # sdf, csv, xlsx
    filename: str


@dataclass
class ParseFileOutput:
    """Output of file parsing."""

    total_count: int
    chunk_count: int
    chunks: list[list[dict]] = field(default_factory=list)  # serialized ChunkItems


class FileParsingActivities:
    """Temporal activities for parsing chemical data files."""

    @activity.defn
    async def parse_file(self, input: ParseFileInput) -> ParseFileOutput:
        """Parse an uploaded file and return chunks of items.

        For files up to ~50K rows, returns chunks inline in the output.
        The workflow processes each chunk via process_chunk activity.
        """
        path = Path(input.storage_path)
        if not path.exists():
            raise FileNotFoundError(f"Upload not found: {input.storage_path}")

        content = path.read_bytes()
        fmt = BulkRegistrationFileFormat(input.file_format)
        parser = get_parser(fmt)

        activity.heartbeat("parsing file")
        parsed = parser.parse(content, input.filename)

        # Convert to ChunkItem dicts and split into chunks
        all_items: list[dict] = []
        for p in parsed:
            item = ChunkItem(
                row_index=p.row_index,
                name=p.name,
                smiles=p.smiles,
                molecule_type=p.molecule_type,
                external_ids=p.external_ids,
                amount_value=p.amount_value,
                amount_unit=p.amount_unit,
                salt_code=p.salt_code,
                salt_stoichiometry=p.salt_stoichiometry,
                purity=p.purity,
                batch_source=p.batch_source,
                appearance=p.appearance,
            )
            all_items.append(asdict(item))

        # Items with parse errors become error ChunkItems
        error_items: list[dict] = []
        valid_items: list[dict] = []
        for item_dict in all_items:
            # ParsedMoleculeItem.error maps through — items without name+smiles
            # already have error set by the parser
            valid_items.append(item_dict)

        # Split into chunks
        chunks: list[list[dict]] = []
        for i in range(0, len(valid_items), CHUNK_SIZE):
            chunks.append(valid_items[i : i + CHUNK_SIZE])

        activity.heartbeat(f"parsed {len(valid_items)} items into {len(chunks)} chunks")

        logger.info(
            "Parsed %s: %d items, %d chunks",
            input.filename,
            len(valid_items),
            len(chunks),
        )

        return ParseFileOutput(
            total_count=len(valid_items),
            chunk_count=len(chunks),
            chunks=chunks,
        )


def save_upload_to_storage(content: bytes, filename: str) -> str:
    """Save an uploaded file to persistent storage. Returns the absolute path.

    Called from the API route (not an activity). Uses STORAGE_ROOT env var.
    """
    storage_root = os.getenv("STORAGE_ROOT", "./data/storage")
    upload_id = str(uuid.uuid4())
    upload_dir = Path(storage_root) / "bulk-imports" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    file_path.write_bytes(content)
    return str(file_path)
