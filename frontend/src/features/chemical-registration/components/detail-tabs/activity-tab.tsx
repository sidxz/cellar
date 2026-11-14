"use client";

import { criterionLabel } from "@/features/screening-assay/components/detail-tabs/use-activity-tab";
import { DoseResponseSparkline } from "@/features/screening-assay/components/dose-response-sparkline";
import { ReportedEndpointBadge } from "@/features/screening-assay/components/reported-endpoint-badge";
import { findInterceptValue, interceptLabel } from "@/features/screening-assay/lib/intercept-label";
import {
  type CurveClass,
  type HitCriterion,
  type InterceptSpec,
  type InterceptValue,
  RUN_STATUS_LABELS,
  type RunStatus,
} from "@/features/screening-assay/types";
import { EmptyState } from "@/shared/components/empty-state";
import { Badge } from "@/shared/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import type {
  ProtocolActivityResponse,
  ProtocolActivityResponseBestCurvesItem,
  ProtocolActivityResponseInterceptsItem,
  ReadoutSummaryResponse,
} from "@/shared/lib/api/model";
import { formatDate } from "@/shared/lib/format-date";
import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { useMoleculeActivity } from "../../hooks/use-molecule-activity";

// ---------------------------------------------------------------------------
// ActivityTab
// ---------------------------------------------------------------------------

interface ActivityTabProps {
  moleculeId: string;
}

// The backend serializes `best_curves` / `intercepts` as untyped JSONB
// records (orval emits `ProtocolActivityResponse{BestCurvesItem,InterceptsItem}`
// as `{ [key: string]: unknown }`). These are the shapes the activity
// endpoint actually returns; we narrow the opaque records into them at the
// render edge below rather than re-typing the backend DTO.
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

/** Narrow an opaque generated `best_curves` JSONB record into the typed
 *  client shape rendered by `CurveTable`. */
function asBestCurve(item: ProtocolActivityResponseBestCurvesItem): BestCurve {
  return item as unknown as BestCurve;
}

/** Narrow an opaque generated `intercepts` JSONB record into the protocol
 *  intercept spec that drives the dynamic column set. */
function asInterceptSpec(item: ProtocolActivityResponseInterceptsItem): InterceptSpec {
  return item as unknown as InterceptSpec;
}

function bestCurves(protocol: ProtocolActivityResponse): BestCurve[] {
  return (protocol.best_curves ?? []).map(asBestCurve);
}

function interceptSpecs(protocol: ProtocolActivityResponse): InterceptSpec[] {
  return (protocol.intercepts ?? []).map(asInterceptSpec);
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
      {activity.protocols.map((protocol) => {
        const curves = bestCurves(protocol);
        const readouts = protocol.readouts ?? [];
        const plain = protocol.plain_readouts ?? [];
        return (
          <Card key={protocol.protocol_id}>
            <CardHeader>
              <div className="flex items-center gap-3">
                <CardTitle className="text-base">
                  <Link
                    href={`/assays/protocols/${protocol.protocol_id}`}
                    className="underline-offset-4 hover:underline"
                  >
                    {protocol.protocol_name}
                  </Link>
                </CardTitle>
                {protocol.protocol_code && (
                  <span className="font-mono text-xs text-muted-foreground">
                    {protocol.protocol_code}
                  </span>
                )}
                <Badge variant="outline">{protocol.protocol_type.replace(/_/g, " ")}</Badge>
                <HitMarker protocol={protocol} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {curves.length > 0 && (
                <CurveTable curves={curves} intercepts={interceptSpecs(protocol)} />
              )}
              {/* Reported endpoints render ALONGSIDE the curve table, not
                  instead of it: a protocol can hold a fitted curve on one
                  readout-def and a summary-imported endpoint on another. */}
              {readouts.length > 0 && (
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
                      {readouts.map((readout, idx) => (
                        <TableRow key={idx}>
                          <TableCell className="font-mono">
                            {readout.qualifier && readout.qualifier !== "="
                              ? `${readout.qualifier} `
                              : ""}
                            {readout.value != null ? readout.value.toFixed(3) : "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {readout.unit ?? "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {readout.source === "readout" ? (
                              <ReportedEndpointBadge />
                            ) : (
                              readout.source
                            )}
                          </TableCell>
                          <TableCell>{readout.data_point_count ?? 0}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
              {plain.length > 0 && <PlainReadoutTable readouts={plain} />}
              <RunLinks protocol={protocol} />
              {curves.length === 0 && readouts.length === 0 && plain.length === 0 && (
                <p className="text-sm text-muted-foreground">No readout data for this protocol.</p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plain readouts (thermal shift, single-point assays) and the hit call
// ---------------------------------------------------------------------------

/** Four significant figures, as the run's results show them. */
const fmt = (v: number) => String(Number(v.toPrecision(4)));

function runsText(r: ReadoutSummaryResponse): string {
  const runs = `${r.run_count} run${r.run_count === 1 ? "" : "s"}`;
  if (r.draft_run_count === 0) return runs;
  return r.draft_run_count === r.run_count && r.run_count === 1
    ? `${runs} (draft)`
    : `${runs} (${r.draft_run_count} draft)`;
}

/** How the shown value was picked from the compound's values on this protocol. */
function howChosen(r: ReadoutSummaryResponse): string {
  const of = `${r.data_point_count} value${r.data_point_count === 1 ? "" : "s"} in ${
    r.run_count
  } run${r.run_count === 1 ? "" : "s"}`;
  if (r.data_point_count === 1) return `From ${of}`;
  if (r.best_direction === "magnitude") return `Largest shift in either direction of ${of}`;
  if (r.best_direction === "low") return `Lowest of ${of}`;
  return `Highest of ${of}`;
}

/** The runs holding the compound's data, each opening the tab that shows it. */
function RunLinks({ protocol }: { protocol: ProtocolActivityResponse }) {
  const runs = protocol.runs ?? [];
  if (runs.length === 0) return null;
  const hash = protocol.results_tab ? `#${protocol.results_tab}` : "";
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <span className="text-muted-foreground">Runs</span>
      {runs.map((run) => (
        <Link
          key={run.run_id}
          href={`/assays/runs/${run.run_id}${hash}`}
          className="underline-offset-4 hover:underline"
        >
          {`${formatDate(run.run_date)} · ${RUN_STATUS_LABELS[run.status as RunStatus] ?? run.status}`}
        </Link>
      ))}
    </div>
  );
}

function PlainReadoutTable({ readouts }: { readouts: ReadoutSummaryResponse[] }) {
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Readout</TableHead>
            <TableHead>Value</TableHead>
            <TableHead>Unit</TableHead>
            <TableHead>Runs</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {readouts.map((r) => (
            <TableRow key={r.readout_definition_id}>
              <TableCell>{r.readout_name}</TableCell>
              <TableCell className="font-mono" title={howChosen(r)}>
                {`${r.qualifier !== "=" ? `${r.qualifier} ` : ""}${fmt(r.value)}`}
              </TableCell>
              <TableCell className="text-muted-foreground">{r.unit ?? "—"}</TableCell>
              <TableCell className={r.draft_run_count > 0 ? "text-muted-foreground" : undefined}>
                {runsText(r)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** The protocol's recommended hit rule applied to this compound; nothing without a rule. */
function HitMarker({ protocol }: { protocol: ProtocolActivityResponse }) {
  if (protocol.hit == null) return null;
  const rule = (protocol.hit_criteria ?? [])
    .map((c) => criterionLabel(c as HitCriterion))
    .join(" and ");
  const title = `By the protocol's recommended rule: ${rule}`;
  return protocol.hit ? (
    <Badge variant="secondary" title={title}>
      Hit
    </Badge>
  ) : (
    <span className="text-xs text-muted-foreground" title={title}>
      Not a hit
    </span>
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
      : // No declared intercepts: emit one synthetic primary column so
        // the table still surfaces `fitted_value` (legacy protocols).
        [{ kind: "ic", level: 50, basis: "relative_percent", label: "Fitted Value" }];

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
                  <TableCell key={`c-${spec.kind}-${spec.level}-${i}`} className="font-mono">
                    {value == null ? (
                      <span
                        className="text-muted-foreground"
                        title="No value for this intercept. Recompute the curve to refresh."
                      >
                        —
                      </span>
                    ) : iv?.at_bound ? (
                      <Badge variant="outline" className="text-xs border-amber-500 text-amber-700">
                        {value.toFixed(3)}
                        <span className="ml-1">⚠︎ at bound</span>
                      </Badge>
                    ) : (
                      value.toFixed(3)
                    )}
                  </TableCell>
                );
              })}
              <TableCell className="text-muted-foreground">{curve.fitted_unit}</TableCell>
              <TableCell className="font-mono">{curve.r_squared.toFixed(3)}</TableCell>
              <TableCell>{curve.num_points}</TableCell>
              <TableCell className="text-muted-foreground">{curve.curve_class ?? "—"}</TableCell>
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
