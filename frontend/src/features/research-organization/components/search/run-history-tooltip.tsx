"use client";

import type { ActivityValue, InterceptKey } from "@/features/research-organization/types";
import { cn } from "@/shared/lib/utils";

export interface RunHistoryTooltipProps {
  av: ActivityValue;
  interceptKey: InterceptKey | null;
  unit: string;
}

function findInterceptValue(
  ivs:
    | Array<{ spec: { kind: string; level?: number }; value: number | null; at_bound?: boolean }>
    | null
    | undefined,
  ik: InterceptKey | null,
): { value: number | null; at_bound?: boolean } | undefined {
  if (!ivs || ivs.length === 0) return undefined;
  if (ik === null) return ivs[0];
  return ivs.find((iv) => iv.spec.kind === ik.kind && iv.spec.level === ik.level);
}

function findAggregate(av: ActivityValue, ik: InterceptKey | null) {
  if (!av.intercept_aggregates) return null;
  if (ik === null) {
    return av.intercept_aggregates.find((a) => a.spec.kind === "primary") ?? null;
  }
  return (
    av.intercept_aggregates.find((a) => a.spec.kind === ik.kind && a.spec.level === ik.level) ??
    null
  );
}

export function RunHistoryTooltip({ av, interceptKey, unit }: RunHistoryTooltipProps) {
  const aggregate = findAggregate(av, interceptKey);
  const stats = aggregate?.aggregate_stats;
  const runs = av.runs ?? [];

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-baseline justify-between">
        <span className="font-semibold uppercase tracking-wider text-muted-foreground">
          Run history
        </span>
        <span className="text-muted-foreground tabular-nums">
          {av.run_count ?? 0} run{(av.run_count ?? 0) === 1 ? "" : "s"}
        </span>
      </div>

      <table className="w-full border-collapse">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
            <th className="pb-1 text-left font-normal">Date</th>
            <th className="pb-1 text-right font-normal">Value</th>
            <th className="pb-1 text-right font-normal">R²</th>
            <th className="pb-1 text-right font-normal">Class</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const iv = findInterceptValue(r.intercept_values, interceptKey);
            const isInactive = r.curve_class === "inactive";
            const isAtBound = iv?.at_bound === true;
            return (
              <tr key={r.run_id} className="border-t border-border/40">
                <td className="py-1 tabular-nums">{r.run_date}</td>
                <td className="py-1 text-right tabular-nums font-mono">
                  {isInactive ? (
                    <span className="text-muted-foreground">ND</span>
                  ) : isAtBound ? (
                    <span>
                      &gt; {iv?.value} {unit}
                    </span>
                  ) : iv?.value !== null && iv?.value !== undefined ? (
                    <span>
                      {iv.value.toPrecision(3)} {unit}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">&mdash;</span>
                  )}
                </td>
                <td
                  className={cn(
                    "py-1 text-right tabular-nums",
                    (r.r_squared ?? 0) < 0.85 && "text-amber-600",
                  )}
                >
                  {r.r_squared?.toFixed(2) ?? "—"}
                </td>
                <td className="py-1 text-right uppercase text-[10px]">{r.curve_class ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {stats && (stats.geometric_mean !== null || stats.fold_range !== null) && (
        <div className="border-t border-border/60 pt-2 text-xs text-muted-foreground space-y-0.5 tabular-nums">
          {stats.geometric_mean !== null && (
            <div>
              Geometric mean:{" "}
              <span className="font-mono text-foreground">
                {stats.geometric_mean.toPrecision(3)} {unit}
              </span>
            </div>
          )}
          {stats.fold_range !== null && stats.fold_range !== 1 && (
            <div>
              Fold-range:{" "}
              <span className="font-mono text-foreground">{stats.fold_range.toPrecision(2)}×</span>
            </div>
          )}
          {stats.log_value_mean !== null && stats.log_value_sd !== null && (
            <div>
              log<sub>10</sub>(value):{" "}
              <span className="font-mono text-foreground">
                {stats.log_value_mean.toFixed(2)} ± {stats.log_value_sd.toFixed(2)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
