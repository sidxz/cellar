"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { MoleculeActivityDetail } from "../types";

export function useMoleculeActivityDetail(moleculeId: string | null) {
  return useQuery({
    queryKey: ["molecule-activity-detail", moleculeId],
    queryFn: () =>
      customInstance<MoleculeActivityDetail>({
        url: `/api/v1/molecules/${moleculeId}/activity-detail`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
