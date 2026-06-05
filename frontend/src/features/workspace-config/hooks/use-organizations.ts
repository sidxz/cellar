"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { CreateOrganizationInput, Organization, UpdateOrganizationInput } from "../types";

const ORGS_KEY = ["organizations"];

const orgHooks = createCrudHooks<Organization, CreateOrganizationInput, UpdateOrganizationInput>({
  entityName: "Organization",
  baseUrl: "/api/v1/organizations",
  queryKey: ORGS_KEY,
});

/** Custom list — supports includeInactive boolean flag. */
export function useOrganizations(includeInactive = false) {
  return useQuery({
    queryKey: [...ORGS_KEY, { includeInactive }],
    queryFn: async () => {
      const resp = await customInstance<Organization[] | { items: Organization[] }>({
        url: "/api/v1/organizations",
        method: "GET",
        params: includeInactive ? { include_inactive: "true" } : undefined,
      });
      return Array.isArray(resp) ? resp : resp.items;
    },
  });
}

export const useCreateOrganization = orgHooks.useCreate;
export const useUpdateOrganization = orgHooks.useUpdate;
