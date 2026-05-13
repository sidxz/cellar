# Screen-Campaign B-gap UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land report-grade screener UX — multi-run import with hit-criteria preview (B6) + grid polish (B1 thumbnails, B5 chip filter, B7 ND-qualifier gating, B8 override reason) + Preview-as-published bonus — DRY against existing cellar machinery.

**Architecture:** New `PreviewRunImport` + `AddFromRuns` use cases replace single-run path; migration 028 extends `campaign_measurement` with snapshot + audit columns; FE wires a 2-step `<AddFromRunsDialog>` + new chip-filter bar + structure thumbnails + override-modal polish. All hit-call math runs through the existing `_compute_hit_call` pure function and channel resolver; all DAIKON output flows through the existing `_serialize_*` helpers.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async (asyncpg) / Alembic / dry-python returns / pytest; Next.js 16 / React 19 / TypeScript / AG Grid Community / TanStack Query / orval-generated client.

**Spec:** `docs/superpowers/specs/2026-05-11-screen-campaign-b-gaps-design.md` (authoritative; this plan sequences it).

---

## File-structure map

**Backend new:**
- `backend/alembic/versions/028_*.py`
- `backend/src/cellar/application/research_organization/preview_run_import.py`
- `backend/src/cellar/application/research_organization/add_results_from_runs.py`
- `backend/tests/unit/application/research_organization/test_preview_run_import.py`
- `backend/tests/unit/application/research_organization/test_add_results_from_runs.py`

**Backend modified:**
- `backend/src/cellar/domain/research_organization/campaign_measurement.py` (relax `__post_init__`; add 6 new fields)
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/*` ORM mapping (new columns)
- `backend/src/cellar/application/research_organization/override_result_cell.py` (`reason: str | None`)
- `backend/src/cellar/application/research_organization/get_published_campaign.py` (extend `_serialize_measurement`)
- `backend/src/cellar/interface/routes/campaigns.py` (new routes, remove deprecated single-run route)
- `backend/src/cellar/interface/dependencies.py` (DI for new use cases)

**Backend deleted:**
- `backend/src/cellar/application/research_organization/add_results_from_run.py`
- `backend/tests/unit/application/research_organization/test_add_results_from_run*.py`

**FE new:**
- `frontend/src/shared/components/molecule-thumbnail.tsx`
- `frontend/src/features/screen-campaign/components/campaign-filter-bar.tsx`
- `frontend/src/features/screen-campaign/components/add-from-runs-dialog.tsx`
- `frontend/src/features/screen-campaign/components/preview-as-published-dialog.tsx`

**FE modified:**
- `frontend/src/features/screen-campaign/components/results-grid.tsx` (B1 thumb + B7/B8 override modal)
- `frontend/src/features/screen-campaign/components/decision-panel.tsx` (B1 thumb in header)
- `frontend/src/features/screen-campaign/components/campaign-builder.tsx` (B5 chip bar + Preview-as-published button)
- `frontend/src/features/screen-campaign/components/compound-list-pane.tsx` (wire `<AddFromRunsDialog>` into dropdown)
- `frontend/src/features/screen-campaign/lib/hooks.ts` (new hooks)
- `frontend/src/shared/lib/api/` (orval regen)

---

## Task sequencing

Backend before FE; within backend, schema → domain → app → API → contract. Within FE, types → primitives → polish → big dialog → bonus. Each task is a clean commit.

---

### Task 1 — Migration 028: `campaign_measurement` extensions

**Files:**
- Create: `backend/alembic/versions/028_campaign_measurement_extensions.py`
- Modify: ORM model — locate via `rg -l "campaign_measurement" backend/src/cellar/infrastructure/persistence/`

- [ ] **Step 1.1: Locate the ORM model file** — `rg "class.*Campaign.*Measurement.*Model" backend/src/cellar/infrastructure/persistence/`. Capture the exact filename.

- [ ] **Step 1.2: Write the migration.** Find the latest revision via `ls backend/alembic/versions/ | sort | tail -1` and use its head as `down_revision`. Migration body:

```python
"""028 campaign_measurement extensions (B6/B8 report-grade snapshots)

Revision ID: 028_campaign_measurement_extensions
Revises: <PREVIOUS_HEAD>
Create Date: 2026-05-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "028_campaign_measurement_extensions"
down_revision = "<PREVIOUS_HEAD>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaign_measurement", sa.Column("override_reason", sa.Text(), nullable=True))
    op.add_column("campaign_measurement", sa.Column("test_concentration_value", sa.Float(), nullable=True))
    op.add_column("campaign_measurement", sa.Column("test_concentration_unit", sa.String(length=32), nullable=True))
    op.add_column("campaign_measurement", sa.Column("replicate_count", sa.Integer(), nullable=True))
    op.add_column("campaign_measurement", sa.Column("qc_pass", sa.Boolean(), nullable=True))
    op.add_column(
        "campaign_measurement",
        sa.Column("contributing_run_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_measurement", "contributing_run_ids")
    op.drop_column("campaign_measurement", "qc_pass")
    op.drop_column("campaign_measurement", "replicate_count")
    op.drop_column("campaign_measurement", "test_concentration_unit")
    op.drop_column("campaign_measurement", "test_concentration_value")
    op.drop_column("campaign_measurement", "override_reason")
```

- [ ] **Step 1.3: Add columns to the ORM model** — mirror the migration with `mapped_column(...)` declarations.

- [ ] **Step 1.4: Verify migration applies** — `cd backend && uv run alembic upgrade head`. Expected: "Running upgrade ... -> 028 ...".

- [ ] **Step 1.5: Commit.**

```
feat(campaign): migration 028 — campaign_measurement audit + snapshot columns

Adds override_reason, test_concentration_{value,unit}, replicate_count,
qc_pass, contributing_run_ids — all nullable. Backwards-compat for
existing closed campaigns.
```

---

### Task 2 — Domain: extend `CampaignMeasurement` + relax `__post_init__` (B7 + B8)

**Files:**
- Modify: `backend/src/cellar/domain/research_organization/campaign_measurement.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_measurement.py`

- [ ] **Step 2.1: Read the existing measurement file** — note current `__post_init__` and field list.

- [ ] **Step 2.2: Add the 6 new fields** as keyword-only with `default=None`. Update any `to_dict`/`from_dict` helpers to round-trip them.

- [ ] **Step 2.3: Relax `__post_init__`** — replace the empty-unit check with:

```python
def __post_init__(self) -> None:
    if self.value_qualifier in (ValueQualifier.ND, ValueQualifier.EXCLUDED):
        # ND/excluded are placeholders — value must be None and unit may be empty
        object.__setattr__(self, "value", None)
        return
    if not self.unit:
        raise ValueError("CampaignMeasurement.unit must be non-empty (use qualifier=nd for missing data)")
```

(Use `object.__setattr__` because the dataclass is frozen.)

- [ ] **Step 2.4: Add tests.** Cases:
  - `qualifier=nd, value=42, unit="nM"` → value forced to None.
  - `qualifier=nd, unit=""` → accepted (no error).
  - `qualifier=excluded, value=10, unit=""` → accepted; value forced to None.
  - `qualifier=eq, unit=""` → raises ValueError.
  - Round-trip of new fields via `to_dict`/`from_dict` (skip if absent).

- [ ] **Step 2.5: Run** `cd backend && uv run pytest tests/unit/domain/research_organization/test_campaign_measurement.py -v`.

- [ ] **Step 2.6: Run the full domain suite** — `uv run pytest tests/unit/domain/ -q`. Expected: no regressions.

- [ ] **Step 2.7: Commit.**

```
feat(campaign): relax CampaignMeasurement unit check for nd/excluded (B7) + add B8/B6 snapshot fields
```

---

### Task 3 — Extend `OverrideResultCellCommand` with `reason` (B8)

**Files:**
- Modify: `backend/src/cellar/application/research_organization/override_result_cell.py`
- Test: `backend/tests/unit/application/research_organization/test_override_result_cell.py` (extend existing)

- [ ] **Step 3.1: Read existing UC + test** to understand the command shape and persistence path.

- [ ] **Step 3.2: Add `reason: str | None = None` to the command dataclass** and propagate to the measurement on override — set `override_reason` on the new/updated measurement.

- [ ] **Step 3.3: Add test cases:**
  - Override with `reason="QC fail on plate 3"` → measurement has `override_reason == "QC fail on plate 3"`.
  - Override with `reason=None` → measurement has `override_reason is None`.

- [ ] **Step 3.4: Run** `uv run pytest tests/unit/application/research_organization/test_override_result_cell.py -v`. Green.

- [ ] **Step 3.5: Commit.**

```
feat(campaign): override_reason field on OverrideResultCell (B8)
```

---

### Task 4 — `PreviewRunImport` use case + tests (B6 core)

**Files:**
- Create: `backend/src/cellar/application/research_organization/preview_run_import.py`
- Create: `backend/tests/unit/application/research_organization/test_preview_run_import.py`

- [ ] **Step 4.1: Inspect `channel_resolution.py`** for the per-channel resolver. The plan extracts a `resolve_for_runs(...)` helper if not already present — see §4.2 below.

- [ ] **Step 4.2: Refactor: extract `resolve_for_runs(workspace_id, run_ids, protocol_id, readout_definition_id, selection_rule)`** as a public helper in `channel_resolution.py`. It must return per-molecule resolved cells with these fields: `molecule_id, value, value_qualifier, unit, source_run_id, source_run_name, source_run_date, contributing_run_ids, replicate_count, test_concentration_value, test_concentration_unit, qc_pass`. The existing per-channel resolver becomes a thin wrapper around this helper — no behavior change for current callers. Run the full `channel_resolution` test suite after refactor to prove parity.

- [ ] **Step 4.3: Skeleton for PreviewRunImport** — follow `get_published_campaign.py` pattern (read-only, `require_editor`, single UoW).

```python
from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import Any, Literal
from returns.result import Failure, Result, Success
from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.research_organization.channel_resolution import (
    _compute_hit_call, resolve_for_runs,
)
from cellar.domain.research_organization.enums import SelectionRule
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.hit_criterion import HitCriterion
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.shared.errors import (
    AuthorizationError, DomainError, NotFoundError, ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class ChannelImportConfig:
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    label: str
    selection_rule: SelectionRule
    hit_threshold: HitCriterion | None
    use_for_filter: bool


@dataclass(frozen=True, kw_only=True)
class PreviewRunImportQuery(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfig]
    filter_mode: Literal["any", "all"] = "all"


class PreviewRunImport:
    def __init__(
        self, *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        run_repo: RunRepository,
        molecule_repo: MoleculeRepository,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._run_repo = run_repo
        self._molecule_repo = molecule_repo

    async def __call__(
        self, input: PreviewRunImportQuery, auth: AuthContext | None = None,
    ) -> Result[dict[str, Any], DomainError]:
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)
        async with self._uow:
            return await self._execute(input)

    async def _execute(self, q: PreviewRunImportQuery) -> Result[dict[str, Any], DomainError]:
        campaign = await self._campaign_repo.find_by_id_in_workspace(q.workspace_id, q.campaign_id)
        if campaign is None:
            return Failure(NotFoundError("Campaign", str(q.campaign_id)))

        runs = await self._run_repo.find_by_ids(q.workspace_id, q.run_ids)
        if not runs:
            return Failure(ValidationError("No runs found"))

        # Build channel meta (new vs reused)
        existing_by_key = {(c.protocol_id, c.readout_definition_id): c for c in campaign.channels}
        channels_meta = [
            {
                "channel_key": f"{cfg.protocol_id}/{cfg.readout_definition_id}",
                "label": cfg.label,
                "source": "reused" if (cfg.protocol_id, cfg.readout_definition_id) in existing_by_key else "new",
                "reuse_of_channel_id": (
                    str(existing_by_key[(cfg.protocol_id, cfg.readout_definition_id)].id)
                    if (cfg.protocol_id, cfg.readout_definition_id) in existing_by_key else None
                ),
                "selection_rule": cfg.selection_rule.value,
                "hit_threshold": cfg.hit_threshold.to_dict() if cfg.hit_threshold else None,
                "use_for_filter": cfg.use_for_filter,
            }
            for cfg in q.channel_configs
        ]

        # Resolve cells per channel
        rows_by_molecule: dict[uuid.UUID, dict] = {}
        active_keys: set[str] = set()
        for cfg in q.channel_configs:
            key = f"{cfg.protocol_id}/{cfg.readout_definition_id}"
            if cfg.use_for_filter:
                active_keys.add(key)
            resolved = await resolve_for_runs(
                workspace_id=q.workspace_id, run_ids=q.run_ids,
                protocol_id=cfg.protocol_id,
                readout_definition_id=cfg.readout_definition_id,
                selection_rule=cfg.selection_rule,
            )
            for r in resolved:
                hit_call = _compute_hit_call(r.value, cfg.hit_threshold) if cfg.hit_threshold else None
                row = rows_by_molecule.setdefault(r.molecule_id, {"cells": []})
                row["cells"].append({
                    "channel_key": key,
                    "value": r.value,
                    "value_qualifier": r.value_qualifier.value,
                    "unit": r.unit,
                    "test_concentration_value": getattr(r, "test_concentration_value", None),
                    "test_concentration_unit": getattr(r, "test_concentration_unit", None),
                    "replicate_count": getattr(r, "replicate_count", None),
                    "qc_pass": getattr(r, "qc_pass", None),
                    "hit_call": hit_call.value if hit_call else None,
                    "source_run_id": str(r.source_run_id) if r.source_run_id else None,
                    "source_run_name": getattr(r, "source_run_name", None),
                    "source_run_date": r.source_run_date.isoformat() if getattr(r, "source_run_date", None) else None,
                    "contributing_run_ids": [str(rid) for rid in getattr(r, "contributing_run_ids", []) or []],
                })

        # is_hit per molecule
        in_campaign = {r.molecule_id for r in campaign.results}
        for mid, row in rows_by_molecule.items():
            active_cells = [c for c in row["cells"] if c["channel_key"] in active_keys]
            if not active_cells:
                row["is_hit"] = False
            else:
                hits = [c["hit_call"] == "hit" for c in active_cells]
                row["is_hit"] = any(hits) if q.filter_mode == "any" else all(hits)
            row["already_in_campaign"] = mid in in_campaign

        # Hydrate molecules
        mol_ids = list(rows_by_molecule.keys())
        molecules = await self._molecule_repo.find_by_ids(q.workspace_id, mol_ids)
        mol_lookup = {m.id: m for m in molecules}

        rows_response = []
        hits_count = non_hits_count = already_count = 0
        for mid, row in rows_by_molecule.items():
            mol = mol_lookup.get(mid)
            if mol is None:
                continue
            if row["already_in_campaign"]:
                already_count += 1
            if row["is_hit"]:
                hits_count += 1
            else:
                non_hits_count += 1
            rows_response.append({
                "molecule": {
                    "id": str(mol.id),
                    "registration_number": mol.registration_number.value,
                    "name": mol.name,
                    "smiles": mol.structure.smiles if mol.structure else None,
                },
                "is_hit": row["is_hit"],
                "already_in_campaign": row["already_in_campaign"],
                "cells": row["cells"],
            })

        return Success({
            "summary": {
                "runs": len(runs),
                "channels_new": sum(1 for c in channels_meta if c["source"] == "new"),
                "channels_reused": sum(1 for c in channels_meta if c["source"] == "reused"),
                "molecules_total": len(rows_response),
                "hits": hits_count,
                "non_hits": non_hits_count,
                "molecules_already_in_campaign": already_count,
            },
            "channels": channels_meta,
            "rows": rows_response,
        })
```

- [ ] **Step 4.4: Write tests** in `test_preview_run_import.py` using `_helpers.py` fakes. Cases:

```python
# Case 1: empty run_ids → ValidationError
# Case 2: single run, single channel, no hit_threshold → all hit_call=None, is_hit=False (no active filter)
# Case 3: single run, single channel, threshold IC50 < 1000nM → some hits, some misses
# Case 4: campaign has matching channel → channel "reuse" detected
# Case 5: AND mode with 2 channels — molecule must hit in both
# Case 6: ANY mode with 2 channels — hit in any qualifies
# Case 7: molecule already in campaign → already_in_campaign=True
# Case 8: concentration + replicate_count + qc_pass surface in cell
# Case 9: missing data for some molecules → qualifier=nd
```

- [ ] **Step 4.5: Run** `uv run pytest tests/unit/application/research_organization/test_preview_run_import.py -v`. Green.

- [ ] **Step 4.6: Commit.**

```
feat(campaign): PreviewRunImport use case (B6 — read-only multi-run preview)

Extracts resolve_for_runs helper from existing channel resolver — no
behavior change for existing callers. DRY against _compute_hit_call.
Returns summary + per-row provenance with concentration, replicate
count, QC pass for report-grade preview.
```

---

### Task 5 — `AddResultsFromRuns` use case (replaces single-run)

**Files:**
- Create: `backend/src/cellar/application/research_organization/add_results_from_runs.py`
- Delete: `backend/src/cellar/application/research_organization/add_results_from_run.py`
- Create: `backend/tests/unit/application/research_organization/test_add_results_from_runs.py`
- Delete: `backend/tests/unit/application/research_organization/test_add_results_from_run*.py`

- [ ] **Step 5.1: Skeleton** mirrors `PreviewRunImport` but mutates. Adds `scope`, `default_decision`, `description`, `refresh_existing_cells`. Reuses the same `resolve_for_runs` + `_compute_hit_call` path so preview ≡ commit.

- [ ] **Step 5.2: Flow** per spec §3.2. Key invariants:
  - DRAFT-only (lock guard).
  - Preserve measurement id when refreshing existing non-override cells (matches the `RefreshFromSources` pattern — UPDATE not DELETE+INSERT, to avoid the non-deferrable unique-constraint collision).
  - Channel reuse: lookup `(protocol_id, readout_definition_id)`; reuse id and apply updated rule/threshold if user changed them.
  - New molecules: `CampaignResult.create` with `added_from=RunRef(run_id=<first contributing>, description=q.description)`.
  - Snapshot all B6 fields into each `CampaignMeasurement` (concentration, N, QC, contributing run ids).
  - Returns `AddResultsOutcomeResponse{added, skipped, channels_created, channels_reused, campaign}`.

- [ ] **Step 5.3: Write tests** in `test_add_results_from_runs.py`:

```python
# Case 1: single run, single channel, hits-only mode → adds only hits with default_decision=SELECTED
# Case 2: scope=all → adds everyone with caller's default_decision
# Case 3: channel reuse — campaign already has matching (protocol, readout) → channel id unchanged
# Case 4: channel create — new (protocol, readout) → new CampaignChannel.id
# Case 5: idempotent re-run with same config → 0 added; existing rows untouched (refresh=False)
# Case 6: refresh_existing_cells=True → non-override cells updated, override cells preserved
# Case 7: locked campaign → DataLockedError (lock guard)
# Case 8: AND filter mode with hits_only → only molecules hitting in ALL active channels added
# Case 9: all use_for_filter=False + hits_only → 0 added (no active filter = no hits)
# Case 10: snapshot fields (concentration, replicate_count, qc_pass) populate on new measurements
```

- [ ] **Step 5.4: Delete the old single-run UC + test files** — `git rm ...`.

- [ ] **Step 5.5: Run the full app suite** — `uv run pytest tests/unit/application/research_organization/ -q`. Green.

- [ ] **Step 5.6: Commit.**

```
feat(campaign): AddResultsFromRuns (multi-run, replaces single)

Removes the disabled-FE-only AddResultsFromRun. Multi-run path snapshots
concentration/replicate/qc per cell at import. Filter modes ANY/ALL,
scope hits_only/all, default_decision configurable. Idempotent.
Channel reuse + create unified path.
```

---

### Task 6 — Update DAIKON serializer + DTO (B8 + new snapshot fields)

**Files:**
- Modify: `backend/src/cellar/application/research_organization/get_published_campaign.py`
- Modify: `backend/src/cellar/interface/routes/campaigns.py::CampaignMeasurementResponse`
- Modify/Add: `backend/tests/integration/test_campaign_published_contract.py` (or wherever contract tests live)

- [ ] **Step 6.1: Extend `_serialize_measurement`** (around line 419):

```python
return {
    "channel_id": str(m.channel_id),
    "value": m.value,
    "value_qualifier": m.value_qualifier.value,
    "unit": m.unit,
    "hit_call": m.hit_call.value if m.hit_call else None,
    "is_manual_override": m.is_manual_override,
    "override_reason": m.override_reason,
    "test_concentration": (
        {"value": m.test_concentration_value, "unit": m.test_concentration_unit}
        if m.test_concentration_value is not None else None
    ),
    "replicate_count": m.replicate_count,
    "qc_pass": m.qc_pass,
    "source": source,
    "contributing_run_ids": (
        [str(rid) for rid in m.contributing_run_ids]
        if m.contributing_run_ids else None
    ),
}
```

- [ ] **Step 6.2: Extend `CampaignMeasurementResponse` DTO** in `campaigns.py` with the same fields, so FE consumers see them in draft view too.

- [ ] **Step 6.3: Test** — extend the published-contract fixture so the closed campaign has at least one measurement with non-null `override_reason` + `test_concentration_value` + `replicate_count`. Assert they appear in the JSON.

- [ ] **Step 6.4: Run** `uv run pytest tests/integration/ -q -k campaign`. Green.

- [ ] **Step 6.5: Commit.**

```
feat(campaign): DAIKON published JSON carries snapshot + audit fields

Adds override_reason, test_concentration{value,unit}, replicate_count,
qc_pass, contributing_run_ids to the measurement block. Flat schema —
null when absent. Existing closed campaigns remain valid.
```

---

### Task 7 — API routes: preview + add-from-runs + remove single + preview-published

**Files:**
- Modify: `backend/src/cellar/interface/routes/campaigns.py`
- Modify: `backend/src/cellar/interface/dependencies.py`
- Modify: `backend/tests/api/test_campaigns_api.py`

- [ ] **Step 7.1: DI wiring** — add `PreviewRunImportDep`, `AddResultsFromRunsDep`; remove `AddResultsFromRunDep`. Wire the new use cases in the DI container.

- [ ] **Step 7.2: New request DTOs:**

```python
class ChannelImportConfigDTO(BaseModel):
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    label: str
    selection_rule: str
    hit_threshold: HitCriterionDTO | None = None
    use_for_filter: bool = True

class PreviewRunImportRequest(BaseModel):
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfigDTO]
    filter_mode: Literal["any", "all"] = "all"

class AddFromRunsRequest(PreviewRunImportRequest):
    scope: Literal["hits_only", "all"] = "hits_only"
    default_decision: str = "selected"
    description: str | None = None
    refresh_existing_cells: bool = False
```

- [ ] **Step 7.3: Routes:**

```python
@router.post("/{campaign_id}/preview-run-import")
async def preview_run_import(
    campaign_id: uuid.UUID, body: PreviewRunImportRequest,
    auth: AuthDep, uc: PreviewRunImportDep,
) -> dict[str, Any]:
    cmd = PreviewRunImportQuery(
        workspace_id=auth.workspace_id, campaign_id=campaign_id,
        run_ids=body.run_ids,
        channel_configs=[_to_domain(c) for c in body.channel_configs],
        filter_mode=body.filter_mode,
    )
    return result_to_response(await uc(cmd, auth=auth))


@router.post("/{campaign_id}/add-from-runs", response_model=AddResultsOutcomeResponse)
async def add_results_from_runs(
    campaign_id: uuid.UUID, body: AddFromRunsRequest,
    auth: AuthDep, uc: AddResultsFromRunsDep,
) -> AddResultsOutcomeResponse:
    cmd = AddFromRunsCommand(
        workspace_id=auth.workspace_id, campaign_id=campaign_id,
        run_ids=body.run_ids,
        channel_configs=[_to_domain(c) for c in body.channel_configs],
        filter_mode=body.filter_mode, scope=body.scope,
        default_decision=CampaignDecision(body.default_decision),
        description=body.description,
        refresh_existing_cells=body.refresh_existing_cells,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)
```

- [ ] **Step 7.4: Remove `/{campaign_id}/add-from-run`** route handler and references to `AddResultsFromRunDep`.

- [ ] **Step 7.5: Preview-as-published bonus route.** Add an optional `bypass_status_check: bool = False` param to `GetPublishedCampaignQuery`; in the use case, skip the closed/superseded status check when True. Then:

```python
@router.get("/{campaign_id}/preview-published")
async def preview_published_campaign(
    campaign_id: uuid.UUID, auth: AuthDep, uc: GetPublishedCampaignDep,
) -> dict[str, Any]:
    """Render any campaign (incl. DRAFT) through the DAIKON serializer."""
    q = GetPublishedCampaignQuery(
        workspace_id=auth.workspace_id, campaign_id=campaign_id,
        bypass_status_check=True,
    )
    return result_to_response(await uc(q, auth=auth))
```

- [ ] **Step 7.6: API tests:**
  - `POST /preview-run-import` — shape contract.
  - `POST /add-from-runs` — happy path (single-run case via `run_ids=[one]`); idempotency; locked-423.
  - `GET /preview-published` — DRAFT campaign returns DAIKON shape.
  - Verify `POST /add-from-run` returns 404 (route removed).

- [ ] **Step 7.7: Run** `uv run pytest tests/api/test_campaigns_api.py -v`. Green.

- [ ] **Step 7.8: Commit.**

```
feat(campaign): API — preview-run-import + add-from-runs + preview-published; remove single-run

Replaces /add-from-run with /add-from-runs. New /preview-run-import for
debounced live-preview from the FE. /preview-published lets screeners
see the DAIKON shape against a DRAFT before close.
```

---

### Task 8 — Update OpenAPI spec + orval regen

**Files:**
- Modify: `frontend/openapi.json` (or wherever the cached spec lives — check `orval.config.ts`)
- Regen: `frontend/src/shared/lib/api/**`

- [ ] **Step 8.1: Export OpenAPI spec.** With a running backend dev server: `curl http://localhost:8000/openapi.json > frontend/openapi.json`. (Or use the project's export script.)

- [ ] **Step 8.2: Run** `cd frontend && pnpm orval`. Verify new hooks: `usePreviewRunImport*`, `useAddResultsFromRuns*`, `usePreviewPublishedCampaign*`. Confirm removal of `useAddResultsFromRun*`.

- [ ] **Step 8.3: Run** `pnpm tsc --noEmit`. Green.

- [ ] **Step 8.4: Commit.**

```
chore(fe): regen orval against new campaign endpoints (B6 + Preview-as-published)
```

---

### Task 9 — `<MoleculeThumbnail>` shared component (B1)

**Files:**
- Create: `frontend/src/shared/components/molecule-thumbnail.tsx`
- Modify: `frontend/src/features/screen-campaign/components/results-grid.tsx`
- Modify: `frontend/src/features/screen-campaign/components/decision-panel.tsx`

- [ ] **Step 9.1: Locate the existing depiction utility** — `rg "RDKit|depict|MolImage|MoleculeStructure|SmilesToSvg" frontend/src/`. Identify the function/component to wrap. The existing utility is the safe-rendering primitive; this task wraps it for consistent sizing — does **not** render raw SVG via `dangerouslySetInnerHTML`.

- [ ] **Step 9.2: Component scaffold.**

```tsx
"use client";
import { MoleculeStructure } from "<existing path from Step 9.1>";

interface MoleculeThumbnailProps {
  smiles: string | null | undefined;
  size?: "sm" | "md" | "lg";
  fallback?: React.ReactNode;
}

const SIZES = {
  sm: { width: 48, height: 36 },
  md: { width: 200, height: 150 },
  lg: { width: 320, height: 240 },
};

export function MoleculeThumbnail({ smiles, size = "sm", fallback = null }: MoleculeThumbnailProps) {
  const dims = SIZES[size];
  if (!smiles) return <>{fallback}</>;
  return (
    <div style={{ width: dims.width, height: dims.height }} className="inline-block shrink-0">
      <MoleculeStructure smiles={smiles} width={dims.width} height={dims.height} />
    </div>
  );
}
```

(Adapt the underlying component's prop names per Step 9.1 findings.)

- [ ] **Step 9.3: Wire into results-grid compound column** — replace the `font-mono reg-id only` cell renderer with a 2-column layout: thumbnail (48×36) + reg-id stacked text.

- [ ] **Step 9.4: Wire into decision-panel header** — 200×150 thumbnail above the molecule name.

- [ ] **Step 9.5: Run** `pnpm tsc --noEmit`. Green.

- [ ] **Step 9.6: Browser smoke** — load a campaign with ≥1 compound; verify thumbnails render in both places.

- [ ] **Step 9.7: Commit.**

```
feat(fe/campaign): structure thumbnails in grid + decision panel (B1)
```

---

### Task 10 — `<CampaignFilterBar>` (B5)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/campaign-filter-bar.tsx`
- Modify: `frontend/src/features/screen-campaign/components/campaign-builder.tsx`
- Modify: `frontend/src/features/screen-campaign/components/results-grid.tsx` (accept filter-state props)

- [ ] **Step 10.1: Filter state model.**

```ts
export interface CampaignFilters {
  decisions: Set<"selected" | "deferred" | "rejected">;
  hitStatus: Set<"hit" | "non_hit" | "nd">;
  overriddenOnly: boolean;
}
```

Lives in `campaign-builder.tsx` as `useState`; passed down.

- [ ] **Step 10.2: Filter-bar component** — three chip groups + the audit toggle. Each chip shows count and toggles its set.

- [ ] **Step 10.3: AG Grid integration** — wire `isExternalFilterPresent` + `doesExternalFilterPass` on `<AgGridReact>`. Add a `computeRowHitStatus(cells)` helper next to results-grid.

- [ ] **Step 10.4: Render the bar in campaign-builder.tsx** — between the sticky header and the 3-pane grid.

- [ ] **Step 10.5: Run** `pnpm tsc --noEmit`. Green.

- [ ] **Step 10.6: Commit.**

```
feat(fe/campaign): chip filter bar — decision + hit status + overridden-only (B5)
```

---

### Task 11 — Override modal qualifier gating + required reason (B7 + B8 FE)

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/results-grid.tsx` (OverrideModal)

- [ ] **Step 11.1: Add `reason` state.**

```tsx
const [reason, setReason] = useState(measurement?.override_reason ?? "");
```

- [ ] **Step 11.2: Compute "value differs from auto"** — compare current form value/qualifier/unit against `measurement` props. If they differ and `is_manual_override` is becoming true, `reasonRequired = true`.

- [ ] **Step 11.3: Qualifier change effect** — when `qualifier in {"nd","excluded"}`, set `value = ""` and `unit = ""`; disable both inputs.

- [ ] **Step 11.4: Submit gate** — `canSubmit = !reasonRequired || reason.trim().length > 0`. Pass `reason: reason.trim() || undefined` to the mutation payload.

- [ ] **Step 11.5: Render textarea** under the value/unit row with a "Required when changing the auto-resolved value" hint.

- [ ] **Step 11.6: Tooltip on grid `OVR` badge** — wrap with `<TooltipProvider>` showing `measurement.override_reason` when present.

- [ ] **Step 11.7: Run** `pnpm tsc --noEmit`. Green.

- [ ] **Step 11.8: Commit.**

```
feat(fe/campaign): override modal — ND/excluded gating + required reason (B7+B8)
```

---

### Task 12 — `<AddFromRunsDialog>` (B6 FE — the meaty one)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/add-from-runs-dialog.tsx`
- Modify: `frontend/src/features/screen-campaign/components/compound-list-pane.tsx` (replace disabled "From protocol run" item)
- Modify: `frontend/src/features/screen-campaign/lib/hooks.ts` (export new hooks)

- [ ] **Step 12.1: Hooks** — wrap orval-generated `usePreviewRunImport*` and `useAddResultsFromRuns*` with project-friendly names (e.g., `usePreviewRunImport`, `useAddResultsFromRuns`).

- [ ] **Step 12.2: Dialog skeleton** — two internal steps; `step: "configure" | "preview"` state.

- [ ] **Step 12.3: Step 1 — Configure.** Layout:
  - **Top:** `<Input>` search + filter chips (`Same project`, `Approved only`, `QC pass`); each toggleable. Use existing run-query hook with appropriate filters.
  - **Run list:** scrollable; each row a `<Checkbox>` + run name + protocol + approval/QC chips + molecule count + Z'.
  - **Channel cards:** populated dynamically from `derived = unique(selectedRuns.flatMap(r => r.protocol.readouts.map(rd => ({protocol_id, readout_id, label, hit_criterion_default}))))`. Each card: editable label, selection-rule radio, hit-criterion form (operator + value + unit), Use-for-filter checkbox.
  - **Global toggles:** filter mode (AND default / ANY), scope (hits_only default / all), default decision (Selected default / Deferred / Rejected), `Refresh non-override cells for already-in-campaign molecules`.
  - **Next button** → `step = "preview"`.

- [ ] **Step 12.4: Step 2 — Preview.** On mount + on every config-state change (debounced 300ms):

```tsx
useEffect(() => {
  const t = setTimeout(() => {
    previewMutation.mutate({ campaignId, data: buildPayload() });
  }, 300);
  return () => clearTimeout(t);
}, [/* config dependency list */]);
```

Renders the preview response: 3 count chips + scrollable molecule table with thumbnails + per-channel cells displayed as `value qualifier @ concentration · N=rep · QC chip · hit chip`. Hover popover for full provenance (contributing runs, run picked, override flag).

- [ ] **Step 12.5: Commit button.** Live label (`Add 23 hits` / `Add 87 compounds`). Fires `addMutation.mutate({campaignId, data: buildPayload()})`. On success: invalidate `campaignKeys.detail(campaignId)`, close dialog, toast `"Added N compounds"`.

- [ ] **Step 12.6: Wire into compound-list-pane dropdown.** Replace the disabled "From a protocol run" item with an enabled item that opens `<AddFromRunsDialog>`. Update the label to "Protocol run(s)…".

- [ ] **Step 12.7: Run** `pnpm tsc --noEmit`. Green.

- [ ] **Step 12.8: Commit.**

```
feat(fe/campaign): AddFromRunsDialog — multi-run + hit-criteria preview (B6)
```

---

### Task 13 — `<PreviewAsPublishedDialog>` (bonus)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/preview-as-published-dialog.tsx`
- Modify: `frontend/src/features/screen-campaign/components/campaign-builder.tsx`

- [ ] **Step 13.1: Hook** — wrap orval-generated `usePreviewPublishedCampaign*`.

- [ ] **Step 13.2: Dialog component** — large `<Dialog>` (sm:max-w-4xl). On open, fetch via the hook. Render:
  - **Top:** campaign header (name, status, closed_at if any, source_protocols).
  - **Middle:** channels list.
  - **Bottom:** results table (thumbnails + per-channel cell display, read-only).
  - **Footer:** "This is the shape DAIKON will receive." + download-JSON button (reuse pattern from the existing `campaign-view/index.tsx`).

- [ ] **Step 13.3: Button in builder header** — add `<Button variant="outline" size="sm">` "Preview as published" next to `Refresh`/`Close & Sign`.

- [ ] **Step 13.4: Run** `pnpm tsc --noEmit`. Green.

- [ ] **Step 13.5: Commit.**

```
feat(fe/campaign): Preview-as-published dialog — render DRAFT through DAIKON serializer (bonus)
```

---

### Task 14 — Final typecheck, lint, smoke checklist, handoff

**Files:** None except docs.

- [ ] **Step 14.1: Backend** — `cd backend && uv run pytest -q`. All green.

- [ ] **Step 14.2: FE typecheck** — `cd frontend && pnpm tsc --noEmit`. Green.

- [ ] **Step 14.3: Manual smoke per spec §9** — record results in the session notes; capture screenshots for B1, B5, B6 preview, override modal, Preview-as-published.

- [ ] **Step 14.4: Update CLAUDE.md "Current Session Notes"** — fresh handoff summarizing shipped tasks, deviations, remaining open follow-ups.

- [ ] **Step 14.5: Update memory pointer** — `~/.claude/projects/-Users-sidx-workspace-cellar2/memory/project_screen_campaign.md`.

- [ ] **Step 14.6: Commit final doc changes** (no remote push without explicit user permission).

```
docs(campaign): handoff after B-gap UX (B1/B5/B6/B7/B8 + Preview-as-published)
```

---

## Self-review notes

- **Spec coverage:** Every spec section maps to a task (§3 → Tasks 4–7+12; §4.1 → Task 9; §4.2 → Task 10; §4.3/4.4 → Tasks 2+3+11; §4.5 → Tasks 7+13; §5 → Task 1; §6 → Task 6).
- **DRY guard:** `_compute_hit_call` is imported, not reimplemented (Task 4); `_serialize_*` are extended, not parallel (Task 6); channel resolver gets a helper extracted, not forked (Task 4 §4.2).
- **Migration ordering:** Task 1 must land first; all subsequent backend tasks depend on the new columns existing on the ORM.
- **Backwards compat:** New columns are nullable; existing closed campaigns serialize the new fields as `null`; no data migration needed.
- **Test order:** TDD where the test exists pre-impl (Tasks 2, 3, 4, 5). For Task 6 (serializer extension), the contract test extension is added in the same commit.
- **Removed `dangerouslySetInnerHTML`:** Task 9 uses the existing `<MoleculeStructure>` component (located in Step 9.1) rather than rendering raw SVG.
