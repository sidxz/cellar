"use client";

import { X } from "lucide-react";
import { type ReactNode, useState } from "react";

import { BatchSelector } from "@/features/inventory/components/batch-selector";
import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { cn } from "@/shared/lib/utils";
import { type LabellingRow, parseDose } from "../lib/labelling-rows";
import { WELL_TYPE_LABELS, type WellType } from "../types";

const WELL_TYPES = Object.keys(WELL_TYPE_LABELS) as WellType[];

/** Left-pinned columns of the labelling table: select (fixed width) then Position. */
const STICKY_SELECT = "sticky left-0 z-[1] w-10 min-w-10";
const STICKY_POSITION = "sticky left-10 z-[1] whitespace-nowrap";
/** Position pinned on its own, when there is no select column. */
const STICKY_POSITION_ALONE = "sticky left-0 z-[1] whitespace-nowrap";
/** ``bg-muted/40`` over the background, made opaque for pinned cells. */
const SELECTED_OPAQUE = "bg-[color-mix(in_oklab,var(--muted)_40%,var(--background))]";

const isBadDose = (dose: string) => parseDose(dose) === undefined;

export function Notice({ tone, children }: { tone: "ok" | "warn" | "bad"; children: ReactNode }) {
  return (
    <div
      role={tone === "bad" ? "alert" : undefined}
      className={cn(
        "rounded-md border p-3 text-sm",
        tone === "ok" && "border-green-500/30 bg-green-500/5",
        tone === "warn" &&
          "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300/90",
        tone === "bad" && "border-destructive/40 bg-destructive/5 text-destructive",
      )}
    >
      {children}
    </div>
  );
}

export interface LabellingTableProps {
  rows: readonly LabellingRow[];
  /** Printed as given. */
  doseUnit: string;
  onUpdate: (key: string, patch: Partial<LabellingRow>) => void;
  onSetRole: (keys: ReadonlySet<string>, wellType: WellType) => void;
  /** The Use column, "Mark unused" and "Use again". */
  showUse: boolean;
  /** When set, Role, Compound, Batch and Concentration are read-only and this
   *  sentence is shown above the table. */
  calculatedLocked?: string | null;
  /** The wizard's "No match" and "matched" badges, by row key. */
  hints?: ReadonlyMap<string, { noMatch: boolean; suggestedId: string | null }>;
  /** Why the rows cannot be stored yet, shown as "To continue, correct …". */
  problem: string | null;
}

/** One row per position: label, role, compound and batch, concentration and
 *  note, with bulk role and (optionally) marking positions unused. */
export function LabellingTable({
  rows,
  doseUnit: unit,
  onUpdate,
  onSetRole,
  showUse,
  calculatedLocked,
  hints,
  problem,
}: LabellingTableProps) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [bulkRole, setBulkRole] = useState<WellType>("sample");
  const locked = !!calculatedLocked;
  // Selection serves the bulk role and Mark unused; with neither there is none.
  const selectable = showUse || !locked;
  const allKeys = rows.map((r) => r.key);
  const allSelected = allKeys.length > 0 && selected.size === allKeys.length;

  const toggle = (key: string, on: boolean) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  return (
    <div className="flex min-h-0 flex-col gap-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {selectable && (
          <span className="text-muted-foreground">
            {selected.size} row{selected.size === 1 ? "" : "s"} selected
          </span>
        )}
        {!locked && (
          <>
            <span className="ml-2 text-muted-foreground">Set role</span>
            <Select value={bulkRole} onValueChange={(v) => setBulkRole(v as WellType)}>
              <SelectTrigger className="h-8 w-44" aria-label="Role for selected rows">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WELL_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {WELL_TYPE_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              disabled={selected.size === 0}
              onClick={() => onSetRole(selected, bulkRole)}
            >
              Apply to selected
            </Button>
          </>
        )}
        {showUse && (
          <Button
            size="sm"
            variant="ghost"
            disabled={selected.size === 0}
            onClick={() => {
              for (const key of selected) onUpdate(key, { used: false });
              setSelected(new Set());
            }}
          >
            Mark unused
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          Concentration is in {unit}, the protocol&apos;s dose unit
        </span>
      </div>

      {locked && <p className="text-sm text-muted-foreground">{calculatedLocked}</p>}

      {/* The only scroller: header row sticks to the top, the select and
          Position columns stick to the left. */}
      <div className="min-h-0 overflow-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-muted">
            <tr className="border-b">
              {selectable && (
                <th className={cn(STICKY_SELECT, "bg-muted px-3 py-2")}>
                  <Checkbox
                    aria-label="Select all positions"
                    checked={allSelected}
                    onCheckedChange={(on) => setSelected(new Set(on === true ? allKeys : []))}
                  />
                </th>
              )}
              <th
                className={cn(
                  selectable ? STICKY_POSITION : STICKY_POSITION_ALONE,
                  "bg-muted px-3 py-2 text-left font-medium",
                )}
              >
                Position
              </th>
              <th className="px-3 py-2 text-left font-medium">Label</th>
              <th className="px-3 py-2 text-left font-medium">Role</th>
              <th className="px-3 py-2 text-left font-medium">Compound</th>
              <th className="px-3 py-2 text-left font-medium">Batch</th>
              <th className="px-3 py-2 text-left font-medium">Conc. ({unit})</th>
              <th className="px-3 py-2 text-left font-medium">Note</th>
              {showUse && <th className="px-3 py-2 text-left font-medium">Use</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const hint = hints?.get(r.key);
              return (
                <PositionRow
                  key={r.key}
                  position={r}
                  selectable={selectable}
                  selected={selected.has(r.key)}
                  showUse={showUse}
                  locked={locked}
                  noMatch={hint?.noMatch ?? false}
                  suggestedId={hint?.suggestedId ?? null}
                  onToggle={(on) => toggle(r.key, on)}
                  onUpdate={(patch) => onUpdate(r.key, patch)}
                />
              );
            })}
          </tbody>
        </table>
      </div>
      {problem && (
        <output className="block text-sm text-destructive">To continue, correct {problem}</output>
      )}
    </div>
  );
}

function PositionRow({
  position: p,
  selectable,
  selected,
  showUse,
  locked,
  noMatch,
  suggestedId,
  onToggle,
  onUpdate,
}: {
  position: LabellingRow;
  selectable: boolean;
  selected: boolean;
  showUse: boolean;
  locked: boolean;
  noMatch: boolean;
  suggestedId: string | null;
  onToggle: (on: boolean) => void;
  onUpdate: (patch: Partial<LabellingRow>) => void;
}) {
  const cell = "px-3 py-1.5 align-middle";
  // Opaque, so scrolled cells pass beneath; matches the row's selected tint.
  const stickyBg = selected ? SELECTED_OPAQUE : "bg-background";
  const checkbox = selectable && (
    <td className={cn(cell, STICKY_SELECT, stickyBg)}>
      <Checkbox
        aria-label={`Select ${p.positionLabel}`}
        checked={selected}
        onCheckedChange={(on) => onToggle(on === true)}
      />
    </td>
  );
  const positionCell = (
    <td className={cn(cell, selectable ? STICKY_POSITION : STICKY_POSITION_ALONE, stickyBg)}>
      {p.positionLabel}
    </td>
  );

  if (!p.used) {
    return (
      <tr className="border-b text-muted-foreground last:border-b-0">
        {checkbox}
        {positionCell}
        <td className={cell}>{p.label || "empty"}</td>
        <td className={cell}>{WELL_TYPE_LABELS[p.wellType]}</td>
        <td className={cell}>{p.moleculeName ?? "No compound"}</td>
        <td className={cell}>None</td>
        <td className={cell}>{p.dose}</td>
        <td className={cell}>{p.note}</td>
        {showUse && (
          <td className={cell}>
            <Button size="sm" variant="ghost" onClick={() => onUpdate({ used: true })}>
              Use again
            </Button>
          </td>
        )}
      </tr>
    );
  }

  return (
    <tr className={cn("border-b last:border-b-0", selected && "bg-muted/40")}>
      {checkbox}
      {positionCell}
      <td className={cell}>
        <Input
          className="h-8 w-44"
          aria-label={`Label for ${p.positionLabel}`}
          placeholder="No name in file"
          value={p.label}
          aria-invalid={p.label.length > 200}
          onChange={(e) => onUpdate({ label: e.target.value })}
        />
      </td>
      <td className={cell}>
        {locked ? (
          WELL_TYPE_LABELS[p.wellType]
        ) : (
          <Select value={p.wellType} onValueChange={(v) => onUpdate({ wellType: v as WellType })}>
            <SelectTrigger className="h-8 w-40" aria-label={`Role for ${p.positionLabel}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WELL_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {WELL_TYPE_LABELS[t]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </td>
      <td className={cell}>
        {locked ? (
          <span className={cn("whitespace-nowrap", !p.moleculeId && "text-muted-foreground")}>
            {p.moleculeName ?? "No compound"}
          </span>
        ) : p.moleculeId ? (
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <span>{p.moleculeName}</span>
            {p.moleculeId === suggestedId && (
              <Badge
                variant="outline"
                className="border-green-500/30 bg-green-500/10 text-green-400"
              >
                matched
              </Badge>
            )}
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              aria-label={`Change compound for ${p.positionLabel}`}
              onClick={() => onUpdate({ moleculeId: null, moleculeName: null, batchId: null })}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            {noMatch && <Badge variant="outline">No match</Badge>}
            <MoleculeSelector
              selectedId={null}
              onSelect={(id, mol) =>
                onUpdate({
                  moleculeId: id,
                  moleculeName: mol?.name ?? null,
                  batchId: null,
                })
              }
            />
          </div>
        )}
      </td>
      <td className={cell}>
        {locked ? (
          <span className={cn(!p.batchId && "text-muted-foreground")}>
            {p.batchId ? (p.batchNumber ?? p.batchId) : "None"}
          </span>
        ) : p.moleculeId ? (
          <div className="flex items-center gap-1.5">
            <BatchSelector
              moleculeId={p.moleculeId}
              selectedId={p.batchId}
              onSelect={(batchId) => onUpdate({ batchId })}
            />
            {!p.batchId && (
              <Badge
                variant="outline"
                className="border-amber-500/30 bg-amber-500/10 text-amber-400"
              >
                not chosen
              </Badge>
            )}
          </div>
        ) : (
          <span className="text-muted-foreground">None</span>
        )}
      </td>
      <td className={cell}>
        {locked ? (
          <span className="tabular-nums">{p.dose}</span>
        ) : (
          <Input
            className="h-8 w-28 text-right"
            inputMode="decimal"
            aria-label={`Concentration for ${p.positionLabel}`}
            value={p.dose}
            aria-invalid={isBadDose(p.dose)}
            onChange={(e) => onUpdate({ dose: e.target.value })}
          />
        )}
      </td>
      <td className={cell}>
        <Input
          className="h-8 w-48"
          aria-label={`Note for ${p.positionLabel}`}
          placeholder="Note"
          value={p.note}
          aria-invalid={p.note.length > 1000}
          onChange={(e) => onUpdate({ note: e.target.value })}
        />
      </td>
      {showUse && (
        <td className={cell}>
          <Badge variant="outline" className="border-green-500/30 bg-green-500/10 text-green-400">
            Used
          </Badge>
        </td>
      )}
    </tr>
  );
}
