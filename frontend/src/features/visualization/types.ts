import type {
  DatasetColumnResponse,
  DatasetResponse,
  RunRowCountsResponse,
  SavedVisualizationResponse,
  SavedVisualizationSummaryResponse,
} from "@/shared/lib/api/model";

export type Dataset = DatasetResponse;
export type DatasetColumn = DatasetColumnResponse;
export type RunRowCounts = RunRowCountsResponse;
export type SavedView = SavedVisualizationResponse;
export type SavedViewSummary = SavedVisualizationSummaryResponse;

/** Row level: what one dataset row is. */
export type Level = DatasetResponse["level"];

export type DatasetSource =
  | { kind: "protocol"; protocolId: string; runIds?: string[] }
  | { kind: "run"; runId: string };
