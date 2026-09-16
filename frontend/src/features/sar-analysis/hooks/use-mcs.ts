import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { ComputeMcsResponse, McsResultDto } from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";

/** The maximum common substructure of a molecule set. Generated DTO, aliased. */
export type McsResult = McsResultDto;

/** Backend guardrails (`application/sar_analysis/compute_mcs.py`). Below the
 *  floor there is nothing to share; above the cap the request is refused. */
const MIN_SET_SIZE = 2;
const MAX_SET_SIZE = 10_000;

/**
 * Either ``moleculeIds`` (an explicit list) or ``collectionId`` (expanded
 * server-side to every member). Exactly one must be set — the backend rejects
 * both and neither.
 */
export type UseMcsParams = {
  moleculeIds?: string[];
  collectionId?: string;
  /** Override for tests — defaults to the orval-generated POST. */
  computeFn?: (input: {
    molecule_ids?: string[];
    collection_id?: string;
  }) => Promise<ComputeMcsResponse>;
  enabled?: boolean;
};

export type UseMcsReturn = {
  mcs: McsResult | null;
  isLoading: boolean;
  error: Error | null;
  /** True when the set is outside the sizes the endpoint accepts, so nothing
   *  was requested. Lets a caller stay quiet rather than show a failure. */
  outOfRange: boolean;
};

function sortedKey(ids: string[]): string {
  return [...ids].sort().join(",");
}

/**
 * Maximum common substructure for a set of molecules.
 *
 * A plain query, not a job + poll like `useScaffoldTree` — the endpoint
 * computes inline (it is milliseconds on realistic sets and carries its own
 * timeout), so there is nothing to wait on.
 */
export function useMcs(params: UseMcsParams): UseMcsReturn {
  const { moleculeIds, collectionId, computeFn = defaultComputeFn, enabled = true } = params;

  const key = useMemo(
    () => (collectionId ? `coll:${collectionId}` : `ids:${sortedKey(moleculeIds ?? [])}`),
    [collectionId, moleculeIds],
  );

  // A collection's size is only known server-side, so only the explicit-id
  // path can be range-checked here.
  const idCount = moleculeIds?.length ?? 0;
  const outOfRange =
    collectionId === undefined && (idCount < MIN_SET_SIZE || idCount > MAX_SET_SIZE);

  const query = useQuery({
    queryKey: ["mcs", key],
    queryFn: () =>
      computeFn(
        collectionId ? { collection_id: collectionId } : { molecule_ids: moleculeIds ?? [] },
      ),
    enabled: enabled && !outOfRange && (collectionId !== undefined || idCount > 0),
    staleTime: STALE_TIME.MEDIUM,
  });

  return {
    mcs: query.data?.result ?? null,
    isLoading: query.isPending && query.fetchStatus !== "idle",
    error: (query.error as Error | null) ?? null,
    outOfRange,
  };
}

/** Whether an MCS is worth offering at all: something was found, and it was
 *  found completely. A timed-out answer is the best-so-far, which is smaller
 *  than the true MCS — usable as information, never as a core. */
export function isUsableCore(mcs: McsResult | null): mcs is McsResult {
  return mcs != null && mcs.num_atoms > 0 && !mcs.timed_out && mcs.core_smiles != null;
}

async function defaultComputeFn(input: {
  molecule_ids?: string[];
  collection_id?: string;
}): Promise<ComputeMcsResponse> {
  const { computeMcsApiV1SarMcsPost } = await import("@/shared/lib/api/sar-analysis/sar-analysis");
  return computeMcsApiV1SarMcsPost(input);
}
