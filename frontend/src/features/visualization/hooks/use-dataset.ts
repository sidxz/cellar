"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { toDatasetRequest } from "../lib/source-url";
import type { Dataset, DatasetSource, Level } from "../types";
import { VISUALIZATION_DATASET_KEY } from "./query-keys";

export function useDataset(source: DatasetSource | null, level: Level) {
  return useQuery({
    queryKey: [...VISUALIZATION_DATASET_KEY, source, level],
    enabled: source !== null,
    queryFn: () =>
      customInstance<Dataset>({
        url: `${API_V1}/visualization/dataset`,
        method: "POST",
        data: toDatasetRequest(source as DatasetSource, level),
      }),
    // A dataset is large and the chemist is mid-analysis: fetch it once per source, never
    // again behind their back (window focus, reconnect). Reopening the workbench reloads it.
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
}
