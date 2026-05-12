"""One-off script: resume CDD molecule import from existing export files on disk.

Usage (from backend/):
    uv run python scripts/resume_cdd_import.py

This creates a DB tracking record in PROCESSING state and starts a Temporal
workflow with resume fields so it skips export/download and jumps straight
to chunk processing.
"""

import asyncio
import uuid

from temporalio.client import Client

# --- Config: edit these if needed ---
WORKSPACE_ID = "442df0cf-e618-4938-a089-80ae2f1e43e7"
CDD_VAULT_ID = "4443"
ORIGINATING_ORG_ID = "cf6f3437-d3d2-431b-ad4a-91faf1f30e93"
SUBMITTED_BY = "eabe1e6c-4f47-46b5-bdf6-4eccca2b8b97"
SECRET_REF = f"{WORKSPACE_ID}:cdd_vault"
IMPORT_MODE = "full_vault"

# Path as seen by the worker (runs locally via `make dev-worker`, not in Docker)
STORAGE_PATH = "./data/storage/cdd-exports/71884649"
TOTAL_COUNT = 214043

TEMPORAL_ADDRESS = "localhost:7233"
TASK_QUEUE = "cellar-main"


async def main():
    # 1. Create DB record in PROCESSING state
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://cellar:cellar@localhost:5432/cellar")

    import_id = uuid.uuid4()
    workflow_id = f"cdd-mol-import-{WORKSPACE_ID}-{uuid.uuid4()}"
    now = sa.text("NOW()")

    async with engine.begin() as conn:
        await conn.execute(
            sa.text("""
                INSERT INTO cdd_molecule_imports (
                    id, workspace_id, cdd_vault_id, import_mode,
                    originating_org_id, submitted_by, workflow_id,
                    status, total_count,
                    registered_count, duplicate_count, error_count, skipped_count,
                    last_processed_offset,
                    submitted_at, created_at, updated_at, version
                ) VALUES (
                    :id, :workspace_id, :cdd_vault_id, :import_mode,
                    :originating_org_id, :submitted_by, :workflow_id,
                    'processing', :total_count,
                    0, 0, 0, 0,
                    0,
                    NOW(), NOW(), NOW(), 1
                )
            """),
            {
                "id": str(import_id),
                "workspace_id": WORKSPACE_ID,
                "cdd_vault_id": CDD_VAULT_ID,
                "import_mode": IMPORT_MODE,
                "originating_org_id": ORIGINATING_ORG_ID,
                "submitted_by": SUBMITTED_BY,
                "workflow_id": workflow_id,
                "total_count": TOTAL_COUNT,
            },
        )

    await engine.dispose()
    print(f"Created import record: {import_id}")
    print(f"Workflow ID: {workflow_id}")

    # 2. Start Temporal workflow with resume fields
    from cellar.domain.workspace_config.data_source import get_default_template
    from cellar.infrastructure.temporal.workflows.cdd_vault_import import (
        CddVaultImportWorkflow,
        CddVaultImportWorkflowInput,
    )

    client = await Client.connect(TEMPORAL_ADDRESS)

    entity_mappings = [em.to_dict() for em in get_default_template("cdd_vault")]

    await client.start_workflow(
        CddVaultImportWorkflow.run,
        CddVaultImportWorkflowInput(
            workspace_id=WORKSPACE_ID,
            cdd_vault_id=CDD_VAULT_ID,
            import_mode=IMPORT_MODE,
            submitted_by=SUBMITTED_BY,
            originating_org_id=ORIGINATING_ORG_ID,
            secret_ref=SECRET_REF,
            entity_mappings=entity_mappings,
            # Resume fields — skip export, jump to processing
            import_id=str(import_id),
            storage_path=STORAGE_PATH,
            total_count=TOTAL_COUNT,
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    print(f"Workflow started! Monitor at: http://localhost:8080/workflows/{workflow_id}")


if __name__ == "__main__":
    asyncio.run(main())
