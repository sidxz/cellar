import { useQuery } from "@tanstack/react-query";

import type { HeatmapResponse } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";

type HeatmapBody = { axis_y: string; axis_x: string; projection_id: string };

export type UseHeatmapAggregationParams = {
  runId: string | null;
  projectionId: string | null;
  axisY: string;
  axisX: string;
  enabled?: boolean;
  fetchFn?: (runId: string, body: HeatmapBody) => Promise<HeatmapResponse>;
};

export function useHeatmapAggregation({
  runId,
  projectionId,
  axisY,
  axisX,
  enabled = true,
  fetchFn = defaultFetchFn,
}: UseHeatmapAggregationParams): {
  data: HeatmapResponse | null;
  isLoading: boolean;
  error: Error | null;
} {
  const queryEnabled = enabled && !!runId && !!projectionId && !!axisY && !!axisX;
  const query = useQuery({
    queryKey: ["sar-heatmap", runId, projectionId, axisY, axisX],
    queryFn: () =>
      fetchFn(runId as string, {
        axis_y: axisY,
        axis_x: axisX,
        projection_id: projectionId as string,
      }),
    enabled: queryEnabled,
    staleTime: STALE_TIME.MEDIUM,
  });
  return {
    data: query.data ?? null,
    isLoading: query.isLoading && queryEnabled,
    error: (query.error as Error | null) ?? null,
  };
}

async function defaultFetchFn(runId: string, body: HeatmapBody): Promise<HeatmapResponse> {
  const { decompositionHeatmapApiV1SarDecompositionRunIdHeatmapPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return decompositionHeatmapApiV1SarDecompositionRunIdHeatmapPost(
    runId,
    body,
  ) as unknown as HeatmapResponse;
}
