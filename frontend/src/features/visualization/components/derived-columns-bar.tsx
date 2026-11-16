"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import type { DerivedEntry } from "../hooks/use-derived";
import { type DerivedSpec, coverage } from "../lib/derived";
import type { Dataset } from "../types";

/** "R-groups · Core A", "Clusters · threshold 0.4", "Series". */
export function derivedTitle(spec: DerivedSpec): string {
  if (spec.kind === "rgroups") return `R-groups · ${spec.name}`;
  if (spec.kind === "clusters") return `Clusters · threshold ${spec.threshold}`;
  return "Series";
}

const clock = (ms: number) => {
  const s = Math.floor(Math.max(0, ms) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/** The time now, ticking each second while ``active``. */
function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

type Handlers = {
  onCancel: (id: string) => void;
  /** Retry after a failure; Run again after a cancel. */
  onRetry: (id: string) => void;
  onRemove: (id: string) => void;
  onRecompute: (id: string) => void;
  /** Add the set's plot: the cluster map, or an R-group matrix. */
  onPlot: (id: string) => void;
};

/** One line per derived column set under the header: running (elapsed time, Cancel),
 * ready (summary, warning, coverage with Recompute, its plot), failed (the server's
 * message, Retry) or cancelled (Run again); each removable. */
export function DerivedColumnsBar({
  entries,
  ds,
  plotsFull,
  ...on
}: Handlers & { entries: DerivedEntry[]; ds: Dataset; plotsFull: boolean }) {
  const now = useNow(entries.some((e) => e.status === "running"));
  return (
    <section
      aria-label="Chemistry columns"
      className="flex shrink-0 flex-col divide-y rounded-md border bg-card text-sm"
    >
      {entries.map((e) => (
        <Line key={e.spec.id} entry={e} ds={ds} now={now} plotsFull={plotsFull} {...on} />
      ))}
    </section>
  );
}

function Line({
  entry: e,
  ds,
  now,
  plotsFull,
  onCancel,
  onRetry,
  onRemove,
  onRecompute,
  onPlot,
}: Handlers & { entry: DerivedEntry; ds: Dataset; now: number; plotsFull: boolean }) {
  const id = e.spec.id;
  const title = derivedTitle(e.spec);
  const btn = "h-6 px-2 text-xs";
  const plot =
    e.spec.kind === "clusters" ? "Show map" : e.spec.kind === "rgroups" ? "Matrix" : null;
  const covered = e.status === "ready" && e.set ? coverage(ds, e.set) : null;

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-1">
      {e.spec.kind === "rgroups" && <StructureThumbnail smiles={e.spec.coreSmiles} size={24} />}
      <span className="font-medium">{title}</span>
      {e.status === "running" && (
        <>
          <span className="text-muted-foreground">Running · {clock(now - e.startedAt)}</span>
          <Button
            size="sm"
            variant="outline"
            className={btn}
            aria-label={`Cancel ${title}`}
            onClick={() => onCancel(id)}
          >
            Cancel
          </Button>
        </>
      )}
      {e.status === "failed" && (
        <>
          <span className="text-destructive">failed: {e.error}</span>
          <Button size="sm" variant="outline" className={btn} onClick={() => onRetry(id)}>
            Retry
          </Button>
        </>
      )}
      {e.status === "cancelled" && (
        <>
          <span className="text-muted-foreground">Cancelled</span>
          <Button size="sm" variant="outline" className={btn} onClick={() => onRetry(id)}>
            Run again
          </Button>
        </>
      )}
      {e.status === "ready" && e.set && (
        <>
          <span className="text-muted-foreground">{e.set.summary}</span>
          {e.set.warning && <span className="font-medium text-warning">{e.set.warning}</span>}
          {covered && covered.covered < covered.total && (
            <>
              <span className="text-muted-foreground">
                Computed for {covered.covered.toLocaleString()} of {covered.total.toLocaleString()}{" "}
                compounds
              </span>
              <Button size="sm" variant="outline" className={btn} onClick={() => onRecompute(id)}>
                Recompute
              </Button>
            </>
          )}
          {plot && (
            // A disabled button shows no tooltip of its own; the wrapper carries the reason.
            <span title={plotsFull ? "Up to 4 plots — close one to add another" : undefined}>
              <Button
                size="sm"
                variant="outline"
                className={btn}
                disabled={plotsFull}
                onClick={() => onPlot(id)}
              >
                {plot}
              </Button>
            </span>
          )}
        </>
      )}
      {e.status !== "running" && (
        <Button
          size="icon"
          variant="ghost"
          className="ml-auto h-6 w-6"
          aria-label={`Remove ${title}`}
          onClick={() => onRemove(id)}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}
