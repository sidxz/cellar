"""Replicate a full local Cellar environment — export real dev data, import it elsewhere.

Companion doc: ``REPLICATION.md`` (repo root). Code comes from git; this moves the data.

WHAT TRAVELS
    postgres.dump   every table (audit included), minus ``alembic_version``
    storage/        the WHOLE ``STORAGE_ROOT`` tree, minus the scratch prefixes below

WHAT DOES NOT, AND WHY
    Valkey      Nothing in the backend opens ``REDIS_URL``. ``ImportFileCache`` is
                ``InMemoryImportFileCache`` (in-process, infrastructure/cache/). Valkey
                is in the compose file for Infisical's benefit. There is no cache to
                warm and no state to carry — it is not "reconstructible", it is unused.

    Temporal    All eight workflows are job-shaped (CDD import, bulk registration,
                export, four SAR computes). Carrying history would either dangle
                against the target's fresh ``temporal-db`` or resume mid-flight and
                hammer CDD with the EXPORTER's credentials. Neither is something a dev
                bundle should do. Instead the import parks live job rows in a failed
                state (see ``JOB_TABLES``), so the UI shows re-runnable jobs rather
                than spinners that never resolve.

    Infisical   The target bootstraps its own (``scripts/bootstrap-infisical.sh``, run
                by ``make up``). Note ``external_api_keys`` stores only ``key_prefix``
                and metadata — real secrets live in Infisical — so the dump carries no
                live external credentials.

    Duar        Never copied, only re-checked. Duar is a shared hosted service here and
                Cellar registers no per-resource ACLs (grep: zero
                ``permissions.register_resource`` calls), so there is nothing to
                rebuild. Import proves Duar is reachable and prints a checklist.

                If a permissions write is ever added to a bare CLI like this one, it
                MUST ``await duar.fetch_whoami()`` first. ``register_resource`` posts
                ``service_name=permissions.service_name``, and whoami is what re-points
                that at the realm slug. Skip it and every row lands under the bare
                service name while the app reads under the realm slug — no error, just
                403s everywhere and empty result sets.

Postgres is reached through ``docker compose exec -T postgres`` so pg_dump/pg_restore
come version-matched from the RDKit cartridge image and the host needs nothing installed.

Usage (from backend/):
    uv run python scripts/replicate.py export [out.tar.gz] [--all-files]
    uv run python scripts/replicate.py import <bundle.tar.gz> [--truncate] [--force]
                                              [--skip-duar-check]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import cache
from pathlib import Path

from cellar.domain.chemical_registration.enums import (
    BulkRegistrationStatus,
    CddMoleculeImportStatus,
)
from cellar.domain.export.enums import ExportStatus
from cellar.domain.inventory.enums import CddPlateImportStatus
from cellar.domain.shared.async_job import AsyncJobStatus

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

BUNDLE_FORMAT = 1
MANIFEST = "manifest.json"
PG_DUMP = "postgres.dump"
STORAGE_DIR = "storage"

COMPOSE = ("docker", "compose", "-f", "docker-compose.infra.yml")


# ── Registries ───────────────────────────────────────────────────────────────
# Two lists in this file will drift as the app grows, and both fail silently when
# they do. They are table-driven and pinned by tests/unit/test_replicate_registry.py
# so the next omission fails in CI instead of on someone's replicated machine.


@dataclass(frozen=True)
class ScratchPrefix:
    """A top-level ``STORAGE_ROOT`` directory that must not travel in a bundle."""

    name: str
    why: str


# A DENY-list, deliberately never an allow-list. Export walks the whole storage root
# and skips only these, so a prefix added later ships by default instead of vanishing.
# (An allow-list is how a sibling project shipped zero dataset files for months while
# reporting success — the importer then restored rows pointing at keys that did not
# exist.) Every skip is recorded in the manifest and printed on stdout.
SCRATCH_PREFIXES: tuple[ScratchPrefix, ...] = (
    # infrastructure/temporal/activities/cdd_fetch.py:131 — StorageSettings().subdir("cdd-exports")
    ScratchPrefix("cdd-exports", "re-fetchable raw CDD vault dumps; 3.4 GB on the source host"),
    # infrastructure/temporal/activities/file_parsing.py:118 — subdir("bulk-imports")
    ScratchPrefix("bulk-imports", "staging for in-flight uploads; meaningless on another machine"),
)


@dataclass(frozen=True)
class JobTable:
    """A table whose rows are driven by a Temporal workflow that does not travel.

    ``live`` are the statuses meaning "a workflow is still driving this row". After a
    restore no workflow exists, so those rows are parked in ``failed``. Both are
    per-table because the vocabularies genuinely differ — ``bulk_registrations`` has no
    'failed' member at all, so parking it there would write a status its own domain
    enum does not define. ``status_enum`` is what lets the test prove that never happens.

    ``workflow`` is the stem of the module under ``infrastructure/temporal/workflows/``
    that drives this table. It exists so the test can assert coverage by set equality
    against the real directory: add a ninth workflow and the test fails until someone
    decides whether it needs sweeping.
    """

    table: str
    workflow: str
    live: tuple[str, ...]
    failed: str
    status_enum: type[StrEnum]
    error_col: str | None = "error_message"


_ASYNC_JOB_LIVE = (AsyncJobStatus.PENDING, AsyncJobStatus.RUNNING)

JOB_TABLES: tuple[JobTable, ...] = (
    # The four AsyncJob subclasses — domain/sar_analysis/*.py
    JobTable("scaffold_tree_jobs", "scaffold_tree", _ASYNC_JOB_LIVE, "failed", AsyncJobStatus),
    JobTable("umap_jobs", "umap_cluster", _ASYNC_JOB_LIVE, "failed", AsyncJobStatus),
    JobTable(
        "rgroup_decomposition_runs",
        "rgroup_decomposition",
        _ASYNC_JOB_LIVE,
        "failed",
        AsyncJobStatus,
    ),
    JobTable(
        "sar_activity_projections",
        "sar_activity_projection",
        _ASYNC_JOB_LIVE,
        "failed",
        AsyncJobStatus,
    ),
    # cancel_requested is mid-flight too: the workflow that would honour it is gone.
    JobTable(
        "export_jobs",
        "export",
        ("pending", "running", "cancel_requested"),
        "failed",
        ExportStatus,
    ),
    JobTable(
        "cdd_molecule_imports",
        "cdd_vault_import",
        ("pending", "discovering", "processing"),
        "failed",
        CddMoleculeImportStatus,
        error_col=None,
    ),
    JobTable(
        "cdd_plate_imports",
        "cdd_plate_import",
        ("pending", "discovering", "processing"),
        "failed",
        CddPlateImportStatus,
        error_col=None,
    ),
    # BulkRegistrationStatus has NO 'failed' member — completed_with_errors is the only
    # terminal state it defines for a run that stopped partway.
    JobTable(
        "bulk_registrations",
        "bulk_registration",
        ("pending", "processing"),
        "completed_with_errors",
        BulkRegistrationStatus,
        error_col=None,
    ),
)

WORKFLOWS_DIR = BACKEND_DIR / "src" / "cellar" / "infrastructure" / "temporal" / "workflows"

SWEEP_REASON = "Workflow did not travel with the replication bundle — re-run this job."


# ── Environment ──────────────────────────────────────────────────────────────


def _load_root_dotenv() -> None:
    """DATABASE_URL lives in the repo-root .env; pydantic-settings only looks in backend/."""
    env = REPO_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


@cache
def _db() -> tuple[str, str]:
    """(user, database) parsed from DATABASE_URL. Host/port are the container's own."""
    from sqlalchemy.engine import make_url

    from cellar.infrastructure.persistence.settings import DatabaseSettings

    url = make_url(DatabaseSettings().database_url)
    return str(url.username), str(url.database)


def _storage_root() -> Path:
    """STORAGE_ROOT, resolved against backend/ when relative (dev default: ./data/storage)."""
    from cellar.infrastructure.storage.fsspec_client import StorageSettings

    root = StorageSettings().root_path
    return root if root.is_absolute() else (BACKEND_DIR / root).resolve()


# ── Postgres, through the container ──────────────────────────────────────────


def _pg(args: list[str], *, stdin=None, stdout=None) -> None:
    user, db = _db()
    subprocess.run(
        [*COMPOSE, "exec", "-T", "postgres", *args, "-U", user, "-d", db],
        cwd=REPO_ROOT,
        check=True,
        stdin=stdin,
        stdout=stdout,
    )


def _psql(sql: str) -> str:
    user, db = _db()
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "postgres", "psql", "-U", user, "-d", db, "-tA", "-c", sql],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # check=True would raise with the error buried in a captured stream nobody prints.
        raise SystemExit(f"psql failed: {result.stderr.strip()}\n  query: {sql.strip()}")
    return result.stdout.strip()


def _require_postgres() -> None:
    try:
        _psql("SELECT 1")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(
            f"postgres is not reachable via docker compose — run `make up` ({exc})"
        ) from None


# Exact, not estimated. pg_stat_user_tables.n_live_tup is a planner estimate that is
# zero until autovacuum analyzes: measured on a live dev box, `molecules` held 61,256
# rows and reported n_live_tup = 0. An estimate-based check calls that database empty
# and charges into a --data-only restore, which then dies on PK collisions mid-restore.
# The LIMIT 1 subquery keeps this cheap — it stops at the first row of each table.
_NON_EMPTY_SQL = """
SELECT relname FROM (
  SELECT c.relname,
         (xpath('/row/c/text()', query_to_xml(
             format('SELECT count(*) AS c FROM (SELECT 1 FROM public.%I LIMIT 1) t', c.relname),
             false, true, '')))[1]::text::int AS n
  FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
  WHERE ns.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'
) s WHERE n > 0 ORDER BY relname
"""

_ALL_TABLES_SQL = (
    "SELECT string_agg(format('%I', c.relname), ', ') FROM pg_class c "
    "JOIN pg_namespace ns ON ns.oid = c.relnamespace "
    "WHERE ns.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'"
)


def _workspaces() -> list[str]:
    """Every workspace UUID with data, discovered rather than hardcoded.

    The importer compares this against the workspace their own Duar login resolves to,
    so it must not quietly go stale when tables are added. Naming a fixed set of tables
    here was the first version and it broke immediately — workspace_settings is keyed by
    ``id``, not ``workspace_id``.
    """
    tables = [
        t
        for t in _psql(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'workspace_id' ORDER BY 1"
        ).splitlines()
        if t
    ]
    if not tables:
        return []
    union = " UNION ".join(
        f"SELECT DISTINCT workspace_id::text AS w FROM public.{t}" for t in tables
    )
    found = _psql(f"SELECT w FROM ({union}) s WHERE w IS NOT NULL ORDER BY 1")
    return [w for w in found.splitlines() if w]


# ── Storage ──────────────────────────────────────────────────────────────────


def _is_junk(path: Path) -> bool:
    """Dotfiles are never storage keys (those are ``{uuid}_{filename}``).

    Catches .DS_Store and any stale ``.write-probe-<pid>`` left by ensure_storage_root.
    """
    return path.name.startswith(".")


def _copy_storage(dest: Path, *, all_files: bool) -> tuple[int, int, dict[str, str]]:
    """Copy the whole storage tree into ``dest``, minus scratch prefixes. Returns stats."""
    root = _storage_root()
    skipped = {} if all_files else {p.name: p.why for p in SCRATCH_PREFIXES}
    files = total_bytes = 0
    if not root.exists():
        return 0, 0, skipped
    for src in root.rglob("*"):
        if not src.is_file() or _is_junk(src):
            continue
        rel = src.relative_to(root)
        if rel.parts[0] in skipped:
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        files += 1
        total_bytes += src.stat().st_size
    return files, total_bytes, skipped


def _restore_storage(src_root: Path) -> int:
    """Copy bundle files into STORAGE_ROOT, preserving keys. Existing files are left alone."""
    if not src_root.exists():
        return 0
    dest_root = _storage_root()
    copied = 0
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        dest = dest_root / src.relative_to(src_root)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n} B"


# ── Duar ─────────────────────────────────────────────────────────────────────


async def _check_duar() -> str:
    """Prove Duar is reachable and print the effective scope. Writes nothing."""
    from cellar.infrastructure.duar.auth import get_duar

    duar = get_duar()
    # Realm-scope discovery normally happens in the app lifespan; a bare CLI must do it
    # itself. Cellar writes no ACLs today, so this is a credential probe — but it is
    # also the ordering any future permissions write in this file has to inherit.
    whoami = await duar.fetch_whoami()
    scope = duar.effective_scope
    if whoami is None:
        print(f"! Duar /realm/whoami did not answer — effective scope is bare {scope!r}.")
        print("! Cellar writes no per-resource ACLs, so nothing is mis-scoped today. But if")
        print("! your app boots as a realm member, DUAR_URL/DUAR_SERVICE_KEY are wrong here")
        print("! and the app will 403 after import. Fix them before you trust this replica.")
    else:
        print(f"  Duar reachable — effective scope {scope!r}")
    return scope


# ── Commands ─────────────────────────────────────────────────────────────────


def export_cmd(out: Path, *, all_files: bool) -> int:
    _require_postgres()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("  dumping postgres ...", flush=True)
        with (tmp / PG_DUMP).open("wb") as fh:
            _pg(["pg_dump", "-Fc", "--exclude-table=alembic_version"], stdout=fh)
        dump_bytes = (tmp / PG_DUMP).stat().st_size

        print("  copying storage ...", flush=True)
        files, total_bytes, skipped = _copy_storage(tmp / STORAGE_DIR, all_files=all_files)

        head = _psql("SELECT version_num FROM alembic_version")
        workspaces = _workspaces()
        manifest = {
            "format": BUNDLE_FORMAT,
            "exported_at": datetime.now(UTC).isoformat(),
            "alembic_head": head,
            "workspaces": workspaces,
            "postgres_bytes": dump_bytes,
            "storage": {
                "files": files,
                "bytes": total_bytes,
                "skipped_prefixes": skipped,
            },
            "excluded": ["valkey (unused by the app)", "temporal", "infisical", "duar"],
        }
        (tmp / MANIFEST).write_text(json.dumps(manifest, indent=2))

        print(f"  writing {out} ...", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out, "w:gz") as tar:
            for path in sorted(tmp.rglob("*")):
                tar.add(path, arcname=str(path.relative_to(tmp)), recursive=False)

    print(f"\n  bundle   {out}  ({_human(out.stat().st_size)})")
    print(f"  postgres {_human(dump_bytes)}, alembic head {head}")
    print(f"  storage  {files} files, {_human(total_bytes)}")
    for name, why in skipped.items():
        print(f"  skipped  {name}/ — {why}")
    if skipped:
        print("           (pass --all-files to include them)")
    print(f"  workspaces {', '.join(workspaces) or '(none)'}")
    return 0


def import_cmd(bundle: Path, *, force: bool, truncate: bool, skip_duar: bool) -> int:
    _require_postgres()
    if not bundle.exists():
        raise SystemExit(f"no such bundle: {bundle}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with tarfile.open(bundle) as tar:
            tar.extractall(tmp, filter="data")

        manifest_path = tmp / MANIFEST
        if not manifest_path.exists():
            raise SystemExit(f"{bundle} has no {MANIFEST} — not a Cellar bundle")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("format") != BUNDLE_FORMAT:
            raise SystemExit(
                f"bundle format {manifest.get('format')} != {BUNDLE_FORMAT} — "
                "check out the commit that wrote it"
            )

        # ── Preflight: every check runs before anything is written ────────────
        target_head = _psql("SELECT version_num FROM alembic_version")
        if not target_head:
            raise SystemExit("target has no migrations — run `make up` first")

        if target_head != manifest["alembic_head"] and not force:
            raise SystemExit(
                f"alembic mismatch: bundle={manifest['alembic_head']} target={target_head} — "
                "check out the matching commit and `make migrate`, or pass --force"
            )

        populated = [t for t in _psql(_NON_EMPTY_SQL).splitlines() if t]
        if populated and not truncate:
            shown = ", ".join(populated[:6]) + (" ..." if len(populated) > 6 else "")
            raise SystemExit(
                f"target postgres is not empty ({len(populated)} tables: {shown}) — "
                "pass --truncate to replace their contents, or start from `make nuke && make up`"
            )

        if skip_duar:
            print("  skipped Duar check (--skip-duar-check)")
        else:
            try:
                asyncio.run(_check_duar())
            except Exception as exc:
                raise SystemExit(
                    f"Duar check failed ({exc}) — fix DUAR_URL / DUAR_SERVICE_KEY in .env, "
                    "or pass --skip-duar-check. Importing against a broken Duar gives you an "
                    "app that loads and shows nothing."
                ) from None

        # ── Write ────────────────────────────────────────────────────────────
        if populated:
            print(f"  truncating {len(populated)} tables ...", flush=True)
            tables = _psql(_ALL_TABLES_SQL)
            if tables:
                _psql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")

        print("  restoring postgres ...", flush=True)
        with (tmp / PG_DUMP).open("rb") as fh:
            _pg(
                ["pg_restore", "--data-only", "--disable-triggers", "--single-transaction"],
                stdin=fh,
            )

        print("  restoring storage ...", flush=True)
        copied = _restore_storage(tmp / STORAGE_DIR)

    swept = _sweep_jobs()

    print(f"\n  restored postgres + {copied} storage files")
    if swept:
        print("  parked abandoned jobs (their workflows did not travel):")
        for line in swept:
            print(f"    {line}")
    _print_checklist(manifest)
    return 0


def _sweep_jobs() -> list[str]:
    """Park rows whose driving Temporal workflow does not exist on this machine."""
    swept = []
    for job in JOB_TABLES:
        assignments = [f"status = '{job.failed}'"]
        if job.error_col:
            assignments.append(f"{job.error_col} = '{SWEEP_REASON}'")
        live = ", ".join(f"'{s}'" for s in job.live)
        count = _psql(
            f"WITH u AS (UPDATE {job.table} SET {', '.join(assignments)} "
            f"WHERE status IN ({live}) RETURNING 1) SELECT count(*) FROM u"
        )
        if count and int(count) > 0:
            swept.append(f"{job.table}: {count} -> {job.failed}")
    return swept


def _print_checklist(manifest: dict) -> None:
    workspaces = manifest.get("workspaces") or []
    skipped = manifest.get("storage", {}).get("skipped_prefixes", {})
    print("\n  Next steps — none of this is automatable from here:")
    print("  1. Duar workspace. Every row is scoped by a Duar-owned workspace UUID, and")
    print("     the app filters on YOUR workspace. This bundle carries:")
    for ws in workspaces:
        print(f"       {ws}")
    print("     If the workspace your login resolves to is not in that list, the app will")
    print("     come up fully functional and completely empty. That is the expected")
    print("     symptom, not a bug — get added to that workspace in the Duar admin panel.")
    print("  2. Role -> action grants stay a Duar admin-panel task. The cellar:* action")
    print("     catalog self-registers when the backend boots (SERVICE_ACTIONS in")
    print("     infrastructure/duar/auth.py); the grants onto roles do not.")
    print("  3. Infisical: `make up` bootstraps your own. External API key SECRETS are not")
    print("     in this bundle (external_api_keys holds only key_prefix + metadata) — re-add")
    print("     any CDD/ChEMBL keys you need through the admin UI.")
    if skipped:
        print("  4. Storage prefixes left out of this bundle, re-fetch if you need them:")
        for name, why in skipped.items():
            print(f"       {name}/ — {why}")


def main(argv: list[str] | None = None) -> int:
    _load_root_dotenv()
    parser = argparse.ArgumentParser(
        prog="replicate", description="Export/import a full local Cellar dataset."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    stamp = datetime.now(UTC).date().isoformat()
    exp = sub.add_parser("export", help="write a bundle from this machine")
    exp.add_argument("out", nargs="?", type=Path, default=Path(f"cellar-bundle-{stamp}.tar.gz"))
    exp.add_argument(
        "--all-files",
        action="store_true",
        help="include scratch storage prefixes (cdd-exports, bulk-imports) — usually GBs",
    )

    imp = sub.add_parser("import", help="load a bundle into this machine")
    imp.add_argument("bundle", type=Path)
    imp.add_argument("--truncate", action="store_true", help="empty the target's tables first")
    imp.add_argument(
        "--force", action="store_true", help="proceed despite an alembic head mismatch"
    )
    imp.add_argument("--skip-duar-check", action="store_true", help="do not probe Duar")

    args = parser.parse_args(argv)
    if args.cmd == "export":
        return export_cmd(args.out, all_files=args.all_files)
    return import_cmd(
        args.bundle,
        force=args.force,
        truncate=args.truncate,
        skip_duar=args.skip_duar_check,
    )


if __name__ == "__main__":
    sys.exit(main())
