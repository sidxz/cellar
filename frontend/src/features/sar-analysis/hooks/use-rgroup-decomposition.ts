"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import { useMutation } from "@tanstack/react-query";

/** One of moleculeIds OR collectionId must be set (the backend enforces xor). */
export interface RGroupDecomposeArgs {
  moleculeIds?: string[];
  collectionId?: string;
  coreSmiles: string;
}

type DecomposeFn = (body: {
  molecule_ids?: string[];
  collection_id?: string;
  core_smiles: string;
}) => Promise<RGroupDecompositionResponse>;

const defaultDecomposeFn: DecomposeFn = (body) =>
  customInstance<RGroupDecompositionResponse>({
    url: `${API_V1}/sar/r-group-decomposition`,
    method: "POST",
    data: body,
  });

/** Injectable `decomposeFn` for tests; defaults to the live POST. */
export function useRGroupDecomposition(opts?: { decomposeFn?: DecomposeFn }) {
  const decomposeFn = opts?.decomposeFn ?? defaultDecomposeFn;
  return useMutation({
    mutationFn: (args: RGroupDecomposeArgs) =>
      decomposeFn(
        args.collectionId
          ? { collection_id: args.collectionId, core_smiles: args.coreSmiles }
          : { molecule_ids: args.moleculeIds ?? [], core_smiles: args.coreSmiles },
      ),
  });
}
