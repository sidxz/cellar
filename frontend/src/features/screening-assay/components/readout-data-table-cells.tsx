"use client";

import { EntityLink } from "@/shared/components/entity-link";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import type { ReadoutTableRow } from "./readout-data-table-view";

export function ReadoutCompoundCell({ data, query }: { data: ReadoutTableRow; query: string }) {
  const search = query.trim().toLocaleLowerCase();
  const code = /^[a-z][a-z\d]*[-_]\d[\w-]*$/i;
  const aliases = data.aliases.toSorted(
    (a, b) =>
      Number(!!search && b.toLocaleLowerCase().includes(search)) -
        Number(!!search && a.toLocaleLowerCase().includes(search)) ||
      Number(code.test(a)) - Number(code.test(b)),
  );
  return (
    <div className="flex h-full min-w-0 flex-col justify-center gap-0.5 py-1.5 leading-snug">
      <EntityLink
        type="compound"
        id={data.moleculeId}
        label={data.registrationNumber || data.moleculeName || "Unknown compound"}
        className="w-fit max-w-full font-sans font-semibold"
      />
      {aliases.length > 0 && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="flex w-fit max-w-full items-baseline gap-1 rounded-sm text-left text-xs text-foreground/80 hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
              aria-label={`Show aliases for ${data.registrationNumber}`}
            >
              <span className="truncate">{aliases[0]}</span>
              {aliases.length > 1 && (
                <span className="shrink-0 text-primary">+{aliases.length - 1}</span>
              )}
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] space-y-3">
            <p className="text-sm font-medium">{data.registrationNumber} · aliases</p>
            <ul className="max-h-64 space-y-2 overflow-y-auto text-sm">
              {aliases.map((alias) => (
                <li key={alias} className="break-words select-text">
                  {alias}
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      )}
      {data.batchNumber && (
        <span
          className="truncate text-xs text-muted-foreground"
          title={`Batch: ${data.batchNumber}`}
        >
          {data.batchNumber}
        </span>
      )}
    </div>
  );
}

export function ReadoutPositionCell({ data }: { data: ReadoutTableRow }) {
  return (
    <div className="flex h-full flex-col justify-center gap-0.5 leading-snug">
      <span>{data.position ?? (data.wellId ? "—" : "Summary")}</span>
      {data.plateLabel && (
        <span className="truncate text-xs text-muted-foreground" title={data.plateLabel}>
          {data.plateLabel}
        </span>
      )}
    </div>
  );
}
