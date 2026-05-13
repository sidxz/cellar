# Campaign Search-Style Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Campaign 3-pane shell with a single-column, Search-style layout: uppercase section blocks, an AG-Grid with inline dose-response cells, decisions edited via popover, and project-scoped pickers throughout.

**Architecture:** One backend addition (`POST /api/v1/dose-response/curves:batch`) feeds inline DR plots. Six phased FE PRs: scaffold the new sections, build the new grid + DR cell + popover, switch to it by default, delete the old shell, add customize-report + project-scoping, and finish with Playwright. All work on branch `fe2`.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0 async, pytest. Frontend — Next.js 16, React 19, TypeScript 5.7, AG Grid Community, Plotly (existing wrapper), TanStack Query v5, Zustand, shadcn/ui. Playwright for E2E (not yet configured).

**Spec:** `docs/superpowers/specs/2026-05-12-campaign-search-style-redesign.md`

---

## Phase 1 — Backend: batch DRC endpoint

Single PR. Adds one repo method, one route, one router include. Re-runs orval.

### Task 1.1: Add `find_by_ids` to the DRC repository

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (Protocol)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/dose_response_curve_repository.py`
- Test: `backend/tests/integration/test_dose_response_curve_repository_find_by_ids.py` (NEW)

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_dose_response_curve_repository_find_by_ids.py`:

```python
"""Integration test: DoseResponseCurveRepository.find_by_ids."""
import uuid
import pytest
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from tests.fixtures.dose_response_curves import seed_curve  # see step 2 if it doesn't exist


@pytest.mark.asyncio
class TestFindByIds:
    async def test_returns_curves_for_matching_ids(self, uow, workspace_id):
        async with uow:
            c1 = await seed_curve(uow, workspace_id=workspace_id)
            c2 = await seed_curve(uow, workspace_id=workspace_id)
            c3 = await seed_curve(uow, workspace_id=workspace_id)
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids(workspace_id, [c1.id, c3.id])
        ids = {c.id for c in curves}
        assert ids == {c1.id, c3.id}

    async def test_filters_by_workspace(self, uow, workspace_id):
        other_ws = uuid.uuid4()
        async with uow:
            c1 = await seed_curve(uow, workspace_id=workspace_id)
            c2 = await seed_curve(uow, workspace_id=other_ws)
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids(workspace_id, [c1.id, c2.id])
        assert {c.id for c in curves} == {c1.id}

    async def test_empty_input_returns_empty(self, uow, workspace_id):
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids(workspace_id, [])
        assert curves == []

    async def test_missing_ids_silently_dropped(self, uow, workspace_id):
        async with uow:
            c1 = await seed_curve(uow, workspace_id=workspace_id)
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids(workspace_id, [c1.id, uuid.uuid4()])
        assert [c.id for c in curves] == [c1.id]
```

- [ ] **Step 2: Confirm/seed the `seed_curve` fixture**

Run: `grep -rn "def seed_curve\|async def seed_curve" backend/tests/fixtures/ 2>/dev/null`

If it doesn't exist, copy the curve-seeding pattern from any existing integration test that creates curves (e.g. search for `DoseResponseCurveModel(` under `backend/tests/integration/`) into a new helper file `backend/tests/fixtures/dose_response_curves.py`. The helper must create a Run + ReadoutDefinition + DoseResponseCurveModel and return the curve aggregate. Match the existing patterns; do not invent fields.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_dose_response_curve_repository_find_by_ids.py -x -v`
Expected: FAIL — `AttributeError: ... no attribute 'find_by_ids'` (or import error).

- [ ] **Step 4: Add `find_by_ids` to the Protocol**

In `backend/src/cellar/domain/screening_assay/repository.py`, add to `DoseResponseCurveRepository` (after `find_by_molecule`, before `find_best_curves_for_molecules`):

```python
    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[DoseResponseCurve]: ...
```

(Parameter order `(workspace_id, ids)` matches the existing convention in `AssayProtocolRepository.find_by_ids` and `MoleculeRepository.find_by_ids`. Don't invert.)

- [ ] **Step 5: Implement `find_by_ids` in the SQLAlchemy repo**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/dose_response_curve_repository.py`, add after `find_by_molecule` (around line 153):

```python
    async def find_by_ids(
        self, workspace_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[DoseResponseCurve]:
        """Batch lookup by primary key, scoped to workspace."""
        if not ids:
            return []
        stmt = (
            select(DoseResponseCurveModel)
            .where(
                DoseResponseCurveModel.workspace_id == workspace_id,
                DoseResponseCurveModel.id.in_(ids),
            )
        )
        result = await self._uow.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/test_dose_response_curve_repository_find_by_ids.py -x -v`
Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add backend/src/cellar/domain/screening_assay/repository.py \
  backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/dose_response_curve_repository.py \
  backend/tests/integration/test_dose_response_curve_repository_find_by_ids.py \
  backend/tests/fixtures/dose_response_curves.py
git -C /Users/sidx/workspace/cellar2 commit -m "feat(be/screening): DoseResponseCurveRepository.find_by_ids"
```

---

### Task 1.2: Add `POST /api/v1/dose-response/curves:batch` route

**Files:**
- Create: `backend/src/cellar/interface/routes/dose_response_curves.py`
- Test: `backend/tests/api/test_dose_response_curves_batch.py` (NEW)

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/api/test_dose_response_curves_batch.py`:

```python
"""API test: POST /api/v1/dose-response/curves:batch."""
import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestBatchCurvesEndpoint:
    async def test_returns_curves_for_ids(self, api_client: AsyncClient, seeded_curve_ids):
        body = {"curve_ids": [str(i) for i in seeded_curve_ids[:2]]}
        resp = await api_client.post("/api/v1/dose-response/curves:batch", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert {c["id"] for c in data["curves"]} == {str(i) for i in seeded_curve_ids[:2]}
        # Sanity-check the response shape matches DoseResponseCurveResponse.
        first = data["curves"][0]
        assert "raw_data" in first
        assert "fitted_value" in first

    async def test_empty_input_returns_empty(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/dose-response/curves:batch", json={"curve_ids": []}
        )
        assert resp.status_code == 200
        assert resp.json() == {"curves": []}

    async def test_max_500_ids(self, api_client: AsyncClient):
        body = {"curve_ids": [str(uuid.uuid4()) for _ in range(501)]}
        resp = await api_client.post("/api/v1/dose-response/curves:batch", json=body)
        assert resp.status_code == 400
        assert "max 500" in resp.text.lower() or "too many" in resp.text.lower()

    async def test_workspace_isolation(self, api_client: AsyncClient, foreign_curve_id):
        body = {"curve_ids": [str(foreign_curve_id)]}
        resp = await api_client.post("/api/v1/dose-response/curves:batch", json=body)
        assert resp.status_code == 200
        assert resp.json()["curves"] == []
```

The fixtures `api_client`, `seeded_curve_ids`, `foreign_curve_id` must exist in `backend/tests/api/conftest.py` or `backend/tests/conftest.py`. If `seeded_curve_ids` and `foreign_curve_id` do not exist, add fixtures that wrap `seed_curve` from Task 1.1, with one curve seeded in a foreign workspace.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_dose_response_curves_batch.py -x -v`
Expected: FAIL — `404 Not Found` (route doesn't exist).

- [ ] **Step 3: Create the route file**

Create `backend/src/cellar/interface/routes/dose_response_curves.py`:

```python
"""Batch read endpoints for DoseResponseCurves.

The campaign UI uses POST /curves:batch to inline DR plots in the results
grid. The cap of 500 ids per request comfortably fits typical campaigns
(1 channel * <=200 compounds = <=200 curves) while bounding payload size.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.interface.dependencies import AuthDep, UoWDep
from cellar.interface.routes.readout_data import DoseResponseCurveResponse

router = APIRouter(prefix="/api/v1/dose-response", tags=["dose-response"])


class BatchCurvesRequest(BaseModel):
    curve_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class BatchCurvesResponse(BaseModel):
    curves: list[DoseResponseCurveResponse]


@router.post("/curves:batch", response_model=BatchCurvesResponse)
async def get_curves_batch(
    body: BatchCurvesRequest,
    auth: AuthDep,
    uow: UoWDep,
) -> BatchCurvesResponse:
    """Look up dose-response curves by id, scoped to the caller's workspace.

    Returns an empty list for missing ids or curves in a foreign workspace.
    Cap: 500 ids per request.
    """
    if len(body.curve_ids) > 500:
        raise HTTPException(status_code=400, detail="max 500 curve ids per request")
    repo = SQLAlchemyDoseResponseCurveRepository(uow)
    async with uow:
        curves = await repo.find_by_ids(auth.workspace_id, body.curve_ids)
    return BatchCurvesResponse(
        curves=[DoseResponseCurveResponse.from_domain(c) for c in curves]
    )
```

- [ ] **Step 4: Register the router**

In `backend/src/cellar/interface/app.py`, find the block where domain routers are included (around line 185 — `protocol_router`, `run_router`). Add:

```python
    from cellar.interface.routes.dose_response_curves import router as drc_batch_router
    app.include_router(drc_batch_router)
```

Place it next to the protocol/run includes for locality.

- [ ] **Step 5: Run the API test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_dose_response_curves_batch.py -x -v`
Expected: 4 tests PASS.

- [ ] **Step 6: Verify the full backend test suite still passes**

Run: `cd backend && uv run pytest -x -q`
Expected: existing tests unchanged (no regression).

- [ ] **Step 7: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add backend/src/cellar/interface/routes/dose_response_curves.py \
  backend/src/cellar/interface/app.py \
  backend/tests/api/test_dose_response_curves_batch.py \
  backend/tests/api/conftest.py
git -C /Users/sidx/workspace/cellar2 commit -m "feat(be/dose-response): POST /api/v1/dose-response/curves:batch"
```

---

### Task 1.3: Regenerate the FE orval client

**Files:**
- Modify: `frontend/src/shared/lib/api/dose-response/*` (orval output)
- Modify: `frontend/src/shared/lib/api/dose-response.schemas.ts` (if your orval setup produces a schemas file)

- [ ] **Step 1: Export the OpenAPI spec**

The project uses orval with a generated OpenAPI export. Run the existing export script (check `frontend/orval.config.ts` or `package.json` scripts for the exact command). Typically:

```bash
cd /Users/sidx/workspace/cellar2/backend
uv run python -m cellar.interface.export_openapi > ../frontend/openapi.json
```

If the export entry point has a different name, run `grep -rn "openapi.*export\|export_openapi" backend/src/cellar/interface/` to find it.

- [ ] **Step 2: Run orval**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm orval
```

This should generate / update files under `frontend/src/shared/lib/api/dose-response/`.

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```

Expected: PASS. (Generated code uses existing patterns.)

- [ ] **Step 4: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/shared/lib/api/dose-response/ frontend/openapi.json
git -C /Users/sidx/workspace/cellar2 commit -m "chore(fe): regen orval for dose-response curves:batch"
```

---

## Phase 2 — FE: new sections behind `?v2=1`

Single PR. Adds the new layout's section components and a `?v2=1` query toggle in `CampaignBuilder` so the legacy 3-pane shell remains default while review happens. No grid changes yet.

### Task 2.1: Add a `?v2=1` toggle in `CampaignBuilder`

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/campaign-builder.tsx`

- [ ] **Step 1: Read the current builder file**

Read: `frontend/src/features/screen-campaign/components/campaign-builder.tsx` (210 lines). Note where the draft/closed status dispatch is and where the 3-pane grid layout is rendered.

- [ ] **Step 2: Add the toggle**

In `campaign-builder.tsx`, add the toggle near the top of the draft branch:

```typescript
import { useSearchParams } from "next/navigation";

// inside CampaignBuilder, after `const { data: campaign } = useCampaign(campaignId);`:
const searchParams = useSearchParams();
const useV2 = searchParams.get("v2") === "1";
```

Then in the draft return, branch on `useV2`:

```typescript
if (useV2) {
  return <CampaignBuilderV2 campaign={campaign} projectId={projectId} />;
}
// existing 3-pane layout below — unchanged
```

`CampaignBuilderV2` is the new shell defined in Task 2.7. For this task, stub it as an empty placeholder so the file compiles:

```typescript
function CampaignBuilderV2({ campaign, projectId }: { campaign: CampaignResponse; projectId: string }) {
  return <div className="p-8 text-muted-foreground">v2 layout — under construction</div>;
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/campaign-builder.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): ?v2=1 toggle scaffolding"
```

---

### Task 2.2: Build the `HeaderStrip` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/sections/header-strip.tsx`

- [ ] **Step 1: Create the component**

Create the file:

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { RefreshCw, FileText, Lock } from "lucide-react";
import type { CampaignResponse } from "@/shared/lib/api/campaigns.schemas";
import { CampaignStatusChip } from "../campaign-status-chip";

interface HeaderStripProps {
  campaign: CampaignResponse;
  onRefresh: () => void;
  onPreview: () => void;
  onCloseAndSign: () => void;
  refreshing?: boolean;
  isDraft: boolean;
}

export function HeaderStrip({
  campaign,
  onRefresh,
  onPreview,
  onCloseAndSign,
  refreshing,
  isDraft,
}: HeaderStripProps) {
  const channelCount = campaign.channels?.length ?? 0;
  const compoundCount = campaign.results?.length ?? 0;
  return (
    <header className="flex flex-col gap-1 border-b px-6 py-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{campaign.name}</h1>
        <CampaignStatusChip status={campaign.status} />
        <Badge variant="outline" className="text-xs">
          {channelCount} {channelCount === 1 ? "channel" : "channels"}
        </Badge>
        <Badge variant="outline" className="text-xs">
          {compoundCount} {compoundCount === 1 ? "compound" : "compounds"}
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          {isDraft && (
            <>
              <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                Refresh
              </Button>
              <Button variant="outline" size="sm" onClick={onPreview}>
                <FileText className="h-4 w-4" />
                Preview as published
              </Button>
              <Button size="sm" onClick={onCloseAndSign}>
                <Lock className="h-4 w-4" />
                Close &amp; Sign
              </Button>
            </>
          )}
        </div>
      </div>
      {campaign.description && (
        <p className="text-sm text-muted-foreground">{campaign.description}</p>
      )}
    </header>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS. (If a lucide icon name is wrong, fix to the project-consistent name; check `frontend/src/features/screen-campaign/components/campaign-builder.tsx` for what's already imported.)

- [ ] **Step 3: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/sections/header-strip.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): HeaderStrip section component"
```

---

### Task 2.3: Build the `AddCompoundsPills` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/add/add-compounds-pills.tsx`

This component renders the 4 `+Add` pills (Run / Collection / Campaign / Manual) and owns the dialog open-state. It wraps the existing dialogs unchanged — just changes the trigger UI.

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import type { CampaignResponse } from "@/shared/lib/api/campaigns.schemas";
import { AddFromCollectionDialog } from "../add-from-collection-dialog";
import { AddFromCampaignDialog } from "../add-from-campaign-dialog";
import { AddFromRunsDialog } from "../add-from-runs-dialog";
// NOTE: the existing manual-add dialog is internal to `compound-list-pane.tsx`.
// Re-extract it into `manual-add-dialog.tsx` if you find it inlined; otherwise
// import it directly from wherever it lives.
import { ManualAddDialog } from "./manual-add-dialog";

interface AddCompoundsPillsProps {
  campaign: CampaignResponse;
  projectId: string;
  disabled?: boolean;
}

const PILL_CLASS =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50";

export function AddCompoundsPills({ campaign, projectId, disabled }: AddCompoundsPillsProps) {
  const [open, setOpen] = useState<"run" | "collection" | "campaign" | "manual" | null>(null);
  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" className={PILL_CLASS} disabled={disabled} onClick={() => setOpen("run")}>
          <Plus className="h-3 w-3" /> Run
        </button>
        <button type="button" className={PILL_CLASS} disabled={disabled} onClick={() => setOpen("collection")}>
          <Plus className="h-3 w-3" /> Collection
        </button>
        <button type="button" className={PILL_CLASS} disabled={disabled} onClick={() => setOpen("campaign")}>
          <Plus className="h-3 w-3" /> Campaign
        </button>
        <button type="button" className={PILL_CLASS} disabled={disabled} onClick={() => setOpen("manual")}>
          <Plus className="h-3 w-3" /> Manual
        </button>
      </div>
      <AddFromRunsDialog
        open={open === "run"}
        onOpenChange={(v) => !v && setOpen(null)}
        campaignId={campaign.id}
        projectId={projectId}
      />
      <AddFromCollectionDialog
        open={open === "collection"}
        onOpenChange={(v) => !v && setOpen(null)}
        campaignId={campaign.id}
        projectId={projectId}
      />
      <AddFromCampaignDialog
        open={open === "campaign"}
        onOpenChange={(v) => !v && setOpen(null)}
        campaignId={campaign.id}
        projectId={projectId}
      />
      <ManualAddDialog
        open={open === "manual"}
        onOpenChange={(v) => !v && setOpen(null)}
        campaignId={campaign.id}
      />
    </>
  );
}
```

- [ ] **Step 2: Extract `ManualAddDialog` if it's inlined**

Run: `grep -n "manualOpen\|Manual (single" frontend/src/features/screen-campaign/components/compound-list-pane.tsx`

If the manual single-compound dialog is inlined in `compound-list-pane.tsx`, extract it to `frontend/src/features/screen-campaign/components/add/manual-add-dialog.tsx` with the same props shape used in `AddCompoundsPills`. Leave the original `compound-list-pane.tsx` in place still importing the new file — this keeps the old shell working until Phase 4.

- [ ] **Step 3: Wire `projectId` prop into the three add-from-* dialogs**

For each of `AddFromRunsDialog`, `AddFromCollectionDialog`, `AddFromCampaignDialog`, add a `projectId: string` prop to the props interface and accept it (do not yet use it — Phase 5 actually scopes the picker). This is just to make `AddCompoundsPills` compile.

Example for one of them:

```typescript
interface AddFromRunsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
  projectId: string;  // NEW — scope applied in Phase 5
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/add/ \
  frontend/src/features/screen-campaign/components/add-from-runs-dialog.tsx \
  frontend/src/features/screen-campaign/components/add-from-collection-dialog.tsx \
  frontend/src/features/screen-campaign/components/add-from-campaign-dialog.tsx \
  frontend/src/features/screen-campaign/components/compound-list-pane.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): AddCompoundsPills + projectId plumbing"
```

---

### Task 2.4: Build the `SourcesSection` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/sections/sources-section.tsx`

- [ ] **Step 1: Create the section**

```tsx
"use client";

import { X } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import type { CampaignResponse } from "@/shared/lib/api/campaigns.schemas";
import { AddCompoundsPills } from "../add/add-compounds-pills";

interface SourcesSectionProps {
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
  onRemoveSource?: (sourceKey: string) => void;
}

const SECTION_HEADING =
  "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

export function SourcesSection({ campaign, projectId, readOnly, onRemoveSource }: SourcesSectionProps) {
  const sources = campaign.compound_sources ?? [];
  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Sources</h2>
        {!readOnly && (
          <AddCompoundsPills campaign={campaign} projectId={projectId} />
        )}
      </div>
      {sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">No compounds yet — add via the pills above.</p>
      ) : (
        <ul className="space-y-1">
          {sources.map((s, i) => (
            <SourceRow
              key={`${s.kind}-${i}`}
              source={s}
              readOnly={readOnly}
              onRemove={onRemoveSource ? () => onRemoveSource(`${s.kind}-${i}`) : undefined}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function SourceRow({
  source,
  readOnly,
  onRemove,
}: {
  source: CampaignResponse["compound_sources"][number];
  readOnly: boolean;
  onRemove?: () => void;
}) {
  const label = describeSource(source);
  return (
    <li className="flex items-center justify-between rounded-md border bg-card px-3 py-1.5">
      <span className="text-sm">{label}</span>
      {!readOnly && onRemove && (
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onRemove}>
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </li>
  );
}

function describeSource(
  source: CampaignResponse["compound_sources"][number],
): string {
  const count = source.count ?? 0;
  const suffix = count > 0 ? ` · ${count} compounds` : "";
  switch (source.kind) {
    case "run":
      return `Run · ${source.ref?.description ?? source.ref?.run_id ?? "(unknown run)"}${suffix}`;
    case "collection":
      return `Collection · ${source.ref?.description ?? source.ref?.collection_id ?? "(unknown collection)"}${suffix}`;
    case "campaign":
      return `Campaign · ${source.ref?.description ?? source.ref?.campaign_id ?? "(unknown campaign)"}${suffix}`;
    case "manual":
      return `Manual${source.ref?.description ? ` · ${source.ref.description}` : ""}${suffix}`;
    case "saved_search":
      return `Saved search · ${source.ref?.description ?? source.ref?.saved_search_id ?? "(unknown)"}${suffix}`;
    default:
      return `${source.kind}${suffix}`;
  }
}
```

**Note on `onRemoveSource`:** The backend does not currently support removing a source group atomically. For v1, wire `onRemoveSource={undefined}` from the parent (no remove button). Re-evaluate after Phase 4. Surface this in `docs/backlog/screen-campaign-followups.md` after Phase 6.

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS. If `compound_sources` shape differs from the assumed `{kind, ref, count}` shape, adjust the `describeSource` accessor. Verify against the orval-generated type.

- [ ] **Step 3: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/sections/sources-section.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): SourcesSection with readable source rows"
```

---

### Task 2.5: Build the `ChannelsSection` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/sections/channels-section.tsx`
- Modify (extract): `frontend/src/features/screen-campaign/components/channel-popover.tsx` — extract the `ChannelForm` popover from `channel-strip.tsx`

- [ ] **Step 1: Extract the channel form**

Read: `frontend/src/features/screen-campaign/components/channel-strip.tsx` (620 lines).

The `ChannelForm` component inside (around line 107) is the add/edit popover form for a campaign channel. Extract it into a new file `frontend/src/features/screen-campaign/components/channel-popover.tsx`. Keep the old `channel-strip.tsx` re-importing the extracted form (so the old layout still works until Phase 4):

```typescript
// In channel-strip.tsx, replace the inlined ChannelForm with:
import { ChannelPopoverForm } from "./channel-popover";
// then in JSX, use <ChannelPopoverForm ... /> with the same props
```

- [ ] **Step 2: Build `ChannelsSection`**

Create `frontend/src/features/screen-campaign/components/sections/channels-section.tsx`:

```tsx
"use client";

import { useState } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import type { CampaignResponse, CampaignChannelResponse } from "@/shared/lib/api/campaigns.schemas";
import { ChannelPopoverForm } from "../channel-popover";

interface ChannelsSectionProps {
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
}

const SECTION_HEADING =
  "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20";

export function ChannelsSection({ campaign, projectId, readOnly }: ChannelsSectionProps) {
  const [addOpen, setAddOpen] = useState(false);
  const channels = campaign.channels ?? [];
  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Channels</h2>
        {!readOnly && (
          <Popover open={addOpen} onOpenChange={setAddOpen}>
            <PopoverTrigger asChild>
              <button type="button" className={ADD_PILL}>
                <Plus className="h-3 w-3" /> Channel
              </button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-[420px]">
              <ChannelPopoverForm
                campaignId={campaign.id}
                projectId={projectId}
                onClose={() => setAddOpen(false)}
              />
            </PopoverContent>
          </Popover>
        )}
      </div>
      {channels.length === 0 ? (
        <p className="text-sm text-muted-foreground">No channels yet — add via the pill above.</p>
      ) : (
        <ul className="space-y-1">
          {channels.map((c) => (
            <ChannelRow key={c.id} channel={c} campaign={campaign} projectId={projectId} readOnly={readOnly} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ChannelRow({
  channel,
  campaign,
  projectId,
  readOnly,
}: {
  channel: CampaignChannelResponse;
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
}) {
  const [editOpen, setEditOpen] = useState(false);
  const sourceKind = channel.source_kind === "dose_response_curve" ? "DR" : "RD";
  const threshold = channel.hit_threshold
    ? ` · hit if ${channel.hit_threshold.operator} ${channel.hit_threshold.value} ${channel.unit ?? ""}`.trim()
    : "";
  const rule = channel.selection_rule.replace(/_/g, " ");
  return (
    <li className="flex items-center justify-between rounded-md border bg-card px-3 py-1.5">
      <span className="text-sm">
        <span className="font-medium">{channel.label}</span>
        <Badge variant="secondary" className="ml-2 text-[10px]">{sourceKind}</Badge>
        <span className="ml-2 text-muted-foreground">{threshold} · {rule}</span>
      </span>
      {!readOnly && (
        <Popover open={editOpen} onOpenChange={setEditOpen}>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="h-6 w-6">
              <MoreHorizontal className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-[420px]">
            <ChannelPopoverForm
              campaignId={campaign.id}
              projectId={projectId}
              existing={channel}
              onClose={() => setEditOpen(false)}
            />
          </PopoverContent>
        </Popover>
      )}
    </li>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS. (Adjust the `channel.unit` reference if the type uses a different attribute; check `CampaignChannelResponse` from orval.)

- [ ] **Step 4: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/channel-popover.tsx \
  frontend/src/features/screen-campaign/components/channel-strip.tsx \
  frontend/src/features/screen-campaign/components/sections/channels-section.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): ChannelsSection + extracted ChannelPopoverForm"
```

---

### Task 2.6: Build the `CampaignToolbar` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/sections/campaign-toolbar.tsx`

- [ ] **Step 1: Create the toolbar**

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import { Download, Settings2 } from "lucide-react";

interface CampaignToolbarProps {
  resultCount: number;
  onCustomizeReport: () => void;
  onExport?: () => void;
  exportDisabled?: boolean;
}

export function CampaignToolbar({
  resultCount,
  onCustomizeReport,
  onExport,
  exportDisabled,
}: CampaignToolbarProps) {
  return (
    <div className="flex items-center justify-between border-b px-6 py-2">
      <span className="text-sm text-muted-foreground">{resultCount} results</span>
      <div className="flex items-center gap-2">
        {onExport && (
          <Button variant="outline" size="sm" onClick={onExport} disabled={exportDisabled}>
            <Download className="h-4 w-4" />
            Export
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={onCustomizeReport}>
          <Settings2 className="h-4 w-4" />
          Customize Report
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/sections/campaign-toolbar.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): CampaignToolbar component"
```

---

### Task 2.7: Wire the new sections into `CampaignBuilderV2`

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/campaign-builder.tsx`

- [ ] **Step 1: Replace the placeholder `CampaignBuilderV2`**

Replace the stub from Task 2.1 with the wired version. Note: the grid is still a placeholder; Phase 3 will fill it.

```tsx
import { HeaderStrip } from "./sections/header-strip";
import { SourcesSection } from "./sections/sources-section";
import { ChannelsSection } from "./sections/channels-section";
import { CampaignFilterBar } from "./campaign-filter-bar";
import { CampaignToolbar } from "./sections/campaign-toolbar";
import { useState } from "react";
// (re-use the existing `useRefresh`, close-sign, preview hooks from the legacy layout)

function CampaignBuilderV2({
  campaign,
  projectId,
}: {
  campaign: CampaignResponse;
  projectId: string;
}) {
  // Reuse the same mutation hooks as the legacy layout. Copy the imports
  // and inline the same state (refresh button + dialogs) verbatim. Pull
  // them out into a `useCampaignBuilderState(campaignId)` hook if the
  // legacy layout has more than 5 useState/useMutation hooks.
  const [filters, setFilters] = useState({ /* match legacy initial */ });
  const refreshing = false; // wire from refresh mutation
  const onRefresh = () => { /* call refresh mutation */ };
  const [previewOpen, setPreviewOpen] = useState(false);
  const [closeSignOpen, setCloseSignOpen] = useState(false);

  return (
    <div className="flex flex-col">
      <HeaderStrip
        campaign={campaign}
        isDraft={campaign.status === "draft"}
        refreshing={refreshing}
        onRefresh={onRefresh}
        onPreview={() => setPreviewOpen(true)}
        onCloseAndSign={() => setCloseSignOpen(true)}
      />
      <SourcesSection campaign={campaign} projectId={projectId} readOnly={campaign.status !== "draft"} />
      <ChannelsSection campaign={campaign} projectId={projectId} readOnly={campaign.status !== "draft"} />
      <CampaignFilterBar campaign={campaign} filters={filters} onChange={setFilters} />
      <CampaignToolbar
        resultCount={campaign.results?.length ?? 0}
        onCustomizeReport={() => { /* phase 5 */ }}
      />
      <div className="border-t p-8 text-center text-muted-foreground">
        Results grid — Phase 3
      </div>
      {/* Re-mount the existing PreviewAsPublishedDialog and CloseSignDialog here */}
    </div>
  );
}
```

Copy the wiring details (mutations, dialog imports, filter state shape) from the existing `CampaignBuilder` body. The key is: the V2 shell *is* the legacy shell with rearranged children — no new mutations, no new state semantics.

- [ ] **Step 2: Browser smoke**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm dev
```

Navigate to a draft campaign with `?v2=1`. Confirm:
- Header strip renders with name + status + counts + buttons.
- SOURCES section lists each source as a readable row.
- `+Add Run` / `+Collection` / `+Campaign` / `+Manual` open the respective dialogs.
- CHANNELS section lists channels with hit-threshold and selection rule.
- `+Channel` opens the channel form popover.
- Filter chip bar renders (unchanged from legacy).
- Toolbar shows result count + Export + Customize Report (buttons may be no-ops here).
- Below the toolbar: "Results grid — Phase 3" placeholder.

If anything renders broken, fix before committing.

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/campaign-builder.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): wire v2 sections behind ?v2=1"
```

---

## Phase 3 — FE: new grid + DR cell + popover/drawer

Single PR. Builds the campaign-side `DoseResponseCell`, the in-row editors, and the new `ResultsGrid` with row expansion. Still hidden behind `?v2=1`.

### Task 3.1: Pure mapper `measurementToActivity`

**Files:**
- Create: `frontend/src/features/screen-campaign/lib/measurement-to-activity.ts`
- Test: `frontend/src/features/screen-campaign/lib/measurement-to-activity.test.ts`

The pure mapper takes a `CampaignMeasurementResponse` + optional matching `DoseResponseCurveResponse` and returns an `ActivityValue` (the shape consumed by Search's `DoseResponseCell`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/screen-campaign/lib/measurement-to-activity.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { measurementToActivity } from "./measurement-to-activity";

describe("measurementToActivity", () => {
  it("returns null for nd qualifier", () => {
    const m = { value: null, value_qualifier: "nd", unit: "", hit_call: null, source_curve_id: null };
    expect(measurementToActivity(m as any, null)).toBeNull();
  });
  it("returns null for excluded qualifier", () => {
    const m = { value: null, value_qualifier: "excluded", unit: "", hit_call: null, source_curve_id: null };
    expect(measurementToActivity(m as any, null)).toBeNull();
  });
  it("returns readout ActivityValue when source_kind=readout_data", () => {
    const m = { value: 53.4, value_qualifier: "=", unit: "uM", hit_call: "hit", source_curve_id: null };
    const av = measurementToActivity(m as any, null);
    expect(av).toEqual(
      expect.objectContaining({
        value: 53.4,
        qualifier: "=",
        unit: "uM",
        source: "readout",
        raw_data: null,
        curve_params: null,
      }),
    );
  });
  it("returns dose_response ActivityValue when curve is provided", () => {
    const m = {
      value: 2.24, value_qualifier: "=", unit: "uM", hit_call: "miss",
      source_curve_id: "curve-1",
    };
    const curve = {
      id: "curve-1", raw_data: [{ x: 0.1, y: 5 }, { x: 100, y: 95 }],
      top: 100, bottom: 0, hill_slope: 1, fitted_value: 2.24,
      curve_class: "F", r_squared: 0.99, num_points: 2, fit_quality_warnings: [],
    };
    const av = measurementToActivity(m as any, curve as any);
    expect(av).toEqual(
      expect.objectContaining({
        source: "dose_response",
        value: 2.24,
        raw_data: [{ x: 0.1, y: 5 }, { x: 100, y: 95 }],
        curve_params: expect.objectContaining({ top: 100, bottom: 0, hill_slope: 1, curve_class: "F" }),
      }),
    );
  });
  it("falls back to readout shape when source_curve_id is set but curve is missing", () => {
    const m = { value: 100, value_qualifier: "=", unit: "uM", hit_call: "hit", source_curve_id: "curve-missing" };
    const av = measurementToActivity(m as any, null);
    expect(av?.source).toBe("readout");
    expect(av?.value).toBe(100);
    expect(av?.raw_data).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm vitest run src/features/screen-campaign/lib/measurement-to-activity.test.ts
```
Expected: FAIL (import error).

- [ ] **Step 3: Implement the mapper**

Create `frontend/src/features/screen-campaign/lib/measurement-to-activity.ts`:

```typescript
import type { ActivityValue } from "@/features/research-organization/types";
import type {
  CampaignMeasurementResponse,
  DoseResponseCurveResponse,
} from "@/shared/lib/api/campaigns.schemas";

/**
 * Compose an ActivityValue (the shape consumed by Search's DoseResponseCell)
 * from a campaign measurement + its matching dose-response curve. Returns
 * null for `nd` / `excluded` qualifiers (the cell should render "—").
 */
export function measurementToActivity(
  m: CampaignMeasurementResponse,
  curve: DoseResponseCurveResponse | null,
): ActivityValue | null {
  if (m.value_qualifier === "nd" || m.value_qualifier === "excluded") {
    return null;
  }
  if (curve && m.source_curve_id === curve.id) {
    return {
      value: m.value,
      qualifier: m.value_qualifier,
      unit: m.unit,
      source: "dose_response",
      curve_type: curve.curve_type,
      r_squared: curve.r_squared,
      data_point_count: curve.num_points,
      raw_data: curve.raw_data as Array<{ x: number; y: number }> | null,
      curve_params: {
        top: curve.top,
        bottom: curve.bottom,
        hill_slope: curve.hill_slope,
        fitted_value: curve.fitted_value,
        curve_class: curve.curve_class,
        fit_quality_warnings: curve.fit_quality_warnings,
      } as ActivityValue["curve_params"],
    };
  }
  return {
    value: m.value,
    qualifier: m.value_qualifier,
    unit: m.unit,
    source: "readout",
    curve_type: null,
    r_squared: null,
    data_point_count: 0,
    raw_data: null,
    curve_params: null,
  };
}
```

If `ActivityValue["curve_params"]` is more strict than what we construct (e.g. requires more fields), shape the object to match. Reference: `frontend/src/features/research-organization/types/index.ts:362`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm vitest run src/features/screen-campaign/lib/measurement-to-activity.test.ts
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/lib/measurement-to-activity.ts \
  frontend/src/features/screen-campaign/lib/measurement-to-activity.test.ts
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): measurementToActivity pure mapper + tests"
```

---

### Task 3.2: `useCampaignCurves` hook

**Files:**
- Create: `frontend/src/features/screen-campaign/lib/use-campaign-curves.ts`

Fetches all DR curves cited by the campaign's measurements via the new batch endpoint. Returns a `Map<curveId, DoseResponseCurveResponse>`.

- [ ] **Step 1: Create the hook**

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import type { CampaignResponse, DoseResponseCurveResponse } from "@/shared/lib/api/campaigns.schemas";
import { customInstance } from "@/shared/lib/api/custom-instance";

const CAMPAIGN_CURVES_KEY = ["campaign-curves"];

/**
 * Batch-fetch all dose-response curves referenced by a campaign's
 * measurements. Returns a Map keyed by curve id. Empty for campaigns
 * with no DR channels.
 */
export function useCampaignCurves(campaign: CampaignResponse | undefined) {
  const curveIds = collectCurveIds(campaign);
  const sortedKey = [...curveIds].sort().join(",");
  return useQuery({
    queryKey: [...CAMPAIGN_CURVES_KEY, campaign?.id ?? "", sortedKey],
    queryFn: async () => {
      if (curveIds.length === 0) return new Map<string, DoseResponseCurveResponse>();
      const resp = await customInstance<{ curves: DoseResponseCurveResponse[] }>({
        url: "/api/v1/dose-response/curves:batch",
        method: "POST",
        data: { curve_ids: curveIds },
      });
      return new Map(resp.curves.map((c) => [c.id, c] as const));
    },
    enabled: !!campaign,
    staleTime: 60_000, // a campaign's curve set is stable; refresh sparingly
  });
}

function collectCurveIds(campaign: CampaignResponse | undefined): string[] {
  if (!campaign) return [];
  const ids = new Set<string>();
  for (const r of campaign.results ?? []) {
    for (const m of r.measurements ?? []) {
      if (m.source_curve_id) ids.add(m.source_curve_id);
    }
  }
  return [...ids];
}
```

- [ ] **Step 2: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/lib/use-campaign-curves.ts
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): useCampaignCurves hook"
```

---

### Task 3.3: Campaign `DoseResponseCell` wrapper

**Files:**
- Create: `frontend/src/features/screen-campaign/components/grid/dose-response-cell.tsx`

This is a thin wrapper that takes a `CampaignMeasurementResponse` + the curve map, composes the `ActivityValue`, and delegates to the Search `DoseResponseCell` for rendering.

- [ ] **Step 1: Create the wrapper**

```tsx
"use client";

import { memo } from "react";
import type { CampaignMeasurementResponse, DoseResponseCurveResponse } from "@/shared/lib/api/campaigns.schemas";
import { DoseResponseCell as SearchDoseResponseCell } from "@/features/research-organization/components/search/dose-response-cell";
import { measurementToActivity } from "../../lib/measurement-to-activity";

interface CampaignDoseResponseCellProps {
  measurement: CampaignMeasurementResponse | undefined;
  curveMap: Map<string, DoseResponseCurveResponse>;
}

function CampaignDoseResponseCellInner({ measurement, curveMap }: CampaignDoseResponseCellProps) {
  if (!measurement) return <span className="text-muted-foreground">&mdash;</span>;
  const curve = measurement.source_curve_id ? curveMap.get(measurement.source_curve_id) ?? null : null;
  const av = measurementToActivity(measurement, curve);
  if (!av) return <span className="text-muted-foreground">&mdash;</span>;
  return <SearchDoseResponseCell value={av} />;
}

export const CampaignDoseResponseCell = memo(CampaignDoseResponseCellInner);
```

- [ ] **Step 2: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/grid/dose-response-cell.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): CampaignDoseResponseCell wrapping search renderer"
```

---

### Task 3.4: `MeasurementCell` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/grid/measurement-cell.tsx`

Renders the value + qualifier + unit + hit-call chip + `OVR` badge + hover-edit pencil. Triggers the existing `OverrideModal` on edit-click.

- [ ] **Step 1: Inspect the existing override modal trigger**

Read: `frontend/src/features/screen-campaign/components/results-grid.tsx` around line 401 (override-badge code) and the `OverrideModal` import/wiring. The new `MeasurementCell` must reproduce the same trigger.

- [ ] **Step 2: Build the cell**

```tsx
"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import type { CampaignMeasurementResponse } from "@/shared/lib/api/campaigns.schemas";

interface MeasurementCellProps {
  measurement: CampaignMeasurementResponse | undefined;
  readOnly: boolean;
  onEdit: () => void; // opens OverrideModal at the parent
}

function HitChip({ call }: { call: string | null | undefined }) {
  if (!call) return null;
  const cls =
    call === "hit"
      ? "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300"
      : call === "miss"
      ? "border-zinc-500/40 bg-zinc-500/10 text-zinc-600 dark:text-zinc-400"
      : "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  return <span className={`ml-1 rounded-sm border px-1 py-px text-[10px] ${cls}`}>{call}</span>;
}

export function MeasurementCell({ measurement, readOnly, onEdit }: MeasurementCellProps) {
  const [hover, setHover] = useState(false);
  if (!measurement) return <span className="text-muted-foreground">&mdash;</span>;
  const q = measurement.value_qualifier;
  if (q === "nd" || q === "excluded") {
    return <span className="text-muted-foreground italic">{q}</span>;
  }
  const prefix = q === "<" || q === ">" ? `${q} ` : "";
  return (
    <div
      className="flex items-center gap-1"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="text-sm">
        {prefix}
        {measurement.value} {measurement.unit}
      </span>
      <HitChip call={measurement.hit_call} />
      {measurement.is_manual_override && (
        <Badge
          variant="outline"
          className="text-[10px]"
          title={measurement.override_reason ?? "Manually overridden"}
        >
          OVR
        </Badge>
      )}
      {!readOnly && hover && (
        <button type="button" onClick={onEdit} className="ml-1 text-muted-foreground hover:text-foreground">
          <Pencil className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/grid/measurement-cell.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): MeasurementCell with hover-edit + OVR badge"
```

---

### Task 3.5: `DecisionPopover` component

**Files:**
- Create: `frontend/src/features/screen-campaign/components/popovers/decision-popover.tsx`

- [ ] **Step 1: Inspect existing decision-panel debounce pattern**

Read: `frontend/src/features/screen-campaign/components/decision-panel.tsx` (289 lines). Note the existing debounce timer (300ms) and the PATCH mutation wiring.

- [ ] **Step 2: Build the popover**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { Button } from "@/shared/components/ui/button";
import { useSetResultDecision } from "../../lib/hooks";
import type { CampaignResultResponse } from "@/shared/lib/api/campaigns.schemas";

type Decision = "selected" | "deferred" | "rejected";

interface DecisionPopoverProps {
  campaignId: string;
  result: CampaignResultResponse;
  onClose: () => void;
}

export function DecisionPopover({ campaignId, result, onClose }: DecisionPopoverProps) {
  const [decision, setDecision] = useState<Decision>((result.decision ?? "deferred") as Decision);
  const [reason, setReason] = useState(result.decision_reason ?? "");
  const [notes, setNotes] = useState(result.notes ?? "");
  const dirty = useRef(false);
  const initial = useRef({
    decision: result.decision ?? "deferred",
    reason: result.decision_reason ?? "",
    notes: result.notes ?? "",
  });

  const isDirty = () =>
    decision !== initial.current.decision ||
    reason !== initial.current.reason ||
    notes !== initial.current.notes;

  const { mutate } = useSetResultDecision(campaignId, result.id);

  // Debounced background save.
  useEffect(() => {
    if (!isDirty()) return;
    dirty.current = true;
    const t = setTimeout(() => {
      mutate({ decision, decision_reason: reason || null, notes: notes || null });
    }, 300);
    return () => clearTimeout(t);
  }, [decision, reason, notes]);

  // Autosave on close if still dirty.
  useEffect(() => {
    return () => {
      if (dirty.current && isDirty()) {
        mutate({ decision, decision_reason: reason || null, notes: notes || null });
      }
    };
  }, []);

  const onSave = () => {
    mutate({ decision, decision_reason: reason || null, notes: notes || null });
    onClose();
  };

  return (
    <div className="space-y-3 p-1">
      <RadioGroup value={decision} onValueChange={(v) => setDecision(v as Decision)}>
        {(["selected", "deferred", "rejected"] as const).map((d) => (
          <div key={d} className="flex items-center gap-2">
            <RadioGroupItem value={d} id={`dec-${d}`} />
            <Label htmlFor={`dec-${d}`} className="capitalize">{d}</Label>
          </div>
        ))}
      </RadioGroup>
      <div>
        <Label htmlFor="dec-reason" className="text-xs">Reason (optional)</Label>
        <Textarea
          id="dec-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          className="text-sm"
        />
      </div>
      <div>
        <Label htmlFor="dec-notes" className="text-xs">Notes</Label>
        <Textarea
          id="dec-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="text-sm"
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button size="sm" onClick={onSave}>Save</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Confirm `useSetResultDecision` exists**

Run: `grep -n "useSetResultDecision\b" frontend/src/features/screen-campaign/lib/hooks.ts`

If it doesn't exist with that exact name, find the equivalent in `lib/hooks.ts` or `lib/api.ts` (orval generated `useSetResultDecisionApiV1...`). If it lacks a friendly named export, add a thin alias to `hooks.ts`:

```typescript
import { useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
export const useSetResultDecision = (campaignId: string, resultId: string) =>
  useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch({
    mutation: { /* invalidate campaign query on success — copy from existing decision-panel pattern */ },
  });
```

Match the exact pattern the existing `DecisionPanel` uses.

- [ ] **Step 4: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/popovers/ \
  frontend/src/features/screen-campaign/lib/hooks.ts
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): DecisionPopover with debounce + autosave-on-close"
```

---

### Task 3.6: `DecisionChipCell` (pinned-right grid cell)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/grid/decision-chip-cell.tsx`

- [ ] **Step 1: Build the cell**

```tsx
"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import type { CampaignResultResponse } from "@/shared/lib/api/campaigns.schemas";
import { DecisionPopover } from "../popovers/decision-popover";

interface DecisionChipCellProps {
  campaignId: string;
  result: CampaignResultResponse;
  readOnly: boolean;
}

const CHIP_CLASS: Record<string, string> = {
  selected: "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300",
  deferred: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  rejected: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
};

export function DecisionChipCell({ campaignId, result, readOnly }: DecisionChipCellProps) {
  const [open, setOpen] = useState(false);
  const dec = (result.decision ?? "deferred") as keyof typeof CHIP_CLASS;
  const chip = (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${CHIP_CLASS[dec]}`}>
      {dec}
      {!readOnly && <ChevronDown className="h-3 w-3" />}
    </span>
  );
  if (readOnly) return chip;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button">{chip}</button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px]">
        <DecisionPopover
          campaignId={campaignId}
          result={result}
          onClose={() => setOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}
```

- [ ] **Step 2: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/grid/decision-chip-cell.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): DecisionChipCell pinned-right cell"
```

---

### Task 3.7: `RowDetailRenderer` (full-width expansion content)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/grid/row-detail-renderer.tsx`

This is the AG-Grid `fullWidthCellRenderer` used when a row is in the expanded state. Renders decision reason, notes, per-channel audit, override history.

- [ ] **Step 1: Build the renderer**

```tsx
"use client";

import type { CampaignResultResponse, CampaignResponse } from "@/shared/lib/api/campaigns.schemas";

interface RowDetailRendererProps {
  // AG-Grid passes the row data via `data`.
  data: { result: CampaignResultResponse; campaign: CampaignResponse };
}

export function RowDetailRenderer({ data }: RowDetailRendererProps) {
  const { result, campaign } = data;
  const channelsById = new Map((campaign.channels ?? []).map((c) => [c.id, c] as const));
  return (
    <div className="border-t bg-muted/30 p-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Decision rationale
          </h3>
          <p className="whitespace-pre-wrap text-sm">{result.decision_reason || <em className="text-muted-foreground">none</em>}</p>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Notes
          </h3>
          <p className="whitespace-pre-wrap text-sm">{result.notes || <em className="text-muted-foreground">none</em>}</p>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Per-channel audit
          </h3>
          <table className="w-full text-xs">
            <thead className="text-muted-foreground">
              <tr><th className="text-left">Channel</th><th className="text-left">Value</th><th className="text-left">[conc]</th><th className="text-left">N</th><th className="text-left">QC</th></tr>
            </thead>
            <tbody>
              {(result.measurements ?? []).map((m) => (
                <tr key={m.id}>
                  <td>{channelsById.get(m.channel_id)?.label ?? m.channel_id}</td>
                  <td>{m.value ?? "—"} {m.unit}</td>
                  <td>{m.test_concentration_value ?? "—"} {m.test_concentration_unit ?? ""}</td>
                  <td>{m.replicate_count ?? "—"}</td>
                  <td>{m.qc_pass === null ? "—" : m.qc_pass ? "pass" : "fail"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
      {(result.measurements ?? []).some((m) => m.is_manual_override) && (
        <section className="mt-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Override history
          </h3>
          <ul className="space-y-1 text-sm">
            {(result.measurements ?? [])
              .filter((m) => m.is_manual_override)
              .map((m) => (
                <li key={m.id}>
                  <strong>{channelsById.get(m.channel_id)?.label ?? m.channel_id}</strong>:{" "}
                  {m.value ?? "—"} {m.unit} —{" "}
                  <em>{m.override_reason ?? "no reason recorded"}</em>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/grid/row-detail-renderer.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): RowDetailRenderer for inline row expansion"
```

---

### Task 3.8: New `ResultsGrid` with column-group architecture + getRowHeight

**Files:**
- Create: `frontend/src/features/screen-campaign/components/grid/results-grid.tsx`

- [ ] **Step 1: Reference existing column patterns**

Open `frontend/src/features/research-organization/components/search/results-grid.tsx` for the column-group + DR-cell pattern (lines 74-327). Open the legacy `frontend/src/features/screen-campaign/components/results-grid.tsx` for `CampaignFilterBar` external-filter wiring (lines ~530).

- [ ] **Step 2: Build the new grid**

```tsx
"use client";

import { useMemo, useState, useCallback } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ColGroupDef } from "ag-grid-community";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { ChevronRight, ChevronDown } from "lucide-react";
import type {
  CampaignResponse,
  CampaignResultResponse,
  CampaignChannelResponse,
} from "@/shared/lib/api/campaigns.schemas";
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { useMoleculesByIds } from "../../lib/hooks";
import { useCampaignCurves } from "../../lib/use-campaign-curves";
import { chemVaultTheme } from "@/shared/components/data-grid/ag-grid-theme";
import { CampaignDoseResponseCell } from "./dose-response-cell";
import { MeasurementCell } from "./measurement-cell";
import { DecisionChipCell } from "./decision-chip-cell";
import { RowDetailRenderer } from "./row-detail-renderer";
import { OverrideModal } from "../override-modal";
import { rowPassesFilters } from "../campaign-filter-bar";

ModuleRegistry.registerModules([AllCommunityModule]);

interface ResultsGridV2Props {
  campaign: CampaignResponse;
  filters: any;            // Same shape as CampaignFilterBar state
  readOnly: boolean;
}

interface RowData {
  result: CampaignResultResponse;
  campaign: CampaignResponse;
  isDetail: boolean;       // True for the synthetic detail row
}

const COLLAPSED_HEIGHT = 60;
const EXPANDED_HEIGHT = 260;

export function ResultsGridV2({ campaign, filters, readOnly }: ResultsGridV2Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [overrideTarget, setOverrideTarget] = useState<
    { result: CampaignResultResponse; channel: CampaignChannelResponse } | null
  >(null);

  const moleculeIds = useMemo(
    () => [...new Set((campaign.results ?? []).map((r) => r.molecule_id))],
    [campaign.results],
  );
  const { data: moleculesPage } = useMoleculesByIds(moleculeIds);
  const moleculesById = useMemo(
    () => new Map((moleculesPage?.items ?? []).map((m) => [m.id, m] as const)),
    [moleculesPage],
  );
  const { data: curveMap = new Map() } = useCampaignCurves(campaign);

  const rowData = useMemo<RowData[]>(() => {
    const rows: RowData[] = [];
    for (const r of campaign.results ?? []) {
      rows.push({ result: r, campaign, isDetail: false });
      if (expanded.has(r.id)) {
        rows.push({ result: r, campaign, isDetail: true });
      }
    }
    return rows;
  }, [campaign, expanded]);

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const columnDefs = useMemo<(ColDef<RowData> | ColGroupDef<RowData>)[]>(() => {
    const channelGroups: ColGroupDef<RowData>[] = (campaign.channels ?? []).map((ch) => ({
      headerName: ch.label,
      children: [
        {
          headerName: ch.label,
          field: `__channel_${ch.id}_value`,
          width: 140,
          cellRenderer: (params: any) => {
            const r = params.data?.result as CampaignResultResponse;
            const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
            return (
              <MeasurementCell
                measurement={m}
                readOnly={readOnly}
                onEdit={() => setOverrideTarget({ result: r, channel: ch })}
              />
            );
          },
        },
        {
          headerName: `${ch.label} Plot`,
          field: `__channel_${ch.id}_plot`,
          width: 240,
          cellRenderer: (params: any) => {
            const r = params.data?.result as CampaignResultResponse;
            const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
            return <CampaignDoseResponseCell measurement={m} curveMap={curveMap} />;
          },
        },
      ],
    }));

    return [
      {
        headerName: "",
        width: 36,
        pinned: "left",
        cellRenderer: (params: any) => {
          const r = params.data?.result as CampaignResultResponse;
          const isOpen = expanded.has(r.id);
          return (
            <button
              type="button"
              className="flex h-full w-full items-center justify-center text-muted-foreground hover:text-foreground"
              onClick={() => toggleExpand(r.id)}
              aria-label={isOpen ? "Collapse row" : "Expand row"}
            >
              {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
          );
        },
      },
      {
        headerName: "Molecule",
        pinned: "left",
        width: 220,
        cellRenderer: (params: any) => {
          const r = params.data?.result as CampaignResultResponse;
          const m = moleculesById.get(r.molecule_id);
          return (
            <div className="flex items-center gap-2">
              <MoleculeThumbnail smiles={m?.smiles ?? null} size="sm" />
              <span className="text-sm">{m?.registration_number ?? r.molecule_id.slice(0, 8)}</span>
            </div>
          );
        },
      },
      ...channelGroups,
      {
        headerName: "Decision",
        pinned: "right",
        width: 160,
        cellRenderer: (params: any) => {
          const r = params.data?.result as CampaignResultResponse;
          return <DecisionChipCell campaignId={campaign.id} result={r} readOnly={readOnly} />;
        },
      },
    ];
  }, [campaign, curveMap, expanded, moleculesById, readOnly, toggleExpand]);

  const getRowHeight = useCallback(
    (params: any) => {
      if (params.data?.isDetail) return EXPANDED_HEIGHT;
      return COLLAPSED_HEIGHT;
    },
    [],
  );

  const isFullWidthRow = useCallback((params: any) => !!params.rowNode.data?.isDetail, []);

  const isExternalFilterPresent = useCallback(() => !!filters && rowPassesFiltersHas(filters), [filters]);
  const doesExternalFilterPass = useCallback(
    (node: any) => {
      const data = node.data as RowData | undefined;
      if (!data || data.isDetail) return true;
      return rowPassesFilters(data.result, filters);
    },
    [filters],
  );

  return (
    <>
      <div style={{ height: 600 }}>
        <AgGridReact<RowData>
          theme={chemVaultTheme}
          rowData={rowData}
          columnDefs={columnDefs}
          getRowHeight={getRowHeight}
          isFullWidthRow={isFullWidthRow}
          fullWidthCellRenderer={RowDetailRenderer}
          isExternalFilterPresent={isExternalFilterPresent}
          doesExternalFilterPass={doesExternalFilterPass}
          suppressRowClickSelection
        />
      </div>
      {overrideTarget && (
        <OverrideModal
          open
          onOpenChange={(v) => !v && setOverrideTarget(null)}
          campaignId={campaign.id}
          result={overrideTarget.result}
          channel={overrideTarget.channel}
        />
      )}
    </>
  );
}

function rowPassesFiltersHas(filters: any): boolean {
  // Re-export from CampaignFilterBar if not already exported.
  // For this task, return true if any filter chip is set; refine after reading
  // the actual shape in `campaign-filter-bar.tsx`.
  return Object.values(filters ?? {}).some((v) => v !== undefined && v !== false && (Array.isArray(v) ? v.length > 0 : true));
}
```

**Important:** the actual `rowPassesFilters` and `filtersActive` helpers already live in `campaign-filter-bar.tsx` — re-import the correct names. The synthetic `rowPassesFiltersHas` above is a placeholder; replace it with the real `filtersActive` export (rename in `campaign-filter-bar.tsx` if needed).

- [ ] **Step 3: Wire `ResultsGridV2` into `CampaignBuilderV2`**

Replace the "Results grid — Phase 3" placeholder in `campaign-builder.tsx` with `<ResultsGridV2 campaign={campaign} filters={filters} readOnly={campaign.status !== "draft"} />`.

- [ ] **Step 4: Browser smoke**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm dev
```

Navigate to a draft campaign with `?v2=1`. Verify:
- Grid renders with pinned Molecule + per-channel pairs (`Value`, `Value Plot`) + pinned Decision.
- DR plot renders inline in each channel-plot cell when source_kind=dose_response_curve.
- Click row chevron → row expands inline with decision rationale + notes + per-channel audit.
- Click decision chip → popover opens; edit decision/reason/notes; close → optimistic update.
- Hover over a measurement cell → pencil appears; click → OverrideModal opens.
- Filter chip bar still filters the grid.

- [ ] **Step 5: TypeScript check + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/grid/results-grid.tsx \
  frontend/src/features/screen-campaign/components/campaign-builder.tsx \
  frontend/src/features/screen-campaign/components/campaign-filter-bar.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): v2 ResultsGrid with inline DR + row expansion"
```

---

## Phase 4 — FE: switch default, delete legacy shell

Single PR.

### Task 4.1: Make V2 the default

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/campaign-builder.tsx`

- [ ] **Step 1: Drop the toggle**

Remove the `useSearchParams` + `useV2` branch added in Task 2.1. `CampaignBuilder` should unconditionally return `<CampaignBuilderV2 ... />` for draft campaigns and dispatch to `<CampaignView />` for closed.

- [ ] **Step 2: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/campaign-builder.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): v2 layout is default"
```

---

### Task 4.2: Migrate `CampaignView` (closed) to the same layout

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/campaign-view/index.tsx`

- [ ] **Step 1: Rewrite using V2 sections in read-only mode**

Replace the existing layout in `campaign-view/index.tsx` with the same component tree as `CampaignBuilderV2`, but pass `readOnly={true}`:

```tsx
return (
  <div className="flex flex-col">
    <HeaderStrip
      campaign={campaign}
      isDraft={false}
      onRefresh={() => {}}        // hidden in non-draft
      onPreview={() => {}}        // hidden in non-draft
      onCloseAndSign={() => {}}   // hidden in non-draft
    />
    <SourcesSection campaign={campaign} projectId={projectId} readOnly={true} />
    <ChannelsSection campaign={campaign} projectId={projectId} readOnly={true} />
    <CampaignFilterBar campaign={campaign} filters={filters} onChange={setFilters} />
    <CampaignToolbar
      resultCount={campaign.results?.length ?? 0}
      onCustomizeReport={onCustomize}
      onExport={onExportPublishedJson}
    />
    <ResultsGridV2 campaign={campaign} filters={filters} readOnly={true} />
    {/* Keep the existing SupersedeDialog mount */}
  </div>
);
```

Preserve the existing supersede-dialog wiring and the closed-campaign signature/closed_by/closed_at display: surface those in `HeaderStrip` by passing additional props (extend `HeaderStripProps` with optional `closedAt`, `closedBy`, `signatureId`, and render a subtle muted line when `isDraft===false`).

- [ ] **Step 2: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/campaign-view/index.tsx \
  frontend/src/features/screen-campaign/components/sections/header-strip.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): closed view uses same layout, read-only"
```

---

### Task 4.3: Delete the legacy shell

**Files:**
- Delete: `frontend/src/features/screen-campaign/components/compound-list-pane.tsx`
- Delete: `frontend/src/features/screen-campaign/components/sources-summary-card.tsx`
- Delete: `frontend/src/features/screen-campaign/components/decision-panel.tsx`
- Delete: `frontend/src/features/screen-campaign/components/channel-strip.tsx`
- Delete: `frontend/src/features/screen-campaign/components/results-grid.tsx` (the legacy one; the V2 is under `components/grid/`)

- [ ] **Step 1: Confirm no remaining imports**

```bash
cd /Users/sidx/workspace/cellar2/frontend
grep -rn "compound-list-pane\|sources-summary-card\|decision-panel\|channel-strip\|features/screen-campaign/components/results-grid" src/ 2>/dev/null
```
Expected: empty (no callers).

- [ ] **Step 2: Delete the files**

```bash
cd /Users/sidx/workspace/cellar2
rm frontend/src/features/screen-campaign/components/compound-list-pane.tsx \
   frontend/src/features/screen-campaign/components/sources-summary-card.tsx \
   frontend/src/features/screen-campaign/components/decision-panel.tsx \
   frontend/src/features/screen-campaign/components/channel-strip.tsx \
   frontend/src/features/screen-campaign/components/results-grid.tsx
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
```
Expected: PASS. If any test file imports a deleted module, update or delete the test as appropriate. Run `pnpm vitest run` if unit tests exist for this feature.

- [ ] **Step 4: Update CLAUDE.md handoff**

Read `/Users/sidx/workspace/cellar2/CLAUDE.md` (the "Current Session Notes" section). Add a new dated block at the top describing the redesign work shipped on `fe2`. Force-add and stage.

- [ ] **Step 5: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add -A frontend/src/features/screen-campaign/ CLAUDE.md
git -C /Users/sidx/workspace/cellar2 commit -m "refactor(fe/campaign): delete legacy 3-pane shell"
```

---

## Phase 5 — FE: customize-report sheet + project-scoped pickers

Single PR. Adds the customize-report sheet and fixes the three add-dialog pickers to scope by `projectId`.

### Task 5.1: `useReportConfig` Zustand store (campaign-scoped)

**Files:**
- Create: `frontend/src/features/screen-campaign/lib/report-config.ts`

- [ ] **Step 1: Create the store**

```typescript
"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface CampaignReportConfig {
  imageSize: "small" | "medium" | "large";
  showProperties: { mw: boolean; logP: boolean; hbd: boolean; hba: boolean; tpsa: boolean };
  showDecisionReasonColumn: boolean;
  showNotesColumn: boolean;
  showOverrideStatusColumn: boolean;
}

const DEFAULTS: CampaignReportConfig = {
  imageSize: "small",
  showProperties: { mw: false, logP: false, hbd: false, hba: false, tpsa: false },
  showDecisionReasonColumn: false,
  showNotesColumn: false,
  showOverrideStatusColumn: false,
};

interface Store {
  byCampaign: Record<string, CampaignReportConfig>;
  get: (campaignId: string) => CampaignReportConfig;
  set: (campaignId: string, patch: Partial<CampaignReportConfig>) => void;
  reset: (campaignId: string) => void;
}

export const useReportConfig = create<Store>()(
  persist(
    (set, get) => ({
      byCampaign: {},
      get: (campaignId: string) => get().byCampaign[campaignId] ?? DEFAULTS,
      set: (campaignId, patch) =>
        set((s) => ({
          byCampaign: {
            ...s.byCampaign,
            [campaignId]: { ...(s.byCampaign[campaignId] ?? DEFAULTS), ...patch },
          },
        })),
      reset: (campaignId) =>
        set((s) => {
          const { [campaignId]: _, ...rest } = s.byCampaign;
          return { byCampaign: rest };
        }),
    }),
    {
      name: "campaign-report-config",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
```

- [ ] **Step 2: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/lib/report-config.ts
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): per-campaign useReportConfig Zustand store"
```

---

### Task 5.2: `CampaignReportSheet` (right-side 420px)

**Files:**
- Create: `frontend/src/features/screen-campaign/components/sections/campaign-report-sheet.tsx`

- [ ] **Step 1: Build the sheet**

```tsx
"use client";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { Button } from "@/shared/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { useReportConfig, type CampaignReportConfig } from "../../lib/report-config";

interface CampaignReportSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
}

export function CampaignReportSheet({ open, onOpenChange, campaignId }: CampaignReportSheetProps) {
  const cfg = useReportConfig((s) => s.get(campaignId));
  const setCfg = useReportConfig((s) => s.set);
  const reset = useReportConfig((s) => s.reset);
  const patch = (p: Partial<CampaignReportConfig>) => setCfg(campaignId, p);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[420px]">
        <SheetHeader>
          <SheetTitle>Customize report</SheetTitle>
        </SheetHeader>
        <div className="space-y-6 py-6">
          <section>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Properties
            </h3>
            {(["mw", "logP", "hbd", "hba", "tpsa"] as const).map((k) => (
              <div key={k} className="flex items-center justify-between py-1">
                <Label className="capitalize">{k}</Label>
                <Switch
                  checked={cfg.showProperties[k]}
                  onCheckedChange={(v) =>
                    patch({ showProperties: { ...cfg.showProperties, [k]: v } })
                  }
                />
              </div>
            ))}
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Image size
            </h3>
            <RadioGroup
              value={cfg.imageSize}
              onValueChange={(v) => patch({ imageSize: v as CampaignReportConfig["imageSize"] })}
            >
              {(["small", "medium", "large"] as const).map((s) => (
                <div key={s} className="flex items-center gap-2">
                  <RadioGroupItem value={s} id={`size-${s}`} />
                  <Label htmlFor={`size-${s}`} className="capitalize">{s}</Label>
                </div>
              ))}
            </RadioGroup>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Columns
            </h3>
            <Row label="Decision reason" v={cfg.showDecisionReasonColumn} on={(v) => patch({ showDecisionReasonColumn: v })} />
            <Row label="Notes" v={cfg.showNotesColumn} on={(v) => patch({ showNotesColumn: v })} />
            <Row label="Override status" v={cfg.showOverrideStatusColumn} on={(v) => patch({ showOverrideStatusColumn: v })} />
          </section>
          <Button variant="ghost" size="sm" onClick={() => reset(campaignId)}>
            Reset to defaults
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Row({ label, v, on }: { label: string; v: boolean; on: (b: boolean) => void }) {
  return (
    <div className="flex items-center justify-between py-1">
      <Label>{label}</Label>
      <Switch checked={v} onCheckedChange={on} />
    </div>
  );
}
```

- [ ] **Step 2: Wire the sheet from `CampaignToolbar`**

In `CampaignBuilderV2` (and the closed `CampaignView`), add state for the sheet and pass it to the toolbar:

```typescript
const [reportOpen, setReportOpen] = useState(false);
// in JSX:
<CampaignToolbar resultCount={...} onCustomizeReport={() => setReportOpen(true)} />
<CampaignReportSheet open={reportOpen} onOpenChange={setReportOpen} campaignId={campaign.id} />
```

- [ ] **Step 3: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/sections/campaign-report-sheet.tsx \
  frontend/src/features/screen-campaign/components/campaign-builder.tsx \
  frontend/src/features/screen-campaign/components/campaign-view/index.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): CampaignReportSheet wired to the toolbar"
```

---

### Task 5.3: Apply report config to the grid

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/grid/results-grid.tsx`

- [ ] **Step 1: Read the config in `ResultsGridV2` and gate columns**

```typescript
import { useReportConfig } from "../../lib/report-config";
// inside ResultsGridV2:
const cfg = useReportConfig((s) => s.get(campaign.id));
```

Then in `columnDefs`, after the `Molecule` column, conditionally insert property columns based on `cfg.showProperties`. Each property column reads from `moleculesById?.get(r.molecule_id)?.properties?.<key>` (verify the exact property location against the molecule type):

```typescript
const propertyColumns: ColDef<RowData>[] = [];
if (cfg.showProperties.mw) propertyColumns.push({ headerName: "MW", width: 80, valueGetter: (p) => moleculesById.get(p.data!.result.molecule_id)?.properties?.mw });
if (cfg.showProperties.logP) propertyColumns.push({ headerName: "LogP", width: 80, valueGetter: (p) => moleculesById.get(p.data!.result.molecule_id)?.properties?.logp });
// ...etc
```

Then after the channel groups, insert optional Decision Reason / Notes / Override-Status columns when `cfg.showXxxColumn` is true. These read from `result.decision_reason`, `result.notes`, and `result.measurements?.some((m) => m.is_manual_override)` respectively. Place them between channels and the pinned Decision column.

For image size, gate `MoleculeThumbnail size` on `cfg.imageSize`.

- [ ] **Step 2: Browser smoke**

In dev, open the sheet, toggle MW + LogP + Decision Reason + image size. Verify columns appear and image size changes with no layout glitches.

- [ ] **Step 3: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/grid/results-grid.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): apply report config (properties + columns + image size)"
```

---

### Task 5.4: Project-scope `AddFromCollectionDialog`

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/add-from-collection-dialog.tsx`

- [ ] **Step 1: Pass `projectId` to `useCollections`**

In `add-from-collection-dialog.tsx`, change:

```typescript
const { data: collections, isLoading: collectionsLoading } = useCollections();
```

to:

```typescript
const { data: collections, isLoading: collectionsLoading } = useCollections([projectId]);
```

`projectId` is the new prop added in Task 2.3.

- [ ] **Step 2: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/add-from-collection-dialog.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): project-scope AddFromCollectionDialog picker"
```

---

### Task 5.5: Project-scope `AddFromCampaignDialog`

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/add-from-campaign-dialog.tsx`

- [ ] **Step 1: Switch to `useCampaignsByProject`**

In `add-from-campaign-dialog.tsx`, replace whatever workspace-wide campaigns query exists with:

```typescript
import { useCampaignsByProject } from "../lib/hooks";
// ...
const { data: campaigns = [] } = useCampaignsByProject(projectId);
// Filter out the current campaign so users don't pick their own:
const pickable = campaigns.filter((c) => c.id !== currentCampaignId);
```

- [ ] **Step 2: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/add-from-campaign-dialog.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): project-scope AddFromCampaignDialog picker"
```

---

### Task 5.6: Project-scope `AddFromRunsDialog`

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/add-from-runs-dialog.tsx`

- [ ] **Step 1: Switch the protocol picker**

In `add-from-runs-dialog.tsx`, replace:

```typescript
import { useListProtocolsApiV1ProtocolsGet } from "@/shared/lib/api/protocols/protocols";
// ...
const { data: protocolsResp } = useListProtocolsApiV1ProtocolsGet();
const protocols = protocolsResp ?? [];
```

with:

```typescript
import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
// ...
const { data: protocols = [] } = useProtocolSummaries([projectId]);
```

If `useProtocolSummaries` returns a different shape than the inline render expects, adapt the renderer or convert at the boundary (don't loosen types).

- [ ] **Step 2: TypeScript + commit**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm tsc --noEmit
git -C /Users/sidx/workspace/cellar2 add frontend/src/features/screen-campaign/components/add-from-runs-dialog.tsx
git -C /Users/sidx/workspace/cellar2 commit -m "feat(fe/campaign): project-scope AddFromRunsDialog protocol picker"
```

---

### Task 5.7: Browser smoke pass

- [ ] **Step 1: Manual smoke checklist (from spec §9.2)**

Run dev server: `cd frontend && pnpm dev`. Walk through:

1. Create a draft campaign in a project, add a channel via `+Add Channel` (verify the protocol dropdown only shows project protocols).
2. Add compounds via `+Add Run` (verify the protocol dropdown only shows project protocols).
3. Verify DR plots render inline.
4. Set decisions via the chip popover (selected + reason + notes). Confirm chip re-colors and tally updates.
5. Expand a row via chevron → drawer shows audit fields.
6. Hover a measurement cell → pencil appears → override modal → set value + reason → `OVR` badge appears.
7. Open Customize Report → toggle MW + Decision Reason → columns appear.
8. Click filter chips → grid filters live.
9. `+Add Collection` → verify only project collections are listed.
10. `+Add Campaign` → verify only project campaigns are listed (and current campaign is excluded).
11. Close & Sign → verify closed view uses same layout, mutation controls hidden.
12. Open Preview-as-published → JSON matches expected shape.

- [ ] **Step 2: Final commit (no source change)**

If anything was tweaked during smoke, commit the fixes. Otherwise no commit needed for this step.

---

## Phase 6 — Playwright happy-path smoke

Single PR. Configure Playwright and land the end-to-end test.

### Task 6.1: Install + configure Playwright

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/e2e/setup/global-setup.ts`

- [ ] **Step 1: Install**

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm add -D @playwright/test
pnpm exec playwright install --with-deps chromium
```

- [ ] **Step 2: Add a config**

Create `frontend/playwright.config.ts`:

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,           // backend seed shared across tests
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
```

- [ ] **Step 3: Add scripts**

In `frontend/package.json`, add:

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
  }
}
```

- [ ] **Step 4: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/package.json frontend/pnpm-lock.yaml frontend/playwright.config.ts
git -C /Users/sidx/workspace/cellar2 commit -m "chore(fe): install + configure Playwright"
```

---

### Task 6.2: Seed fixture helper

**Files:**
- Create: `frontend/tests/e2e/setup/seed.ts`

- [ ] **Step 1: Build a seed helper**

The helper logs in via the dev-mode auth path (see `reference_dev_api_access.md` memory: two-token auth, mint authz via Sentinel `/authz/resolve`) and creates:
- 1 project
- 1 protocol with a DR readout
- 1 approved run with 5 compounds × DR curves
- An empty draft campaign in that project

```typescript
import { request, APIRequestContext } from "@playwright/test";

interface SeedResult {
  projectId: string;
  protocolId: string;
  runId: string;
  campaignId: string;
  moleculeIds: string[];
}

export async function seedCampaignFixture(api: APIRequestContext): Promise<SeedResult> {
  // 1. Create project
  const proj = await api.post("/api/v1/projects", { data: { name: `e2e-${Date.now()}` } });
  const projectId = (await proj.json()).id;

  // 2. Create protocol with DR readout
  // (copy the exact payload from an existing integration test that seeds a DR protocol;
  //  search backend/tests/integration for "ReadoutDefinition" + "dose_response_config")

  // 3. Approve a run with 5 compounds (seed ReadoutData + DoseResponseCurve)

  // 4. Create a draft campaign
  // POST /api/v1/campaigns { project_id, name, publishes_collection: false }

  return { projectId, protocolId, runId, campaignId, moleculeIds };
}
```

The exact payloads must match the backend integration-test fixtures. Cross-reference `backend/tests/integration/` for an existing fixture that creates this exact shape.

- [ ] **Step 2: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/tests/e2e/setup/seed.ts
git -C /Users/sidx/workspace/cellar2 commit -m "test(fe/e2e): seed helper for campaign fixtures"
```

---

### Task 6.3: Happy-path spec

**Files:**
- Rename: `frontend/tests/e2e/screen-campaign.spec.ts.TODO` → `frontend/tests/e2e/screen-campaign.spec.ts`
- Modify: contents of that file

- [ ] **Step 1: Replace the file content**

```typescript
import { test, expect, request } from "@playwright/test";
import { seedCampaignFixture } from "./setup/seed";

test.describe("Screen Campaign — happy path", () => {
  test("create campaign, add from runs, set decision, close & sign", async ({ page, baseURL }) => {
    const api = await request.newContext({ baseURL });
    const { projectId, protocolId, runId, campaignId } = await seedCampaignFixture(api);

    await page.goto(`/projects/${projectId}/campaigns/${campaignId}`);

    // 1. Add a channel via the +Channel pill
    await page.getByRole("button", { name: /\+ Channel/ }).click();
    await page.getByLabel(/protocol/i).selectOption(protocolId);
    // ...select first readout, set hit threshold, submit
    await page.getByRole("button", { name: /save/i }).click();

    // 2. Add from runs via +Add Run pill
    await page.getByRole("button", { name: /^\+ Run$/ }).click();
    await page.getByLabel(/protocol/i).selectOption(protocolId);
    await page.getByLabel(new RegExp(runId.slice(0, 8))).check();
    await page.getByRole("button", { name: /preview/i }).click();
    await page.getByRole("button", { name: /commit/i }).click();

    // 3. Verify DR plots rendered in grid (Plotly produces <svg> nodes)
    await expect(page.locator(".ag-row >> svg")).toHaveCount(5, { timeout: 5000 });

    // 4. Set decision on first row → Selected
    await page.locator(".ag-row").first().getByText(/deferred/i).click();
    await page.getByLabel(/selected/i).check();
    await page.getByLabel(/reason/i).fill("Good IC50, clean assay");
    await page.getByRole("button", { name: /save/i }).click();

    // 5. Close & Sign
    await page.getByRole("button", { name: /close & sign/i }).click();
    await page.getByRole("button", { name: /confirm/i }).click();
    await expect(page.getByText(/closed/i).first()).toBeVisible({ timeout: 5000 });
  });
});
```

The selectors above are illustrative; tighten them against the actual rendered DOM during a first pass with `pnpm test:e2e:ui`.

- [ ] **Step 2: Run the test**

Start the backend + frontend (or point `PLAYWRIGHT_BASE_URL` at a running dev server), then:

```bash
cd /Users/sidx/workspace/cellar2/frontend
pnpm test:e2e
```

Iterate on selectors until it passes. Expected: 1 test PASS.

- [ ] **Step 3: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add frontend/tests/e2e/screen-campaign.spec.ts
git -C /Users/sidx/workspace/cellar2 rm frontend/tests/e2e/screen-campaign.spec.ts.TODO
git -C /Users/sidx/workspace/cellar2 commit -m "test(fe/e2e): screen campaign happy-path Playwright spec"
```

---

### Task 6.4: Wire Playwright into CI

**Files:**
- Modify: existing GitHub Actions workflow under `.github/workflows/`

- [ ] **Step 1: Find the existing FE workflow**

```bash
ls /Users/sidx/workspace/cellar2/.github/workflows/
```

- [ ] **Step 2: Add a Playwright job**

Add a job that:
- Spins up the backend (docker-compose.dev.yml is the project's convention)
- Runs the frontend dev server
- Executes `pnpm test:e2e`

Follow the patterns already in use in the existing FE/BE workflows. If no FE workflow exists today, add a new one in a *separate* PR after Phase 6 lands locally; the spec doesn't require CI for the redesign to ship.

- [ ] **Step 3: Commit**

```bash
git -C /Users/sidx/workspace/cellar2 add .github/workflows/
git -C /Users/sidx/workspace/cellar2 commit -m "ci: run Playwright E2E on PRs"
```

---

## Verification

After each phase:
- `pnpm tsc --noEmit` (FE)
- `cd backend && uv run pytest -x -q` (BE phases only)
- Manual browser smoke per the relevant spec section

At the end of Phase 6:
- Full backend suite: `cd backend && uv run pytest -q`
- Full FE typecheck + Playwright: `cd frontend && pnpm tsc --noEmit && pnpm test:e2e`

---

## Notes for the implementer

- **Branch is `fe2`** — do not branch off main.
- **`docs/` is gitignored** — every spec/plan commit needs `git add -f`.
- **Never run `--no-verify`** — fix hook failures, don't bypass.
- **Reuse existing patterns** — for every new component, point to an analogous existing component first. Don't invent new patterns for layout, theming, or query keys.
- **Don't add unrelated cleanup** — fix what's in scope; leave the rest.
- **Project-scoped pickers are mandatory** — the user explicitly called this out. Phase 5 wiring is non-negotiable.
- **Spec is the source of truth** — if anything in this plan disagrees with the spec, fix the plan or escalate.
