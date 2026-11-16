"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ProtocolPlateQcAveragesResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";
import type { ProtocolStats } from "../types";

export function useProtocolStats(protocolId: string) {
  return useQuery({
    queryKey: ["protocol-stats", protocolId],
    queryFn: () =>
      customInstance<ProtocolStats>({
        url: `${API_V1}/protocols/${protocolId}/stats`,
        method: "GET",
      }),
  });
}

/** Plate QC per readout x layer averaged over the protocol's plates (rejected runs left out). */
export function useProtocolPlateQcAverages(protocolId: string) {
  return useQuery({
    queryKey: ["protocol-stats", protocolId, "plate-qc-averages"],
    queryFn: () =>
      customInstance<ProtocolPlateQcAveragesResponse>({
        url: `${API_V1}/protocols/${protocolId}/plate-qc-averages`,
        method: "GET",
      }),
    enabled: !!protocolId,
  });
}
