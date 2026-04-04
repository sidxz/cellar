"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getApiBaseUrl } from "@/shared/lib/api/custom-instance";
import { getSentinelClient } from "@/shared/lib/auth/config";

const MOLECULES_KEY = ["molecules"];

export interface BulkRegistrationItemResult {
  row_index: number;
  success: boolean;
  is_new: boolean;
  molecule_id: string | null;
  error: string | null;
}

export interface BulkRegistrationResponse {
  id: string;
  status: string;
  total_count: number;
  registered_count: number;
  duplicate_count: number;
  error_count: number;
  items: BulkRegistrationItemResult[];
}

export function useBulkRegistration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      fileFormat,
      originatingOrgId,
    }: {
      file: File;
      fileFormat: string;
      originatingOrgId: string;
    }) => {
      const client = getSentinelClient();
      const authHeaders = client?.isAuthenticated ? client.getHeaders() : {};

      const formData = new FormData();
      formData.append("file", file);
      formData.append("file_format", fileFormat);
      formData.append("originating_org_id", originatingOrgId);

      const res = await fetch(
        `${getApiBaseUrl()}/api/v1/bulk-registrations`,
        {
          method: "POST",
          headers: { ...authHeaders },
          body: formData,
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Upload failed: ${res.status}`);
      }
      return res.json() as Promise<BulkRegistrationResponse>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: MOLECULES_KEY }),
  });
}
