"use client";

import { FlaskConical } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { EmptyState } from "@/shared/components/empty-state";
import { DoseResponseSparkline } from "@/features/screening-assay/components/dose-response-sparkline";
import type { CurveParams, CurveClass } from "@/features/screening-assay/types";
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
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Curve Type</TableHead>
                      <TableHead>Fitted Value</TableHead>
                      <TableHead>Unit</TableHead>
                      <TableHead>R²</TableHead>
                      <TableHead>Points</TableHead>
                      <TableHead>Class</TableHead>
                      <TableHead>Curve</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {protocol.best_curves.map((curve, idx) => (
                      <TableRow key={idx}>
                        <TableCell>
                          <Badge variant="outline">
                            {curve.curve_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono">
                          {curve.fitted_value.toFixed(3)}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {curve.fitted_unit}
                        </TableCell>
                        <TableCell className="font-mono">
                          {curve.r_squared.toFixed(3)}
                        </TableCell>
                        <TableCell>{curve.num_points}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {curve.curve_class ?? "\u2014"}
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
                          {readout.value != null ? readout.value.toFixed(3) : "\u2014"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {readout.unit ?? "\u2014"}
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
