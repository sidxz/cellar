"use client";

import { Fragment, useMemo } from "react";
import { cn } from "@/shared/lib/utils";
import { StructureThumbnail } from "@/shared/components/chemistry";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import type { DoseUnit, PlateData, PlateMapWell } from "../types";
import { plateDimensionsTuple, plateCellSizePx, rowLabel } from "../lib/plate-dimensions";
import { GROUP_PALETTE, WELL_TYPE_COLORS, CHART_COLORS, WELL_EMPTY_COLOR } from "@/shared/lib/chart-colors";

// ─── Constants ────────────────────────────────────────────────────────────────

const CONTROL_COLORS: Record<string, string> = {
  positive_control: WELL_TYPE_COLORS.positive_control,
  negative_control: WELL_TYPE_COLORS.negative_control,
  blank: WELL_TYPE_COLORS.blank,
  reference: CHART_COLORS.warning,
};

/** Build a color map for compounds that scales beyond the 12-slot palette.
 *
 * Up to 12 compounds: use the curated brand palette so colors match the
 * rest of the app's chart aesthetic. For larger screens, fall back to an
 * evenly-distributed HSL ramp with consistent saturation/lightness — every
 * compound stays distinct without cycling, and the hues feel like a single
 * family rather than a clashing rainbow. */
function buildCompoundColors(ids: string[]): Map<string, string> {
  const m = new Map<string, string>();
  if (ids.length <= GROUP_PALETTE.length) {
    ids.forEach((id, i) => m.set(id, GROUP_PALETTE[i]));
    return m;
  }
  ids.forEach((id, i) => {
    const hue = Math.round((i * 360) / ids.length);
    // 50% saturation + 55% lightness reads well on the dark surface and
    // on the white legend swatches without anything looking neon.
    m.set(id, `hsl(${hue}, 50%, 55%)`);
  });
  return m;
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

function WellTooltipContent({
  well,
  doseUnit,
}: {
  well: PlateMapWell;
  doseUnit: DoseUnit;
}) {
  const aliases: string[] = [];
  if (well.molecule_name && !aliases.includes(well.molecule_name)) {
    aliases.push(well.molecule_name);
  }
  for (const s of well.synonyms ?? []) {
    if (s && !aliases.includes(s)) aliases.push(s);
  }
  return (
    <div className="w-[200px] space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-xs font-medium">{well.position}</span>
        <span className="text-[10px] capitalize opacity-70">
          {well.well_type.replace(/_/g, " ")}
        </span>
      </div>
      {well.batch_number && (
        <p className="font-mono text-[11px] truncate">{well.batch_number}</p>
      )}
      {aliases.length > 0 && (
        <p className="text-[10px] italic opacity-70 line-clamp-2">
          {aliases.join(" · ")}
        </p>
      )}
      {well.dose != null && (
        <p className="text-[10px]">
          Dose: <span className="tabular-nums">{well.dose}</span> {doseUnit}
        </p>
      )}
      {well.smiles && (
        <div className="flex items-center justify-center rounded-sm bg-white p-1">
          <StructureThumbnail smiles={well.smiles} size={140} />
        </div>
      )}
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

interface PlateMapViewerProps {
  plate: PlateData;
  doseUnit: DoseUnit;
  className?: string;
}

export function PlateMapViewer({
  plate,
  doseUnit,
  className,
}: PlateMapViewerProps) {
  const [rows, cols] = plateDimensionsTuple(plate.format);
  const size = plateCellSizePx(plate.format);
  const showLabel = size >= 18;

  // Build a map: position -> well
  const wellMap = useMemo(() => {
    const m = new Map<string, PlateMapWell>();
    for (const well of plate.wells) m.set(well.position, well);
    return m;
  }, [plate.wells]);

  // Compound color assignment + per-compound stats for the legend table.
  const compoundEntries = useMemo(() => {
    const ids: string[] = [];
    const seen = new Set<string>();
    for (const w of plate.wells) {
      if (w.well_type === "sample" && w.molecule_id && !seen.has(w.molecule_id)) {
        seen.add(w.molecule_id);
        ids.push(w.molecule_id);
      }
    }
    const colors = buildCompoundColors(ids);
    return ids.map((id) => {
      const wells = plate.wells.filter((w) => w.molecule_id === id);
      const sample = wells[0];
      const aliases: string[] = [];
      if (sample?.molecule_name && !aliases.includes(sample.molecule_name)) {
        aliases.push(sample.molecule_name);
      }
      for (const s of sample?.synonyms ?? []) {
        if (s && !aliases.includes(s)) aliases.push(s);
      }
      return {
        id,
        color: colors.get(id) ?? CHART_COLORS.primary,
        regNumber: sample?.batch_number?.split("-")[0] ?? "",
        batchNumber: sample?.batch_number ?? "",
        aliases,
        wellCount: wells.length,
      };
    });
  }, [plate.wells]);

  const compoundColorMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const e of compoundEntries) m.set(e.id, e.color);
    return m;
  }, [compoundEntries]);

  function getWellStyle(well: PlateMapWell | undefined): {
    background: string;
    border?: string;
    opacity?: number;
  } {
    if (!well) return { background: WELL_EMPTY_COLOR };

    if (well.well_type === "sample") {
      const color = well.molecule_id
        ? (compoundColorMap.get(well.molecule_id) ?? CHART_COLORS.primary)
        : CHART_COLORS.primary;
      return { background: color };
    }

    const controlColor = CONTROL_COLORS[well.well_type];
    if (controlColor) {
      return {
        background: "transparent",
        border: `2px solid ${controlColor}`,
      };
    }

    return { background: WELL_EMPTY_COLOR };
  }

  const labelSize =
    size >= 28 ? "text-xs" : size >= 18 ? "text-[10px]" : "text-[8px]";

  const { summary } = plate;

  return (
    <div className={cn("space-y-4", className)}>
      {/* Summary bar */}
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span>
          <span className="font-medium text-foreground">{summary.compounds}</span> compounds
        </span>
        <span>
          <span className="font-medium text-foreground">{summary.sample_wells}</span> sample wells
        </span>
        <span>
          <span className="font-medium text-foreground">{summary.control_wells}</span> control wells
        </span>
        {summary.concentrations_per_compound > 0 && (
          <span>
            <span className="font-medium text-foreground">
              {summary.concentrations_per_compound}
            </span>{" "}
            conc / compound
          </span>
        )}
        {summary.replicates > 1 && (
          <span>
            <span className="font-medium text-foreground">{summary.replicates}</span>x replicates
          </span>
        )}
      </div>

      {/* Well-type legend — sample / POS / NEG / etc. Compound identity
          and the per-compound color mapping live in the table below the
          plate so the header stays compact. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <span
            className="h-3 w-3 rounded-sm inline-block"
            style={{ background: CHART_COLORS.primary }}
          />
          Sample
        </div>
        {Object.entries(CONTROL_COLORS).map(([type, color]) => {
          const hasType = plate.wells.some((w) => w.well_type === type);
          if (!hasType) return null;
          return (
            <div key={type} className="flex items-center gap-1.5">
              <span
                className="h-3 w-3 rounded-sm inline-block border-2"
                style={{ borderColor: color, background: "transparent" }}
              />
              <span className="capitalize">{type.replace(/_/g, " ")}</span>
            </div>
          );
        })}
      </div>

      {/* Plate grid */}
      <TooltipProvider delayDuration={120}>
      <div className="overflow-auto">
        <div
          className="inline-grid select-none"
          style={{
            gridTemplateColumns: `${size + 8}px repeat(${cols}, ${size}px)`,
            gridTemplateRows: `${size}px repeat(${rows}, ${size}px)`,
            gap: "1px",
          }}
        >
          {/* Top-left corner */}
          <div />

          {/* Column headers */}
          {Array.from({ length: cols }, (_, c) => (
            <div
              key={`col-${c}`}
              className={cn(
                "flex items-center justify-center",
                labelSize,
                "text-muted-foreground font-medium"
              )}
            >
              {c + 1}
            </div>
          ))}

          {/* Rows */}
          {Array.from({ length: rows }, (_, r) => {
            const rLabel = rowLabel(r);
            return (
              <Fragment key={`row-${r}`}>
                {/* Row header */}
                <div
                  className={cn(
                    "flex items-center justify-center",
                    labelSize,
                    "text-muted-foreground font-medium"
                  )}
                >
                  {rLabel}
                </div>

                {/* Wells */}
                {Array.from({ length: cols }, (_, c) => {
                  const pos = `${rLabel}${c + 1}`;
                  const well = wellMap.get(pos);
                  const style = getWellStyle(well);
                  const cell = (
                    <div
                      className="rounded-sm cursor-default transition-opacity hover:opacity-75"
                      style={{
                        width: size,
                        height: size,
                        background: style.background,
                        border: style.border,
                        boxSizing: "border-box",
                      }}
                    >
                      {showLabel && !well && (
                        <span className="flex h-full w-full items-center justify-center text-[8px] text-muted-foreground/40 select-none">
                          {pos}
                        </span>
                      )}
                    </div>
                  );
                  if (!well) return <Fragment key={pos}>{cell}</Fragment>;
                  return (
                    <Tooltip key={pos}>
                      <TooltipTrigger asChild>{cell}</TooltipTrigger>
                      <TooltipContent
                        side="top"
                        sideOffset={6}
                        collisionPadding={12}
                        className="bg-popover text-popover-foreground border shadow-lg p-2.5"
                      >
                        <WellTooltipContent well={well} doseUnit={doseUnit} />
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </Fragment>
            );
          })}
        </div>
      </div>
      </TooltipProvider>

      {/* Compound legend — table form. Sorted by reg id so the analyst can
          locate any compound by its CV-NNNNN. Aliases column truncates to
          keep rows scannable. */}
      {compoundEntries.length > 0 && (
        <div className="rounded-md border">
          <div className="border-b bg-muted/30 px-3 py-2 text-xs font-medium text-muted-foreground">
            Compounds on plate
          </div>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/20 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr className="border-b">
                  <th className="w-8 px-2 py-1.5"></th>
                  <th className="px-2 py-1.5 text-left font-medium">
                    Compound
                  </th>
                  <th className="px-2 py-1.5 text-left font-medium">Aliases</th>
                  <th className="px-2 py-1.5 text-right font-medium">Wells</th>
                </tr>
              </thead>
              <tbody>
                {[...compoundEntries]
                  .sort((a, b) =>
                    a.batchNumber.localeCompare(b.batchNumber, undefined, {
                      numeric: true,
                    }),
                  )
                  .map((e) => (
                    <tr key={e.id} className="border-b last:border-b-0">
                      <td className="px-2 py-1.5">
                        <span
                          className="block h-3 w-3 rounded-sm"
                          style={{ background: e.color }}
                          aria-hidden
                        />
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {e.batchNumber}
                      </td>
                      <td className="px-2 py-1.5 text-muted-foreground italic truncate max-w-[300px]">
                        {e.aliases.join(" · ") || "—"}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {e.wellCount}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
