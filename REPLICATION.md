# Replicating a Cellar environment

Code comes from git. Data comes from a bundle. This is how another developer gets a
working local Cellar with your actual data in it.

```bash
# on the machine that HAS the data
cd backend && uv run python scripts/replicate.py export cellar-bundle.tar.gz

# on the machine that WANTS it
git clone git@github.com:sidxz/cellar.git && cd cellar
cp .env.example .env          # fill in DUAR_SERVICE_KEY etc.
make up                       # postgres + valkey + temporal + infisical, migrations, secrets
cd backend && uv run python scripts/replicate.py import ../cellar-bundle.tar.gz
make dev
```

Or via make: `make export-data`, `make import-data BUNDLE=path/to/bundle.tar.gz`.

## What's in the bundle

| | |
|---|---|
| `postgres.dump` | every table, `pg_dump -Fc`, minus `alembic_version` |
| `storage/` | the whole `STORAGE_ROOT` tree minus scratch prefixes |
| `manifest.json` | alembic head, workspace UUIDs, counts, what was skipped and why |

A representative bundle is **~58 MB**: 56 MB of Postgres (61k molecules, RDKit
fingerprints and all) and 3.3 MB of attachments.

Postgres goes in and out through `docker compose exec -T postgres`, so `pg_dump` and
`pg_restore` come version-matched from the RDKit cartridge image. Nothing needs to be
installed on the host.

## What's deliberately left out

**`cdd-exports/` and `bulk-imports/`** — 3.4 GB of re-fetchable CDD vault dumps and
upload staging, against 3.3 MB of real attachments. `--all-files` includes them.

These are a **deny-list, not an allow-list**: export walks the entire storage root and
skips only the named prefixes, so a prefix added later ships automatically instead of
vanishing. Every skip is printed and recorded in the manifest, so "0 files" can never
pass for success. (A sibling project allow-listed one prefix and silently shipped zero
dataset files for months; importers restored rows pointing at keys that did not exist.)

**Valkey** — carries nothing. No backend code opens `REDIS_URL`; `ImportFileCache` is
`InMemoryImportFileCache`, in-process. Valkey is in the compose file for Infisical.
There is no cache to warm here, and nothing to reconstruct.

**Temporal** — excluded on purpose. All eight workflows are job-shaped (CDD import, bulk
registration, export, four SAR computes). Replayed history would either dangle against
the target's fresh `temporal-db` or resume mid-flight and hammer CDD with the
*exporter's* API credentials. Instead, import parks live job rows in a terminal state so
the UI shows re-runnable jobs instead of spinners that never resolve. That table lives in
`JOB_TABLES` in `scripts/replicate.py` and is pinned by
`tests/unit/test_replicate_registry.py`.

**Infisical** — `make up` bootstraps your own. External API key *secrets* are not in the
bundle: `external_api_keys` stores only `key_prefix` and metadata, so the dump carries no
live external credentials. Re-add CDD/ChEMBL keys through the admin UI.

**Duar** — never copied, only re-checked. See below.

## Duar, and the empty-app failure

Every row is scoped by a workspace UUID that **Duar owns**, not Cellar
(`RequestAuth.workspace_id`, `interface/dependencies/_core.py:186`). If the workspace your
login resolves to isn't one the bundle carries, the app comes up fully functional and
completely empty, with no error anywhere. That is the single most likely way this goes
wrong. Import prints the bundle's workspace UUIDs; get yourself added to one in the Duar
admin panel.

Import probes Duar **before** it writes anything, and prints the effective scope:

```
Duar reachable — effective scope 'daikon-siblings'
```

Note that the scope is the *realm slug*, not the bare `cellar` service name. Cellar
registers no per-resource ACLs today (grep: zero `permissions.register_resource` calls),
so nothing can currently be mis-scoped — but if you ever add a permissions write to a
bare CLI like this one, it **must** `await duar.fetch_whoami()` first. `register_resource`
posts `service_name=permissions.service_name`, and whoami is what re-points that at the
realm slug. Skip it and every row lands under the bare service name while the app reads
under the realm slug: no error, just 403s and empty result sets.

Role → action grants stay a Duar admin-panel task. The `cellar:*` action catalog
self-registers when the backend boots (`SERVICE_ACTIONS` in `infrastructure/duar/auth.py`).

## Import refuses, and when to override

| Refusal | Override |
|---|---|
| target has no migrations | run `make up` first — no override |
| alembic head ≠ bundle's | `--force`, but check out the matching commit and `make migrate` instead |
| target tables not empty | `--truncate` to replace their contents |
| Duar unreachable / bad key | `--skip-duar-check` |
| bundle format mismatch | none — check out the commit that wrote it |

The emptiness check counts rows **exactly** (a `LIMIT 1` subquery per table), and this is
not a detail. `pg_stat_user_tables.n_live_tup` is a planner estimate that reads zero until
autovacuum analyzes: on a live dev box here, `molecules` held 61,256 rows and reported
`n_live_tup = 0`. An estimate-based check calls that database empty, charges into a
`--data-only` restore, and dies on primary-key collisions partway through. The exact check
found all 77 populated tables.

Restore is `pg_restore --data-only --disable-triggers --single-transaction`: schema comes
from `alembic upgrade head`, `--disable-triggers` makes table order irrelevant, and the
whole thing is atomic — a failure leaves the target as it was.

## Keeping the registries honest

Two lists in `scripts/replicate.py` drift silently as the app grows, so
`tests/unit/test_replicate_registry.py` pins both:

- every `JOB_TABLES` entry names a real table with real `status`/error columns;
- every status it writes exists in that table's domain enum — this is what caught
  `bulk_registrations`, whose `BulkRegistrationStatus` has **no** `failed` member, so the
  obvious uniform sweep would have written a status nothing in the app can read;
- every workflow module under `infrastructure/temporal/workflows/` has a sweep entry,
  asserted by set equality against the real directory, so a ninth workflow fails the test
  until someone decides whether it needs sweeping.

Add a workflow, a job table, or a storage prefix, and update the registry — not the test.
