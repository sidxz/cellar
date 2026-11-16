"use client";

/**
 * The Ry × Rx grid of an R-group matrix: fragment structures on both axes, one button per
 * filled combination and a dashed "make?" cell for each empty one. Callers decide each
 * cell's text, badge, shade and hover title.
 */

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";
import { fragmentDisplay } from "../lib/sar-fragment-label";

const GAP_CLASS =
  "bg-[repeating-linear-gradient(45deg,transparent,transparent_5px,var(--color-muted)_5px,var(--color-muted)_7px)]";

/** Stable, collision-free key for a (y, x) cell. */
export function cellKey(y: string, x: string): string {
  return JSON.stringify([y, x]);
}

export interface MatrixGridCell {
  text: string;
  badge?: string;
  /** Background classes (potencyShade); empty for a neutral cell. */
  shade: string;
  title: string;
  /** Drawn with a strong outline; undefined where cells are not selectable. */
  selected?: boolean;
}

function AxisFragment({ smiles, orientation }: { smiles: string; orientation: "col" | "row" }) {
  const frag = fragmentDisplay(smiles);
  return (
    <div
      className={cn(
        orientation === "col"
          ? "flex w-20 flex-col items-center gap-0.5"
          : "flex w-24 items-center gap-1",
      )}
      title={frag.title}
    >
      {frag.thumbnailSmiles && (
        <StructureThumbnail
          smiles={frag.thumbnailSmiles}
          size={32}
          className={orientation === "row" ? "shrink-0" : undefined}
        />
      )}
      <span className="break-all text-[9px] leading-tight text-muted-foreground">{frag.label}</span>
    </div>
  );
}

/** The potent → weak swatches of potencyShade, for a legend. */
export function PotencyRamp() {
  return (
    <>
      <span>potent</span>
      <span className="h-3 w-5 rounded bg-green-600/30" />
      <span className="h-3 w-5 rounded bg-green-500/20" />
      <span className="h-3 w-5 rounded bg-amber-500/20" />
      <span className="h-3 w-5 rounded bg-orange-500/25" />
      <span className="h-3 w-5 rounded bg-red-600/30" />
      <span>weak</span>
    </>
  );
}

export function RGroupMatrixGrid({
  yLabel,
  xLabel,
  yValues,
  xValues,
  cells,
  onCellClick,
}: {
  yLabel: string;
  xLabel: string;
  /** Fragment SMILES, in display order. */
  yValues: string[];
  xValues: string[];
  /** By cellKey(y, x); a missing key is an empty combination. */
  cells: Map<string, MatrixGridCell>;
  onCellClick: (y: string, x: string) => void;
}) {
  return (
    <div className="overflow-auto">
      <table className="border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-background p-1 text-left align-bottom font-medium text-muted-foreground">
              {yLabel} ↓ / {xLabel} →
            </th>
            {xValues.map((x) => (
              <th key={x} className="p-1 align-bottom font-normal" scope="col">
                <AxisFragment smiles={x} orientation="col" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {yValues.map((y) => (
            <tr key={y}>
              <th
                scope="row"
                className="sticky left-0 z-10 bg-background p-1 text-left align-middle font-normal"
              >
                <AxisFragment smiles={y} orientation="row" />
              </th>
              {xValues.map((x) => {
                const cell = cells.get(cellKey(y, x));
                if (!cell) {
                  return (
                    <td
                      key={x}
                      className={cn(
                        "h-16 w-20 rounded border border-dashed border-muted-foreground/30 text-center align-middle text-muted-foreground/50",
                        GAP_CLASS,
                      )}
                      title="No compound with this combination — make?"
                    >
                      <span className="text-[10px]">make?</span>
                    </td>
                  );
                }
                return (
                  <td key={x} className="p-0">
                    <button
                      type="button"
                      aria-pressed={cell.selected}
                      className={cn(
                        "flex h-16 w-20 cursor-pointer flex-col items-center justify-center gap-0.5 rounded border border-border text-center",
                        cell.shade || "bg-muted/30",
                        cell.selected && "outline outline-2 outline-foreground",
                      )}
                      onClick={() => onCellClick(y, x)}
                      title={cell.title}
                    >
                      <span className="font-medium tabular-nums">{cell.text}</span>
                      {cell.badge && (
                        <span className="rounded-full bg-foreground/10 px-1.5 text-[10px] text-muted-foreground">
                          {cell.badge}
                        </span>
                      )}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
