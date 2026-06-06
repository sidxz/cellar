"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  ActivitySummaryResponse as GeneratedActivitySummaryResponse,
  ProtocolActivityResponse as GeneratedProtocolActivityResponse,
} from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";
import { MOLECULES_KEY } from "./query-keys";

// Backend-owned shapes — aliased from the orval-generated model (the
// nested `readouts` / `best_curves` / `intercepts` are carried by the
// generated sub-models ActivityValueResponse / ...BestCurvesItem /
// ...InterceptsItem). The latter two are emitted as opaque JSONB records
// (`{ [key: string]: unknown }`); ActivityTab narrows them into the typed
// client shapes at the render edge.
export type ProtocolActivityResponse = GeneratedProtocolActivityResponse;
export type ActivitySummaryResponse = GeneratedActivitySummaryResponse;

export function useMoleculeActivity(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, moleculeId, "activity"],
    queryFn: () =>
      customInstance<ActivitySummaryResponse>({
        url: `/api/v1/molecules/${moleculeId}/activity`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
