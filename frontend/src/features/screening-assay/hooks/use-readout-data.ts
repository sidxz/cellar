"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CreateReadoutDataInput, ReadoutData } from "../types";

const READOUT_DATA_KEY = ["readout-data"];

export function useReadoutDataByRun(runId: string | undefined) {
  return useQuery({
    queryKey: [...READOUT_DATA_KEY, "run", runId],
    queryFn: () =>
      customInstance<ReadoutData[]>({
        url: "/api/v1/readout-data",
        method: "GET",
        params: { run_id: runId! },
      }),
    enabled: !!runId,
  });
}

export function useCreateReadoutData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateReadoutDataInput) =>
      customInstance<ReadoutData>({
        url: "/api/v1/readout-data",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: READOUT_DATA_KEY }),
  });
}
