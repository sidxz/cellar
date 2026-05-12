"use client";

import { useMemo } from "react";
import { X } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import type { CampaignResponse } from "../../types";
import { AddCompoundsPills } from "../add/add-compounds-pills";

// ── Local type ────────────────────────────────────────────────────────────────
// The orval-generated `CampaignResponseCompoundSourcesItem` is typed as
// `{ [key: string]: unknown }` because the backend returns a discriminated
// union that orval couldn't narrow. The runtime shape (confirmed in
// sources-summary-card.tsx) is:
//   { kind: string; collection_id?: string; campaign_id?: string;
//     run_id?: string; description?: string | null; count: number }
type SourceEntry = {
  kind: string;
  collection_id?: string;
  campaign_id?: string;
  run_id?: string;
  saved_search_id?: string;
  description?: string | null;
  count?: number;
  /** Backend resolves the bench scientist for run-kind entries by looking
   *  up the run's "Scientist" readout at response time. */
  scientist?: string | null;
};

// ── Props ─────────────────────────────────────────────────────────────────────

interface SourcesSectionProps {
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
  /** Not wired to any backend operation today — pass `undefined`. The × button
   *  stays hidden when this prop is absent. */
  onRemoveSource?: (source: SourceEntry) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const SECTION_HEADING =
  "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

/** Cached per-run label info derived from the measurement snapshots so the
 *  UI doesn't need an extra round-trip to /runs/{id} just to render a row. */
interface RunInfo {
  protocol_name?: string;
  run_date?: string;
}

/** Short human-readable label for a source entry.
 *
 * Uses `description` when the server supplies one; for run-sourced entries
 * additionally falls back to the protocol-name + run-date snapshot we get
 * from any measurement attributed to that run. Final fallback is the first
 * 8 chars of the relevant ID. Count is appended when present.
 *
 * Examples produced:
 *   "Run · NadD-Sumo dose response · 2026-05-07 · 31 compounds"
 *   "Run · 3f8a1b9c · 31 compounds"          (no snapshot available)
 *   "Collection · Primary hits Q1 · 12 compounds"
 *   "Campaign · fc3a291d · 7 compounds"
 *   "Manual · 5 compounds"
 *   "Saved search · 0 compounds"
 */
function describeSource(
  source: SourceEntry,
  runInfoById: Map<string, RunInfo>,
): string {
  const countPart =
    source.count !== undefined
      ? `${source.count} ${source.count === 1 ? "compound" : "compounds"}`
      : null;

  const parts: string[] = [];

  switch (source.kind) {
    case "manual":
      parts.push("Manual");
      break;

    case "collection": {
      parts.push("Collection");
      const collectionLabel =
        source.description?.trim() ||
        (source.collection_id ? source.collection_id.slice(0, 8) : null);
      if (collectionLabel) parts.push(collectionLabel);
      break;
    }

    case "campaign": {
      parts.push("Campaign");
      const campaignLabel =
        source.description?.trim() ||
        (source.campaign_id ? source.campaign_id.slice(0, 8) : null);
      if (campaignLabel) parts.push(campaignLabel);
      break;
    }

    case "run": {
      parts.push("Run");
      const info = source.run_id ? runInfoById.get(source.run_id) : undefined;
      // Prefer protocol_name + run_date snapshot — much more useful than a
      // bare UUID when a campaign mixes runs from several protocols.
      const snapshotLabel =
        info?.protocol_name || info?.run_date
          ? [info?.protocol_name, info?.run_date].filter(Boolean).join(" · ")
          : null;
      const runLabel =
        source.description?.trim() ||
        snapshotLabel ||
        (source.run_id ? source.run_id.slice(0, 8) : null);
      if (runLabel) parts.push(runLabel);
      const scientist = source.scientist?.trim();
      if (scientist) parts.push(`by ${scientist}`);
      break;
    }

    case "saved_search": {
      parts.push("Saved search");
      const label =
        source.description?.trim() ||
        (source.saved_search_id ? source.saved_search_id.slice(0, 8) : null);
      if (label) parts.push(label);
      break;
    }

    default: {
      // Unknown future kind — show it verbatim so it's debuggable.
      parts.push(source.kind);
      const fallbackId =
        source.description?.trim() ||
        source.collection_id?.slice(0, 8) ||
        source.campaign_id?.slice(0, 8) ||
        source.run_id?.slice(0, 8) ||
        null;
      if (fallbackId) parts.push(fallbackId);
      break;
    }
  }

  if (countPart) parts.push(countPart);

  return parts.join(" · ");
}

// ── Main component ────────────────────────────────────────────────────────────

export function SourcesSection({
  campaign,
  projectId,
  readOnly,
  onRemoveSource,
}: SourcesSectionProps) {
  const sources = (campaign.compound_sources ?? []) as SourceEntry[];

  // Build a run_id → {protocol_name, run_date} map from the per-measurement
  // snapshots. We pick the first non-empty snapshot seen for each run_id —
  // every measurement attributed to that run carries the same snapshot at
  // import time, so order doesn't matter.
  const runInfoById = useMemo(() => {
    const map = new Map<string, RunInfo>();
    for (const r of campaign.results ?? []) {
      for (const m of r.measurements ?? []) {
        const rid = m.source_run_id ?? undefined;
        if (!rid || map.has(rid)) continue;
        map.set(rid, {
          protocol_name: m.protocol_name_snapshot || undefined,
          run_date: m.run_date_snapshot || undefined,
        });
      }
    }
    return map;
  }, [campaign.results]);

  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Sources</h2>
        {!readOnly && (
          <AddCompoundsPills campaign={campaign} projectId={projectId} />
        )}
      </div>

      {sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {readOnly
            ? "No compounds were added to this campaign."
            : "No compounds yet — add via the pills above."}
        </p>
      ) : (
        <ul className="space-y-1">
          {sources.map((s, i) => {
            const key = `${s.kind}-${i}`;
            return (
              <SourceRow
                key={key}
                source={s}
                runInfoById={runInfoById}
                readOnly={readOnly}
                onRemove={
                  onRemoveSource ? () => onRemoveSource(s) : undefined
                }
              />
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ── SourceRow ─────────────────────────────────────────────────────────────────

function SourceRow({
  source,
  runInfoById,
  readOnly,
  onRemove,
}: {
  source: SourceEntry;
  runInfoById: Map<string, RunInfo>;
  readOnly: boolean;
  onRemove?: () => void;
}) {
  const label = describeSource(source, runInfoById);

  return (
    <li className="flex items-center justify-between rounded-md border bg-card px-3 py-1.5">
      <span className="text-sm">{label}</span>
      {!readOnly && onRemove && (
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={onRemove}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </li>
  );
}
