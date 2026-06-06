"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { ConditionGroupsResponse } from "../types";

export function useConditionGroups(
  protocolId: string | undefined,
  conditionName: string | undefined,
) {
  return useQuery<ConditionGroupsResponse>({
    queryKey: ["condition-groups", protocolId, conditionName],
    queryFn: () =>
      customInstance<ConditionGroupsResponse>({
        url: `${API_V1}/protocols/${protocolId}/condition-groups`,
        method: "GET",
        params: { condition_name: conditionName! },
      }),
    enabled: !!protocolId && !!conditionName,
  });
}
