"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CddProtocolMappingResultResponse,
  CddProtocolSummaryResponse,
  MappedConditionResponse,
  MappedReadoutResponse,
  MappingWarningResponse,
} from "@/shared/lib/api/model";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// ─── API DTOs (orval-generated; aliased per project rule) ────────────────────
// The CDD protocol-mapping preview shapes are generated from the live backend
// OpenAPI — aliased to domain-friendly names so call sites don't churn.
export type CddProtocolSummary = CddProtocolSummaryResponse;
export type MappedReadout = MappedReadoutResponse;
export type MappedCondition = MappedConditionResponse;
export type MappingWarning = MappingWarningResponse;
export type CddProtocolMappingResult = CddProtocolMappingResultResponse;

const CDD_PROTOCOLS_KEY = ["cdd-import", "protocols"];

export function useCddProtocols(enabled: boolean) {
  return useQuery({
    queryKey: CDD_PROTOCOLS_KEY,
    queryFn: () =>
      customInstance<CddProtocolSummary[]>({
        url: `${API_V1}/cdd-import/protocols`,
        method: "GET",
      }),
    enabled,
    staleTime: STALE_TIME.MEDIUM, // CDD protocols don't change often
  });
}

export function useCddProtocolPreview(externalId: number | null) {
  return useQuery({
    queryKey: ["cdd-import", "preview", externalId],
    queryFn: () =>
      customInstance<CddProtocolMappingResult>({
        url: `${API_V1}/cdd-import/protocols/${externalId}/preview`,
        method: "GET",
      }),
    enabled: externalId !== null,
    staleTime: STALE_TIME.MEDIUM,
  });
}

export function useImportCddProtocol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      externalId,
      nameOverride,
    }: {
      externalId: number;
      nameOverride?: string;
    }) =>
      customInstance({
        url: `${API_V1}/cdd-import/protocols/${externalId}`,
        method: "POST",
        data: nameOverride ? { name_override: nameOverride } : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["protocols"] });
      showSuccess("Protocol imported from CDD Vault");
    },
  });
}
