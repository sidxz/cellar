"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  BulkRegistrationMappingResponse,
  CreateBulkRegistrationMappingRequest,
  UpdateBulkRegistrationMappingRequest,
} from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export type BulkRegistrationMapping = BulkRegistrationMappingResponse;

const MAPPINGS_KEY = ["bulk-registration-mappings"];

/** GET /api/v1/bulk-registration-mappings — the workspace's saved column mappings. */
export function useBulkRegistrationMappings() {
  return useQuery({
    queryKey: MAPPINGS_KEY,
    queryFn: () =>
      customInstance<BulkRegistrationMapping[]>({
        url: `${API_V1}/bulk-registration-mappings`,
        method: "GET",
      }),
  });
}

/** POST, or PATCH when `id` is given. */
export function useSaveBulkRegistrationMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id?: string;
      body: CreateBulkRegistrationMappingRequest & UpdateBulkRegistrationMappingRequest;
    }) =>
      customInstance<BulkRegistrationMapping>({
        url: id
          ? `${API_V1}/bulk-registration-mappings/${id}`
          : `${API_V1}/bulk-registration-mappings`,
        method: id ? "PATCH" : "POST",
        data: body,
      }),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: MAPPINGS_KEY });
      showSuccess(`Saved mapping "${m.name}"`);
    },
    onError: (err: Error) => {
      showError(err.message ?? "Could not save the mapping");
    },
  });
}
