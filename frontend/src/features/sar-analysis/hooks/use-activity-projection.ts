import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import { aggregationModeToWire } from "@/features/research-organization/lib/use-aggregation-mode";
import { useJobPoll } from "@/shared/hooks/use-job-poll";
import type { ActivityProjectionResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import type { SarColorSpec } from "../lib/sar-color-spec";

export type ActivityChannel = {
  column: string;
  source: "dr_curve" | "readout_data";
  intercept_key: { kind: string; level: number } | null;
  selection_rule: string;
  protocol_id: string;
  label: string;
};

/** SarColorSpec + aggregation mode → the server `ActivityChannelRequest`. */
export function channelFromColorSpec(
  spec: SarColorSpec,
  aggMode: AggregationMode,
): ActivityChannel {
  return {
    column: spec.column,
    source: spec.source,
    intercept_key: spec.interceptKey
      ? { kind: spec.interceptKey.kind, level: spec.interceptKey.level }
      : null,
    selection_rule: aggregationModeToWire(aggMode) as unknown as string,
    protocol_id: spec.protocolId,
    label: spec.label,
  };
}

type StartInput = { collection_id?: string; molecule_ids?: string[]; channel: ActivityChannel };

export type UseActivityProjectionParams = {
  collectionId?: string;
  moleculeIds?: string[];
  channel: ActivityChannel | null;
  startFn?: (input: StartInput) => Promise<ActivityProjectionResponse>;
  pollFn?: (id: string) => Promise<ActivityProjectionResponse>;
  pollIntervalMs?: number;
  enabled?: boolean;
};

export type UseActivityProjectionReturn = {
  projectionId: string | null;
  status: string | null;
  isStarting: boolean;
  isPolling: boolean;
  error: Error | null;
};

const DEFAULT_POLL_MS = 1500;

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

export function useActivityProjection(
  params: UseActivityProjectionParams,
): UseActivityProjectionReturn {
  const {
    collectionId,
    moleculeIds,
    channel,
    startFn = defaultStartFn,
    pollFn = defaultPollFn,
    pollIntervalMs = DEFAULT_POLL_MS,
    enabled = true,
  } = params;

  // Channel identity for the query key: the semantic fields that change the scalar.
  const channelKey = channel
    ? `${channel.column}|${channel.selection_rule}|${channel.intercept_key ? `${channel.intercept_key.kind}:${channel.intercept_key.level}` : ""}`
    : "";
  const sourceKey = collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`;
  const queryEnabled =
    enabled && channel != null && (collectionId !== undefined || (moleculeIds ?? []).length > 0);

  const start = useQuery({
    queryKey: ["activity-projection", "start", sourceKey, channelKey],
    queryFn: () =>
      startFn(
        collectionId
          ? { collection_id: collectionId, channel: channel as ActivityChannel }
          : { molecule_ids: moleculeIds ?? [], channel: channel as ActivityChannel },
      ),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });

  const startProj = start.data ?? null;
  const job = useMemo(
    () => (startProj ? { id: startProj.projection_id, status: startProj.status } : null),
    [startProj],
  );

  const { result: polled, error: pollError } = useJobPoll<
    ActivityProjectionResponse,
    ActivityProjectionResponse
  >({
    job,
    pollFn,
    getStatus: (j) => j.status,
    getResult: (j) => (j.status === "ready" ? j : null),
    getError: (j) => {
      if (j.status === "failed") return j.error_message ?? "activity projection failed";
      if (j.status === "cancelled") return "activity projection cancelled";
      return null;
    },
    pollIntervalMs,
    queryKey: "activity-projection-poll",
  });

  const ready = polled ?? (startProj?.status === "ready" ? startProj : null);
  const current = ready ?? startProj;

  return {
    projectionId: startProj?.projection_id ?? null,
    status: current?.status ?? null,
    isStarting: start.isPending && queryEnabled,
    isPolling: job != null && ready === null && pollError === null,
    error: (pollError ? new Error(pollError) : null) ?? (start.error as Error | null) ?? null,
  };
}

async function defaultStartFn(input: StartInput): Promise<ActivityProjectionResponse> {
  const { startActivityProjectionApiV1SarActivityProjectionPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  // The loose ActivityChannel (selection_rule: string) is cast to the generated
  // request type at this orval boundary — same intent as the response cast below.
  return startActivityProjectionApiV1SarActivityProjectionPost(
    input as unknown as Parameters<typeof startActivityProjectionApiV1SarActivityProjectionPost>[0],
  ) as unknown as ActivityProjectionResponse;
}

async function defaultPollFn(id: string): Promise<ActivityProjectionResponse> {
  const { getActivityProjectionApiV1SarActivityProjectionJobsProjectionIdGet } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return getActivityProjectionApiV1SarActivityProjectionJobsProjectionIdGet(
    id,
  ) as unknown as ActivityProjectionResponse;
}
