"use client";

import { memo } from "react";
import type { CampaignMeasurementResponse } from "../../types";
import type { DoseResponseCurveResponse } from "@/shared/lib/api/model";
import { DoseResponseCell as SearchDoseResponseCell } from "@/features/research-organization/components/search/dose-response-cell";
import { measurementToActivity } from "../../lib/measurement-to-activity";

interface CampaignDoseResponseCellProps {
  measurement: CampaignMeasurementResponse | undefined;
  curveMap: Map<string, DoseResponseCurveResponse>;
}

function CampaignDoseResponseCellInner({ measurement, curveMap }: CampaignDoseResponseCellProps) {
  if (!measurement) return <span className="text-muted-foreground">&mdash;</span>;
  const curve = measurement.source_curve_id ? curveMap.get(measurement.source_curve_id) ?? null : null;
  const av = measurementToActivity(measurement, curve);
  if (!av) return <span className="text-muted-foreground">&mdash;</span>;
  return <SearchDoseResponseCell value={av} />;
}

export const CampaignDoseResponseCell = memo(CampaignDoseResponseCellInner);
