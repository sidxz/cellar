import type { IDatasource, IGetRowsParams } from "ag-grid-community";
import { useMemo, useState } from "react";

import type { ActivityValue } from "@/features/research-organization/types";
import type { DecompositionRowsResponse } from "@/shared/lib/api/model";
import { agFilterModelToParam, colIdToBackendKey } from "../lib/ag-filter-model";

/** The table's row shape — server `/rows` row mapped to AG-Grid row data. */
export interface RGroupRow {
  id: string;
  registration_number: string | null;
  name: string | null;
  smiles: string | null;
  rgroups: Record<string, string>;
  mw: number | null;
  clogp: number | null;
  tpsa: number | null;
  activity: number | null;
  activitySnapshot: ActivityValue | null;
}

type RowsBody = {
  offset: number;
  limit: number;
  sort: { col: string; dir: "asc" | "desc" }[];
  filter: Record<string, unknown> | undefined;
  projection_id: string | undefined;
};

export type UseDecompositionRowsReturn = {
  datasource: IDatasource | null;
  activityReference: number | null;
};

export function useDecompositionRows(
  runId: string | null,
  projectionId?: string | null,
  opts?: { fetchFn?: (runId: string, body: RowsBody) => Promise<DecompositionRowsResponse> },
): UseDecompositionRowsReturn {
  const fetchFn = opts?.fetchFn ?? defaultFetchRows;
  const [activityReference, setActivityReference] = useState<number | null>(null);

  const datasource = useMemo<IDatasource | null>(() => {
    if (!runId) return null;
    return {
      getRows: async (params: IGetRowsParams) => {
        const body: RowsBody = {
          offset: params.startRow,
          limit: params.endRow - params.startRow,
          sort: params.sortModel
            .map((s) => ({ col: colIdToBackendKey(s.colId), dir: s.sort as "asc" | "desc" }))
            .filter((s): s is { col: string; dir: "asc" | "desc" } => s.col !== null),
          filter: agFilterModelToParam(params.filterModel as Record<string, never>),
          projection_id: projectionId ?? undefined,
        };
        try {
          const res = await fetchFn(runId, body);
          setActivityReference(res.activity_reference ?? null);
          params.successCallback(res.rows.map(toRow), res.total);
        } catch {
          params.failCallback();
        }
      },
    };
    // setActivityReference is stable; runId/projectionId/fetchFn are the real deps.
  }, [runId, projectionId, fetchFn]);

  return { datasource, activityReference };
}

function toRow(r: DecompositionRowsResponse["rows"][number]): RGroupRow {
  return {
    id: r.molecule_id,
    registration_number: r.registration_number ?? null,
    name: r.name ?? null,
    smiles: r.smiles ?? null,
    rgroups: r.rgroups,
    mw: r.mw ?? null,
    clogp: r.clogp ?? null,
    tpsa: r.tpsa ?? null,
    activity: r.activity ?? null,
    activitySnapshot: (r.activity_snapshot as ActivityValue | null) ?? null,
  };
}

async function defaultFetchRows(runId: string, body: RowsBody): Promise<DecompositionRowsResponse> {
  const { decompositionRowsApiV1SarDecompositionRunIdRowsPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return decompositionRowsApiV1SarDecompositionRunIdRowsPost(
    runId,
    body,
  ) as unknown as DecompositionRowsResponse;
}
