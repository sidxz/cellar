"use client";

import type { OrgPlatePolicyResponse, SetOrgPlatePolicyBody } from "@/shared/lib/api/model";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/** Per-org plate loan/visibility policy. Aliased from the orval-generated type. */
export type OrgPlatePolicy = OrgPlatePolicyResponse;
export type SetOrgPlatePolicyInput = SetOrgPlatePolicyBody;

const orgPlatePolicyKey = (orgId: string) => ["org-plate-policy", orgId];

/** Fetches the policy for an org. Server returns defaults when unconfigured. */
export function useOrgPlatePolicy(orgId: string | undefined) {
  return useQuery({
    queryKey: orgPlatePolicyKey(orgId ?? ""),
    queryFn: () =>
      customInstance<OrgPlatePolicy>({
        url: `${API_V1}/org-plate-policies/${orgId}`,
        method: "GET",
      }),
    enabled: !!orgId,
  });
}

/** Sets (overwrites) an org's plate policy. Admin-only on the backend. */
export function useSetOrgPlatePolicy(orgId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SetOrgPlatePolicyInput) =>
      customInstance<OrgPlatePolicy>({
        url: `${API_V1}/org-plate-policies/${orgId}`,
        method: "PUT",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orgPlatePolicyKey(orgId) });
      showSuccess("Org plate policy updated");
    },
  });
}
