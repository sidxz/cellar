"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateOrganizationInput,
  Organization,
  UpdateOrganizationInput,
} from "../types";

const ORGS_KEY = ["organizations"];

export function useOrganizations(includeInactive = false) {
  return useQuery({
    queryKey: [...ORGS_KEY, { includeInactive }],
    queryFn: () =>
      customInstance<Organization[]>({
        url: "/api/v1/organizations",
        method: "GET",
        params: includeInactive ? { include_inactive: "true" } : undefined,
      }),
  });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateOrganizationInput) =>
      customInstance<Organization>({
        url: "/api/v1/organizations",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ORGS_KEY }),
  });
}

export function useUpdateOrganization(orgId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateOrganizationInput) =>
      customInstance<Organization>({
        url: `/api/v1/organizations/${orgId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ORGS_KEY }),
  });
}
