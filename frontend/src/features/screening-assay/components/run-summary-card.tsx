"use client";

import { ProtocolName } from "@/shared/components/entity-name";
import { Card, CardContent } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { classifyZPrime, worstZPrime } from "../lib/qc-metrics";
import { PLATE_FORMAT_LABELS, type PlateFormat, type Protocol, type Run } from "../types";
import { RunNotesLine } from "./run-notes-line";
import {
  CollectionsRelation,
  ConditionsRelation,
  TagsRelation,
  TargetsRelation,
} from "./run-relations";
import { Z_PRIME_BADGE } from "./z-prime-badge";

function Dot() {
  return <span className="text-muted-foreground/40">·</span>;
}

/** Worst-plate Z' surfaced as a color-coded chip in the facts band. Links to
 *  the QC Metrics tab (`#qc`, picked up by `useHashTab` in the data panel). */
function ZPrimeFactChip({ value }: { value: number }) {
  const { label, className } = Z_PRIME_BADGE[classifyZPrime(value)];
  return (
    <a
      href="#qc"
      title="View QC Metrics"
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium tabular-nums",
        className,
      )}
    >
      Z&prime; {value.toFixed(2)} · {label}
    </a>
  );
}

interface RunSummaryCardProps {
  run: Run;
  protocol: Protocol | undefined;
  /** Editor on an unlocked run — can edit targets, collections, and notes. */
  canEditMeta: boolean;
  /** Editor — can edit tags (tags are not frozen by the run lock). */
  canEditTags: boolean;
}

/**
 * Condensed run header. Collapses the former Details / Targets / Collections /
 * Tags cards into a single card with two bands: intrinsic facts (+ a Z' quality
 * chip and click-to-edit notes) on top, and editable associations
 * (targets, collection coverage, tags) below a hairline. Associations show as
 * compact chips and reveal their existing multi-select editors on demand —
 * no always-on dropdowns.
 */
export function RunSummaryCard({ run, protocol, canEditMeta, canEditTags }: RunSummaryCardProps) {
  const zPrime = worstZPrime(run.qc_metrics);
  const plateFormatLabel = run.plate_format
    ? (PLATE_FORMAT_LABELS[run.plate_format as PlateFormat] ?? run.plate_format)
    : null;

  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        {run.lock_reason && (
          <div className="mb-3 rounded-md bg-destructive/10 px-3 py-2">
            <p className="text-sm font-medium text-destructive">Lock reason: {run.lock_reason}</p>
          </div>
        )}

        {/* Facts band */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span className="text-muted-foreground">Protocol</span>
          <a
            href={`/assays/protocols/${run.protocol_id}`}
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            <ProtocolName id={run.protocol_id} />
          </a>
          <Dot />
          <span className="font-mono">{run.run_date}</span>
          {plateFormatLabel && (
            <>
              <Dot />
              <span>{plateFormatLabel}</span>
            </>
          )}
          <Dot />
          <span>
            {run.plate_count} {run.plate_count === 1 ? "plate" : "plates"}
          </span>
          {zPrime !== null && (
            <>
              <Dot />
              <ZPrimeFactChip value={zPrime} />
            </>
          )}
        </div>

        <RunNotesLine run={run} canEdit={canEditMeta} />

        <div className="my-3 border-t" />

        {/* Relations band */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <TargetsRelation run={run} canEdit={canEditMeta} />
          <CollectionsRelation run={run} protocol={protocol} canEdit={canEditMeta} />
          <ConditionsRelation run={run} protocol={protocol} canEdit={canEditMeta} />
        </div>
        <div className="mt-2.5">
          <TagsRelation runId={run.id} canEdit={canEditTags} />
        </div>
      </CardContent>
    </Card>
  );
}
