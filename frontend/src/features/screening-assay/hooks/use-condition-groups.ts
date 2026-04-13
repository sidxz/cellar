"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { ConditionGroupsResponse } from "../types";

export function useConditionGroups(
  protocolId: string | undefined,
  conditionName: string | undefined
) {
  return useQuery<ConditionGroupsResponse>({
    queryKey: ["condition-groups", protocolId, conditionName],
    queryFn: () =>
      customInstance<ConditionGroupsResponse>({
        url: `/api/v1/protocols/${protocolId}/condition-groups`,
        method: "GET",
        params: { condition_name: conditionName! },
      }),
    enabled: !!protocolId && !!conditionName,
  });
}
