"use client";

import { AlertCircle } from "lucide-react";

import type { ImportRowErrorModel } from "@/shared/lib/api/model";
import { cn } from "@/shared/lib/utils";

// Shared renderers for the import result vocabulary that BOTH importers
// (plate + summary) return from preview and import: unmatched refs, per-row
// errors, and the big-number tiles.

/** Big-number tile used by both import wizards' preview + confirm steps. */
export function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: "ok" | "warn" | "fail";
}) {
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        accent === "warn" && "border-amber-500/30 bg-amber-500/5",
        accent === "ok" && value > 0 && "border-green-500/30 bg-green-500/5",
        accent === "fail" && "border-destructive/40 bg-destructive/5",
      )}
    >
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}

/** Amber card listing unmatched compound/batch refs (first 20). */
export function UnmatchedRefsCard({
  refs,
  title,
  help,
}: {
  refs: string[];
  title: string;
  help: string;
}) {
  const shown = refs.slice(0, 20);
  const extra = refs.length - shown.length;
  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
      <div className="mb-1 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
        <AlertCircle className="h-4 w-4" />
        {refs.length} {title}
      </div>
      <p className="text-xs text-muted-foreground">{help}</p>
      <p className="mt-2 break-words font-mono text-xs">
        {shown.join(", ")}
        {extra > 0 && ` … +${extra} more`}
      </p>
    </div>
  );
}

/** Red card listing per-row errors ({row, error}) — the shared `errors` field. */
export function RowErrorsCard({
  errors,
  title,
  help,
  max = 20,
}: {
  errors: ImportRowErrorModel[];
  title?: string;
  help?: string;
  max?: number;
}) {
  const shown = errors.slice(0, max);
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
      <div className="mb-1 flex items-center gap-2 font-medium text-destructive">
        <AlertCircle className="h-4 w-4" />
        {title ?? `${errors.length} row error${errors.length === 1 ? "" : "s"}`}
      </div>
      {help && <p className="text-xs text-muted-foreground">{help}</p>}
      <ul className="ml-2 mt-2 space-y-1 font-mono text-xs">
        {shown.map((e, i) => (
          <li key={`${e.row}-${i}`}>
            <span className="text-foreground">Row {e.row}</span>
            <span className="ml-2 text-muted-foreground">— {e.error}</span>
          </li>
        ))}
        {errors.length > shown.length && (
          <li className="text-muted-foreground">…and {errors.length - shown.length} more</li>
        )}
      </ul>
    </div>
  );
}
