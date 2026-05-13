"""Demo data loader — seeds all entity types via DI container + use cases.

Usage:
    cd backend && uv run python ../demo-data/load.py

Requires:
    - PostgreSQL running (make up)
    - DATABASE_URL set in environment or .env
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load .env from repo root (DATABASE_URL etc.)
_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Add backend/src to path so cellar imports work
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

import uuid as _uuid

import loaders._context as _ctx
from loaders._context import DEFAULT_WORKSPACE_ID, DemoAuthContext, DemoContext, IdRegistry

DATA_DIR = Path(__file__).resolve().parent / "data"


def _resolve_workspace_id() -> _uuid.UUID:
    """Read workspace ID from WORKSPACE_ID env var, or use default."""
    raw = os.environ.get("WORKSPACE_ID", "").strip()
    if raw:
        return _uuid.UUID(raw)
    return DEFAULT_WORKSPACE_ID


async def main() -> int:
    from cellar.infrastructure.di.container import create_container

    ws_id = _resolve_workspace_id()

    # Set BEFORE importing loaders — their top-level `from ._context import WORKSPACE_ID`
    # captures whatever value _context.WORKSPACE_ID holds at import time.
    _ctx.WORKSPACE_ID = ws_id

    from loaders import (
        s01_workspace,
        s02_organizations,
        s03_salts,
        s04_storage,
        s05_molecules,
        s06_projects,
        s07_targets,
        s08_protocols,
        s09_plate_templates,
        s10_batches,
        s11_samples,
        s12_plates,
        s13_runs,
        s14_readouts,
        s15_dose_response,
        s16_synthesis_routes,
        s17_synthesis_requests,
        s18_sample_requests,
        s19_shipments,
        s20_collections,
        s21_saved_searches,
    )

    stages = [
        ("Workspace settings", s01_workspace.load),
        ("Organizations", s02_organizations.load),
        ("Salt catalog", s03_salts.load),
        ("Storage locations", s04_storage.load),
        ("Molecules", s05_molecules.load),
        ("Projects", s06_projects.load),
        ("Targets", s07_targets.load),
        ("Protocols", s08_protocols.load),
        ("Plate templates", s09_plate_templates.load),
        ("Batches", s10_batches.load),
        ("Samples", s11_samples.load),
        ("Registered plates", s12_plates.load),
        ("Screening runs", s13_runs.load),
        ("Readout data", s14_readouts.load),
        ("Dose-response curves", s15_dose_response.load),
        ("Synthesis routes", s16_synthesis_routes.load),
        ("Synthesis requests", s17_synthesis_requests.load),
        ("Sample requests", s18_sample_requests.load),
        ("Shipments", s19_shipments.load),
        ("Collections", s20_collections.load),
        ("Saved searches", s21_saved_searches.load),
    ]

    print("\n  Cellar Demo Data Loader")
    print("  " + "=" * 40)
    print(f"  Workspace: {ws_id}")

    container = create_container()
    registry = IdRegistry()
    auth = DemoAuthContext(workspace_id=ws_id)
    ctx = DemoContext(
        container=container,
        registry=registry,
        data_dir=DATA_DIR,
        workspace_id=ws_id,
        auth=auth,
    )

    t0 = time.monotonic()
    total = 0

    for label, loader in stages:
        print(f"  {label:<28s}", end="", flush=True)
        try:
            count = await loader(ctx)
            total += count
            print(f"  {count:>4d} records")
        except Exception as exc:
            print(f"  FAILED: {exc}")
            raise

    elapsed = time.monotonic() - t0
    print(f"\n  Done — {total} records in {elapsed:.1f}s\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
