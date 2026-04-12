"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";

export interface ProtocolActivityResponse {
  protocol_id: string;
  protocol_name: string;
  protocol_type: string;
  readouts: Array<{
    value: number | null;
    qualifier: string | null;
    unit: string | null;
    source: string;
    curve_type: string | null;
    r_squared: number | null;
    data_point_count: number;
  }>;
  best_curves: Array<{
    curve_type: string;
    fitted_value: number;
    fitted_unit: string;
    r_squared: number;
    hill_slope: number;
    num_points: number;
    curve_class: string | null;
    data_points: Array<{ x: number; y: number }> | null;
  }>;
}

export interface ActivitySummaryResponse {
  molecule_id: string;
  protocols: ProtocolActivityResponse[];
}

const MOLECULES_KEY = ["molecules"];

export function useMoleculeActivity(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, moleculeId, "activity"],
    queryFn: () =>
      customInstance<ActivitySummaryResponse>({
        url: `/api/v1/molecules/${moleculeId}/activity`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
