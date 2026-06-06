"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { unwrapList } from "@/shared/types/pagination";
import { useQuery } from "@tanstack/react-query";
import type { CreateOrganizationInput, Organization, UpdateOrganizationInput } from "../types";

const ORGS_KEY = ["organizations"];

const orgHooks = createCrudHooks<Organization, CreateOrganizationInput, UpdateOrganizationInput>({
  entityName: "Organization",
  baseUrl: `${API_V1}/organizations`,
  queryKey: ORGS_KEY,
});

/** Custom list — supports includeInactive boolean flag. */
export function useOrganizations(includeInactive = false) {
  return useQuery({
    queryKey: [...ORGS_KEY, { includeInactive }],
    queryFn: async () => {
      const resp = await customInstance<Organization[] | { items: Organization[] }>({
        url: `${API_V1}/organizations`,
        method: "GET",
        params: includeInactive ? { include_inactive: "true" } : undefined,
      });
      return unwrapList(resp);
    },
  });
}

export const useCreateOrganization = orgHooks.useCreate;
export const useUpdateOrganization = orgHooks.useUpdate;
