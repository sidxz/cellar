import { formatConditionEntries } from "@/features/screening-assay/lib/conditions";
import type { Run } from "@/features/screening-assay/types";

/** How a run is named in the workbench: "2026-11-12 · A. Chen" (never its id). */
export function runLabel(run: Run, nameOf: (userId: string) => string): string {
  const who = nameOf(run.operator);
  return who ? `${run.run_date} · ${who}` : run.run_date;
}

export function conditionsText(run: Run): string {
  return formatConditionEntries(run.conditions)
    .map((e) => `${e.key}: ${e.value}`)
    .join(", ");
}

export function newestFirst(runs: readonly Run[]): Run[] {
  return [...runs].sort(
    (a, b) => b.run_date.localeCompare(a.run_date) || b.created_at.localeCompare(a.created_at),
  );
}
