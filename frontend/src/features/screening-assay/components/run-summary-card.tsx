"use client";

import { ProtocolName } from "@/shared/components/entity-name";
import { cn } from "@/shared/lib/utils";
import { usePlateMap } from "../hooks/use-plate-setup";
import { classifyZPrime, worstZPrime } from "../lib/qc-metrics";
import { PLATE_FORMAT_LABELS, type PlateFormat, type Run } from "../types";
import { ConditionChips } from "./condition-chips";
import { TargetChips } from "./target-chips";
import { Z_PRIME_BADGE } from "./z-prime-badge";

function Dot() {
  return <span className="text-muted-foreground/40">·</span>;
}

/** Keep assay quality separate from the workflow status beside the title. */
function ZPrimeFactChip({ value }: { value: number }) {
  const { label, className } = Z_PRIME_BADGE[classifyZPrime(value)];
  return (
    <a
      href="#quality"
      title="View run quality"
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium tabular-nums",
        className,
      )}
    >
      QC: Z&prime; {value.toFixed(2)} · {label}
    </a>
  );
}

interface RunSummaryCardProps {
  run: Run;
}

/** Compact facts beneath the run title; editable metadata lives on Details. */
export function RunSummaryCard({ run }: RunSummaryCardProps) {
  const zPrime = worstZPrime(run.qc_metrics);
  const plateFormatLabel = run.plate_format
    ? (PLATE_FORMAT_LABELS[run.plate_format as PlateFormat] ?? run.plate_format)
    : null;
  // A holder that is not a plate: say what the API calls it instead of format and count.
  const { data: plateMap } = usePlateMap(run.id);
  const holder = plateMap?.plates.find((p) => p.holder_kind !== "plate");

  return (
    <div className="space-y-2">
      {run.lock_reason && (
        <div className="rounded-md bg-destructive/10 px-3 py-2">
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
        <span className="tabular-nums">{run.run_date}</span>
        {holder ? (
          <>
            <Dot />
            <span>{holder.holder_label}</span>
          </>
        ) : (
          <>
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
          </>
        )}
        {!!run.targets?.length && <TargetChips targets={run.targets} />}
        <ConditionChips conditions={run.conditions} max={3} emptyFallback={null} />
        {zPrime !== null && (
          <>
            <Dot />
            <ZPrimeFactChip value={zPrime} />
          </>
        )}
      </div>
    </div>
  );
}
