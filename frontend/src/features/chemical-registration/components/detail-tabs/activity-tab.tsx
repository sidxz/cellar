"use client";

import { FlaskConical } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { EmptyState } from "@/shared/components/empty-state";
import { DoseResponseSparkline } from "@/features/screening-assay/components/dose-response-sparkline";
import { findInterceptValue, interceptLabel } from "@/features/screening-assay/lib/intercept-label";
import type {
  CurveClass,
  InterceptSpec,
  InterceptValue,
} from "@/features/screening-assay/types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useMoleculeActivity } from "../../hooks/use-molecule-activity";

// ---------------------------------------------------------------------------
// ActivityTab
// ---------------------------------------------------------------------------

interface ActivityTabProps {
  moleculeId: string;
}

interface BestCurve {
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
  intercept_values?: InterceptValue[];
}

export function ActivityTab({ moleculeId }: ActivityTabProps) {
  const { data: activity, isLoading } = useMoleculeActivity(moleculeId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!activity?.protocols?.length) {
    return (
      <EmptyState
        icon={FlaskConical}
        title="No activity data"
        description="No activity data for this molecule."
      />
    );
  }

  return (
    <div className="space-y-6">
      {activity.protocols.map((protocol) => (
        <Card key={protocol.protocol_id}>
          <CardHeader>
            <div className="flex items-center gap-3">
              <CardTitle className="text-base">
                {protocol.protocol_name}
              </CardTitle>
              <Badge variant="outline">
                {protocol.protocol_type.replace(/_/g, " ")}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {protocol.best_curves.length > 0 ? (
              <CurveTable
                curves={protocol.best_curves}
                intercepts={protocol.intercepts ?? []}
              />
            ) : protocol.readouts.length > 0 ? (
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Value</TableHead>
                      <TableHead>Unit</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Points</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {protocol.readouts.map((readout, idx) => (
                      <TableRow key={idx}>
                        <TableCell className="font-mono">
                          {readout.qualifier && readout.qualifier !== "=" ? `${readout.qualifier} ` : ""}
                          {readout.value != null ? readout.value.toFixed(3) : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {readout.unit ?? "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {readout.source}
                        </TableCell>
                        <TableCell>{readout.data_point_count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No readout data for this protocol.
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CurveTable — per-Card dynamic table
//
// Columns are driven by the protocol's intercept spec list. Each row is
// one curve fit for this molecule on this protocol; cell values are
// matched out of `curve.intercept_values` by (kind, level). When the
// protocol declares no intercepts we fall back to a "Fitted Value"
// column so the headline number still renders for legacy / single-
// intercept protocols.
// ---------------------------------------------------------------------------

function CurveTable({
  curves,
  intercepts,
}: {
  curves: BestCurve[];
  intercepts: InterceptSpec[];
}) {
  const interceptCols: InterceptSpec[] =
    intercepts.length > 0
      ? intercepts
      // No declared intercepts: emit one synthetic primary column so
      // the table still surfaces `fitted_value` (legacy protocols).
      : [{ kind: "ic", level: 50, basis: "relative_percent", label: "Fitted Value" }];

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            {interceptCols.map((spec, i) => (
              <TableHead key={`h-${spec.kind}-${spec.level}-${i}`}>
                {interceptLabel(spec)}
              </TableHead>
            ))}
            <TableHead>Unit</TableHead>
            <TableHead>R²</TableHead>
            <TableHead>Points</TableHead>
            <TableHead>Class</TableHead>
            <TableHead>Curve</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {curves.map((curve, idx) => (
            <TableRow key={idx}>
              {interceptCols.map((spec, i) => {
                const iv = findInterceptValue(curve.intercept_values, spec);
                // Primary column falls back to fitted_value for legacy
                // curves that have no persisted intercept_values.
                const value = iv?.value ?? (i === 0 ? curve.fitted_value : null);
                return (
                  <TableCell
                    key={`c-${spec.kind}-${spec.level}-${i}`}
                    className="font-mono"
                  >
                    {value == null ? (
                      <span
                        className="text-muted-foreground"
                        title="No value for this intercept. Recompute the curve to refresh."
                      >
                        —
                      </span>
                    ) : iv?.at_bound ? (
                      <Badge
                        variant="outline"
                        className="text-xs border-amber-500 text-amber-700"
                      >
                        {value.toFixed(3)}
                        <span className="ml-1">⚠︎ at bound</span>
                      </Badge>
                    ) : (
                      value.toFixed(3)
                    )}
                  </TableCell>
                );
              })}
              <TableCell className="text-muted-foreground">
                {curve.fitted_unit}
              </TableCell>
              <TableCell className="font-mono">
                {curve.r_squared.toFixed(3)}
              </TableCell>
              <TableCell>{curve.num_points}</TableCell>
              <TableCell className="text-muted-foreground">
                {curve.curve_class ?? "—"}
              </TableCell>
              <TableCell>
                {curve.hill_slope != null ? (
                  <DoseResponseSparkline
                    params={{
                      hill_slope: curve.hill_slope,
                      top: curve.top ?? 100,
                      bottom: curve.bottom ?? 0,
                      fitted_value: curve.fitted_value,
                      r_squared: curve.r_squared,
                    }}
                    dataPoints={curve.data_points}
                    curveClass={curve.curve_class as CurveClass | null}
                  />
                ) : (
                  "--"
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
