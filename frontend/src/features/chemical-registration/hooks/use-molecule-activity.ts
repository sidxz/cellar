"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import { MOLECULES_KEY } from "./query-keys";

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
    top: number;
    bottom: number;
    num_points: number;
    curve_class: string | null;
    data_points: Array<{ x: number; y: number }> | null;
    /** Per-spec intercepts (EC50, EC90, IC10, ...) computed from this
     *  curve's fit. Empty on legacy curves; the FE per-Card table
     *  renders one column per protocol intercept and reads values from
     *  this list. */
    intercept_values?: Array<{
      spec: {
        kind: "ic" | "ec";
        level: number;
        basis: "relative_percent" | "absolute";
        label?: string | null;
      };
      value: number;
      confidence_interval_low: number | null;
      confidence_interval_high: number | null;
      at_bound: boolean;
    }>;
  }>;
  /** Protocol-declared intercept specs. Drives the dynamic column set
   *  on this protocol's Card; matches cell values out of each row's
   *  `intercept_values` by (kind, level). */
  intercepts?: Array<{
    kind: "ic" | "ec";
    level: number;
    basis: "relative_percent" | "absolute";
    label?: string | null;
  }>;
}

export interface ActivitySummaryResponse {
  molecule_id: string;
  protocols: ProtocolActivityResponse[];
}

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
