import type {
  DatasetColumnResponse,
  DatasetResponse,
  RunRowCountsResponse,
} from "@/shared/lib/api/model";

export type Dataset = DatasetResponse;
export type DatasetColumn = DatasetColumnResponse;
export type RunRowCounts = RunRowCountsResponse;

/** Row level: what one dataset row is. */
export type Level = "wells";

export type DatasetSource =
  | { kind: "protocol"; protocolId: string; runIds?: string[] }
  | { kind: "run"; runId: string };
