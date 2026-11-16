"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { DatasetRequest } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";
import type { Dataset, DatasetSource, Level } from "../types";
import { VISUALIZATION_DATASET_KEY } from "./query-keys";

function toRequest(source: DatasetSource, level: Level): DatasetRequest {
  return {
    level,
    source:
      source.kind === "run"
        ? { kind: "run", run_id: source.runId }
        : { kind: "protocol", protocol_id: source.protocolId, run_ids: source.runIds ?? null },
  };
}

export function useDataset(source: DatasetSource | null, level: Level) {
  return useQuery({
    queryKey: [...VISUALIZATION_DATASET_KEY, source, level],
    enabled: source !== null,
    queryFn: () =>
      customInstance<Dataset>({
        url: `${API_V1}/visualization/dataset`,
        method: "POST",
        data: toRequest(source as DatasetSource, level),
      }),
    // A dataset is large and the chemist is mid-analysis: fetch it once per source, never
    // again behind their back (window focus, reconnect). Reopening the workbench reloads it.
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
}
