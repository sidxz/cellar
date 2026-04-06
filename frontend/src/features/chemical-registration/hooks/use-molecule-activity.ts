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
  }>;
}

export interface ActivitySummaryResponse {
  molecule_id: string;
  protocols: ProtocolActivityResponse[];
}

export function useMoleculeActivity(moleculeId: string | undefined) {
  return useQuery({
    queryKey: ["molecule-activity", moleculeId],
    queryFn: () =>
      customInstance<ActivitySummaryResponse>({
        url: `/api/v1/molecules/${moleculeId}/activity`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
