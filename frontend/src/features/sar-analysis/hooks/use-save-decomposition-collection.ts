import { useCallback } from "react";

import type { SaveCollectionResponse } from "@/shared/lib/api/model";

export type SaveAllArgs = {
  runId: string;
  name: string;
  projectId: string | null;
  filter?: Record<string, unknown>;
  projectionId?: string | null;
};

type SaveBody = {
  name: string;
  project_id: string | null;
  filter: Record<string, unknown> | undefined;
  projection_id: string | undefined;
};

export function useSaveDecompositionCollection(opts?: {
  fetchFn?: (runId: string, body: SaveBody) => Promise<SaveCollectionResponse>;
}) {
  const fetchFn = opts?.fetchFn ?? defaultSave;
  const saveAll = useCallback(
    (args: SaveAllArgs): Promise<SaveCollectionResponse> =>
      fetchFn(args.runId, {
        name: args.name,
        project_id: args.projectId,
        filter: args.filter,
        projection_id: args.projectionId ?? undefined,
      }),
    [fetchFn],
  );
  return { saveAll };
}

async function defaultSave(runId: string, body: SaveBody): Promise<SaveCollectionResponse> {
  const { saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost } = await import(
    "@/shared/lib/api/sar-analysis/sar-analysis"
  );
  return saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost(
    runId,
    body as unknown as Parameters<
      typeof saveDecompositionCollectionApiV1SarDecompositionRunIdSaveCollectionPost
    >[1],
  ) as unknown as SaveCollectionResponse;
}
