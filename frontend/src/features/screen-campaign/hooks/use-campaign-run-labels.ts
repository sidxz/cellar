/**
 * How the campaign page names a run: its protocol (in the protocol's colour)
 * and "Run on Nov 12, 2026", the way the add-from-runs list shows it — never
 * its id as the name unless the run can't be found. A secondary detail (the
 * time it was created and a short id) tells same-day runs apart.
 *
 * Runs come from each protocol's run list (the same query the add-from-runs
 * dialog makes, so it is usually cached); the measurement snapshots fill in
 * while those load.
 */

import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";

import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { TEST_CONCENTRATION } from "@/features/screening-assay/lib/test-concentration";
import type { RunResponse } from "@/shared/lib/api/model";
import { getListRunsByProtocolApiV1ProtocolsProtocolIdRunsGetQueryOptions } from "@/shared/lib/api/runs/runs";
import { formatDate } from "@/shared/lib/format-date";
import { shortId } from "@/shared/lib/utils";
import { protocolColorById } from "../lib/protocol-colors";
import type { CampaignResponse } from "../types";

export interface RunLabel {
  protocolName: string;
  /** The protocol's hue on the grid's columns and readout chips. */
  color?: string;
  /** "Run on Nov 12, 2026". */
  text: string;
  /** "created 14:32 · 3f2a9c1b": tells same-day runs apart (secondary text). */
  detail: string;
  /** The run's Test concentration as recorded ("10 µM"), when it has one. */
  concentration?: string;
  /** How many compounds the run measured, when known. */
  compoundCount?: number;
}

const timeOfDay = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

const runsById = (results: { data?: RunResponse[] }[]) =>
  new Map(results.flatMap((r) => r.data ?? []).map((run) => [run.id, run] as const));

export function useCampaignRunLabels(campaign: CampaignResponse): (runId: string) => RunLabel {
  const protocolIds = useMemo(
    () => [
      ...new Set([
        ...(campaign.seed_runs ?? []).map((r) => r.protocol_id),
        ...(campaign.channels ?? []).map((c) => c.protocol_id),
      ]),
    ],
    [campaign.seed_runs, campaign.channels],
  );
  const runs = useQueries({
    queries: protocolIds.map((id) =>
      getListRunsByProtocolApiV1ProtocolsProtocolIdRunsGetQueryOptions(id),
    ),
    combine: runsById,
  });
  const { data: protocols } = useProtocolSummaries(undefined, { includeAll: true });

  // Snapshot fallback: run → (protocol, date) from any measurement it sourced.
  const snapshots = useMemo(() => {
    const protocolByChannel = new Map((campaign.channels ?? []).map((c) => [c.id, c.protocol_id]));
    const map = new Map<string, { protocolId?: string; date?: string | null }>();
    for (const r of campaign.results ?? []) {
      for (const m of r.measurements ?? []) {
        if (m.source_run_id && !map.has(m.source_run_id)) {
          map.set(m.source_run_id, {
            protocolId: protocolByChannel.get(m.channel_id),
            date: m.run_date_snapshot,
          });
        }
      }
    }
    for (const s of campaign.seed_runs ?? []) {
      map.set(s.run_id, { ...map.get(s.run_id), protocolId: s.protocol_id });
    }
    return map;
  }, [campaign.results, campaign.channels, campaign.seed_runs]);

  const protocolNames = useMemo(
    () => new Map((protocols ?? []).map((p) => [p.id, p.name] as const)),
    [protocols],
  );
  const colors = useMemo(() => protocolColorById(campaign.channels ?? []), [campaign.channels]);

  return (runId) => {
    const run = runs.get(runId);
    const snap = snapshots.get(runId);
    const protocolId = run?.protocol_id ?? snap?.protocolId;
    const date = run?.run_date ?? snap?.date;
    const concentration = run?.conditions?.[TEST_CONCENTRATION];
    return {
      concentration:
        concentration != null && String(concentration).trim() !== ""
          ? String(concentration).trim()
          : undefined,
      compoundCount: run?.molecule_count,
      protocolName: (protocolId && protocolNames.get(protocolId)) || "Protocol",
      color: protocolId ? colors.get(protocolId) : undefined,
      text: date ? `Run on ${formatDate(date)}` : `Run ${shortId(runId)}`,
      detail: [
        run?.created_at && `created ${timeOfDay.format(new Date(run.created_at))}`,
        date && shortId(runId),
      ]
        .filter(Boolean)
        .join(" · "),
    };
  };
}
